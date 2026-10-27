"""Measure serving throughput and latency through the real serving path.

Modes: `local` loads each model in-process, `http` hits a running API, `merge`
combines existing reports. Accuracy is not measured here — use `evaluate.py`."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.vlm_registry import (
    REGISTRY,
    check_available,
    resolve,
    resolve_model_dir,
    snapshot_complete,
)
from src.utils.cccd_schema import CardSide, infer_side_from_filename

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")


def collect_images(paths: Sequence[str], limit: Optional[int]) -> List[Path]:
    """Collect images from files or directories; `--limit` applies per directory."""
    found: List[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            in_dir = [
                p for p in sorted(path.iterdir())
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS
            ]
            found.extend(in_dir[:limit] if limit else in_dir)
        elif path.is_file():
            found.append(path)
        else:
            logger.warning("Bỏ qua '%s': không tồn tại", raw)
    if not found:
        raise SystemExit(f"Không tìm thấy ảnh nào trong {list(paths)}")
    return found


def percentile(ordered: Sequence[float], q: float) -> float:
    """Nearest-rank percentile on a sorted list, matching evaluate.py."""
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def latency_stats(latencies_ms: Sequence[float]) -> Dict[str, float]:
    if not latencies_ms:
        return {}
    ordered = sorted(latencies_ms)
    return {
        "p50": round(statistics.median(ordered), 1),
        "p95": round(percentile(ordered, 0.95), 1),
        "p99": round(percentile(ordered, 0.99), 1),
        "mean": round(statistics.fmean(ordered), 1),
        "min": round(ordered[0], 1),
        "max": round(ordered[-1], 1),
    }


def gpu_info() -> Dict[str, object]:
    """GPU name and VRAM, so a report says which machine produced it."""
    try:
        import torch
    except ImportError:
        return {"gpu": "n/a (chưa cài torch)"}
    if not torch.cuda.is_available():
        return {"gpu": "cpu", "torch": torch.__version__}
    props = torch.cuda.get_device_properties(0)
    return {
        "gpu": props.name,
        "vram_gb": round(props.total_memory / 2**30, 1),
        "torch": torch.__version__,
    }


def render_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    cells = [[("-" if c is None else str(c)) for c in row] for row in rows]
    widths = [
        max([len(str(headers[i]))] + [len(row[i]) for row in cells])
        for i in range(len(headers))
    ]
    line = lambda row: "| " + " | ".join(  # noqa: E731
        str(c).ljust(widths[i]) for i, c in enumerate(row)
    ) + " |"
    out = [line(headers), "|" + "|".join("-" * (w + 2) for w in widths) + "|"]
    out.extend(line(row) for row in cells)
    return "\n".join(out)


def print_table(title: str, headers: Sequence[str], rows: Sequence[Sequence[object]]) -> None:
    print(f"\n### {title}\n")
    print(render_table(headers, rows))


def bench_one_model(
    serving, model_key: str, blobs: List[tuple], sides: List[CardSide], args: argparse.Namespace
) -> Optional[dict]:
    """Load one model and sweep batch sizes; skipped models return a `skipped` reason."""
    import io

    import torch
    from PIL import Image

    spec = resolve(model_key)
    ok, reason = check_available(spec)
    if not ok:
        logger.warning("⏭ Bỏ qua %s: %s", model_key, reason)
        return {"model_key": model_key, "skipped": reason}

    model_dir = resolve_model_dir(spec, args.models_dir)
    complete, why = snapshot_complete(model_dir)
    if not complete:
        logger.warning(
            "⏭ Bỏ qua %s: snapshot base chưa đủ (%s) tại %s. Tải bằng "
            "ensure_snapshot(spec, dir) ở notebook trước.", model_key, why, model_dir,
        )
        return {"model_key": model_key, "skipped": f"snapshot: {why}"}

    adapters = serving.discover_adapters(model_key, args.checkpoint_dir)
    if not adapters:
        logger.warning(
            "%s không có adapter nào trong '%s' → đo trên base thuần (zero-shot). "
            "Tốc độ vẫn so sánh được, nhưng output sẽ kém.", model_key, args.checkpoint_dir,
        )
    # Images of a side without an adapter would measure the wrong thing.
    keep = [
        i for i, side in enumerate(sides)
        if not adapters or side in adapters or side == CardSide.UNKNOWN
    ]
    if len(keep) < len(sides):
        dropped = sorted({sides[i].value for i in range(len(sides)) if i not in set(keep)})
        logger.warning(
            "%s: bỏ %d ảnh thuộc mặt chưa có adapter (%s)",
            model_key, len(sides) - len(keep), ", ".join(dropped),
        )
    if not keep:
        return {"model_key": model_key, "skipped": "không có ảnh nào khớp adapter đang có"}
    model_blobs = [blobs[i] for i in keep]
    model_sides = [sides[i] for i in keep]

    logger.info(
        "▶ %s [%s] — %d ảnh × %d vòng, base %s",
        model_key, spec.model_id, len(model_blobs), args.repeat, model_dir,
    )
    serving.STATE["model"], serving.STATE["processor"] = serving.load_inference_model(
        str(model_dir), args.checkpoint_dir, model_key
    )
    run_sides = [serving.serving_side(side) or side for side in model_sides]

    def decode(n: Optional[int] = None) -> List["Image.Image"]:
        return [Image.open(io.BytesIO(blob)).convert("RGB") for _, blob in model_blobs[:n]]

    runs: List[dict] = []
    try:
        for batch_size in args.batch_sizes:
            # Warmup: the first generate pays for CUDA autotune and NF4 dequant.
            serving.run_inference_batch(
                decode(batch_size), run_sides[:batch_size], max_batch=batch_size
            )

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()

            batch_latencies: List[float] = []
            n_parse_ok = 0
            n_total = 0
            wall0 = time.perf_counter()
            for _ in range(args.repeat):
                images = decode()
                for start in range(0, len(images), batch_size):
                    chunk = images[start : start + batch_size]
                    chunk_sides = run_sides[start : start + batch_size]
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    t0 = time.perf_counter()
                    raws = serving.run_inference_batch(chunk, chunk_sides, max_batch=batch_size)
                    if torch.cuda.is_available():
                        torch.cuda.synchronize()
                    batch_latencies.append((time.perf_counter() - t0) * 1000)
                    n_total += len(chunk)
                    n_parse_ok += sum(
                        1 for raw in raws if serving.parse_json_safe(raw) is not None
                    )
            wall_s = time.perf_counter() - wall0

            run = {
                "batch_size": batch_size,
                "n_batches": len(batch_latencies),
                "n_images": n_total,
                "batch_latency_ms": latency_stats(batch_latencies),
                "ms_per_image": round(sum(batch_latencies) / n_total, 1) if n_total else None,
                "images_per_sec": round(n_total / wall_s, 3) if wall_s else None,
                # A drop here means padding is broken and the speed numbers are meaningless.
                "parse_ok_rate": round(n_parse_ok / n_total, 4) if n_total else None,
            }
            if torch.cuda.is_available():
                run["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)
            runs.append(run)
            logger.info(
                "  batch=%-2d → %.1f ms/ảnh | %.2f ảnh/s | parse_ok=%.0f%% | peak %s MB",
                batch_size, run["ms_per_image"], run["images_per_sec"],
                100 * (run["parse_ok_rate"] or 0), run.get("peak_vram_mb", "-"),
            )
    finally:
        # Free VRAM even on OOM so the next model can load.
        serving.unload_model()

    return {
        "mode": "local",
        "model_key": model_key,
        "model_id": spec.model_id,
        "family": spec.family,
        "params_b": spec.params_b,
        "base_model_dir": str(model_dir),
        "sides": sorted({s.value for s in run_sides}),
        "adapters": {side.value: str(path) for side, path in adapters.items()},
        "config": {
            "n_images": len(model_blobs),
            "repeat": args.repeat,
            "batch_sizes": args.batch_sizes,
            "max_new_tokens": serving.MAX_NEW_TOKENS,
        },
        "env": gpu_info(),
        "runs": runs,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def bench_local(args: argparse.Namespace) -> List[dict]:
    """Sweep batch sizes for each model in `--models`, loading them one at a time."""
    try:
        # Import the serving module itself so the benchmark measures deployed code.
        from app import main as serving
    except ImportError as exc:
        raise SystemExit(
            f"Không import được app.main ({exc}). Chế độ local dùng chính đường phục "
            f"vụ nên cần đủ dependency của API: pip install fastapi uvicorn python-multipart"
        )

    image_paths = collect_images(args.images, args.limit)
    # Keep bytes and decode per round: images are resized in place, so reusing them
    # would make later rounds artificially fast.
    blobs = [(p.name, p.read_bytes()) for p in image_paths]
    sides = [infer_side_from_filename(p.name) for p in image_paths]
    logger.info(
        "Tập ảnh: %d (%s)", len(blobs),
        ", ".join(f"{s.value}={sum(1 for x in sides if x == s)}" for s in sorted(
            set(sides), key=lambda x: x.value)),
    )

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    reports: List[dict] = []
    for model_key in args.models:
        report = bench_one_model(serving, model_key, blobs, sides, args)
        if report is None or report.get("skipped"):
            continue
        path = report_dir / f"benchmark_local_{model_key}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info("💾 %s", path)
        reports.append(report)

    for report in reports:
        print_table(
            f"Local — {report['model_key']} ({report['model_id']})",
            ["batch", "ms/ảnh", "ảnh/s", "p50 lô (ms)", "p95 lô (ms)", "parse_ok",
             "peak VRAM (MB)"],
            [
                [
                    r["batch_size"], r["ms_per_image"], r["images_per_sec"],
                    r["batch_latency_ms"].get("p50"), r["batch_latency_ms"].get("p95"),
                    f"{100 * (r['parse_ok_rate'] or 0):.0f}%", r.get("peak_vram_mb"),
                ]
                for r in report["runs"]
            ],
        )
    return reports


def _post_single(session, url: str, path: Path) -> dict:
    t0 = time.perf_counter()
    try:
        with open(path, "rb") as f:
            resp = session.post(
                f"{url}/extract-cccd/",
                files={"file": (path.name, f, "image/jpeg")},
                params={"side": "auto"},
                timeout=600,
            )
        elapsed = (time.perf_counter() - t0) * 1000
        body = resp.json()
        return {
            "ms": elapsed,
            "ok": resp.status_code == 200 and "error" not in body,
            "parse_ok": bool(body.get("parse_ok")),
            "error": body.get("error"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ms": (time.perf_counter() - t0) * 1000, "ok": False, "parse_ok": False,
                "error": str(exc)}


def _post_batch(session, url: str, paths: Sequence[Path]) -> dict:
    handles = [open(p, "rb") for p in paths]
    try:
        files = [("files", (p.name, h, "image/jpeg")) for p, h in zip(paths, handles)]
        t0 = time.perf_counter()
        resp = session.post(
            f"{url}/extract-cccd/batch", files=files, params={"side": "auto"}, timeout=600
        )
        elapsed = (time.perf_counter() - t0) * 1000
        body = resp.json()
        results = body.get("results") or []
        return {
            "ms": elapsed,
            "n": len(paths),
            "ok": resp.status_code == 200 and "error" not in body,
            "n_parse_ok": sum(1 for r in results if r and r.get("parse_ok")),
            "server_ms": (body.get("timing") or {}).get("total_ms"),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ms": 0.0, "n": len(paths), "ok": False, "n_parse_ok": 0, "error": str(exc)}
    finally:
        for handle in handles:
            handle.close()


def bench_http(args: argparse.Namespace) -> dict:
    """Sweep concurrency then batch size against a running API."""
    try:
        import requests
    except ImportError:
        raise SystemExit("Chế độ http cần `pip install requests`")

    image_paths = collect_images(args.images, args.limit)

    # One Session per thread: `requests.Session` is not guaranteed thread-safe.
    local_store = threading.local()

    def get_session():
        if not hasattr(local_store, "session"):
            local_store.session = requests.Session()
        return local_store.session

    session = get_session()
    health = session.get(f"{args.url}/health", timeout=30).json()
    logger.info("Server: %s", health)
    if not health.get("model_loaded"):
        raise SystemExit("Model chưa load xong — đợi log '✓ Model sẵn sàng phục vụ' rồi chạy lại")

    model_key = health.get("model_key") or "unknown"
    served_sides = set(health.get("sides") or [])
    if served_sides:
        # Otherwise the run would measure the throughput of returning errors.
        kept = [
            p for p in image_paths
            if infer_side_from_filename(p.name).value in served_sides
            or infer_side_from_filename(p.name) == CardSide.UNKNOWN
        ]
        if len(kept) < len(image_paths):
            logger.warning(
                "Bỏ %d ảnh: server '%s' chỉ có adapter mặt %s",
                len(image_paths) - len(kept), model_key, sorted(served_sides),
            )
        image_paths = kept or image_paths

    logger.info("Warmup 1 request...")
    _post_single(session, args.url, image_paths[0])

    report: dict = {
        "mode": "http",
        "model_key": model_key,
        "model_id": health.get("model_id"),
        "params_b": health.get("params_b"),
        "sides": sorted(served_sides),
        "config": {
            "url": args.url,
            "n_images": len(image_paths),
            "repeat": args.repeat,
            "concurrency": args.concurrency,
            "batch_sizes": args.batch_sizes,
        },
        "env": gpu_info(),
        "server_health": health,
        "concurrency_runs": [],
        "batch_runs": [],
    }

    queue = [p for _ in range(args.repeat) for p in image_paths]
    for workers in args.concurrency:
        wall0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            outcomes = list(pool.map(lambda p: _post_single(get_session(), args.url, p), queue))
        wall_s = time.perf_counter() - wall0

        ok = [o for o in outcomes if o["ok"]]
        run = {
            "concurrency": workers,
            "n_requests": len(outcomes),
            "n_errors": len(outcomes) - len(ok),
            "latency_ms": latency_stats([o["ms"] for o in ok]),
            "images_per_sec": round(len(ok) / wall_s, 3) if wall_s else None,
            "parse_ok_rate": round(sum(o["parse_ok"] for o in ok) / len(ok), 4) if ok else None,
        }
        report["concurrency_runs"].append(run)
        logger.info(
            "concurrency=%-2d → p50=%.0fms p95=%.0fms | %.2f ảnh/s | lỗi %d",
            workers, run["latency_ms"].get("p50", 0), run["latency_ms"].get("p95", 0),
            run["images_per_sec"] or 0, run["n_errors"],
        )

    if report["concurrency_runs"]:
        print_table(
            f"HTTP {model_key} — quét mức đồng thời (1 ảnh / request)",
            ["đồng thời", "p50 (ms)", "p95 (ms)", "p99 (ms)", "ảnh/s", "lỗi", "parse_ok"],
            [
                [
                    r["concurrency"], r["latency_ms"].get("p50"), r["latency_ms"].get("p95"),
                    r["latency_ms"].get("p99"), r["images_per_sec"], r["n_errors"],
                    f"{100 * (r['parse_ok_rate'] or 0):.0f}%",
                ]
                for r in report["concurrency_runs"]
            ],
        )

    for batch_size in args.batch_sizes or []:
        chunks = [
            image_paths[i : i + batch_size] for i in range(0, len(image_paths), batch_size)
        ] * args.repeat
        wall0 = time.perf_counter()
        outcomes = [_post_batch(session, args.url, chunk) for chunk in chunks]
        wall_s = time.perf_counter() - wall0

        ok = [o for o in outcomes if o["ok"]]
        n_images = sum(o["n"] for o in ok)
        run = {
            "batch_size": batch_size,
            "n_requests": len(outcomes),
            "n_errors": len(outcomes) - len(ok),
            "request_latency_ms": latency_stats([o["ms"] for o in ok]),
            "ms_per_image": round(sum(o["ms"] for o in ok) / n_images, 1) if n_images else None,
            "images_per_sec": round(n_images / wall_s, 3) if wall_s else None,
            "parse_ok_rate": (
                round(sum(o["n_parse_ok"] for o in ok) / n_images, 4) if n_images else None
            ),
        }
        report["batch_runs"].append(run)
        logger.info(
            "batch=%-2d → %.1f ms/ảnh | %.2f ảnh/s | lỗi %d",
            batch_size, run["ms_per_image"] or 0, run["images_per_sec"] or 0, run["n_errors"],
        )

    if report["batch_runs"]:
        print_table(
            f"HTTP {model_key} — quét batch size (/extract-cccd/batch)",
            ["batch", "ms/ảnh", "ảnh/s", "p50 request (ms)", "lỗi", "parse_ok"],
            [
                [
                    r["batch_size"], r["ms_per_image"], r["images_per_sec"],
                    r["request_latency_ms"].get("p50"), r["n_errors"],
                    f"{100 * (r['parse_ok_rate'] or 0):.0f}%",
                ]
                for r in report["batch_runs"]
            ],
        )
        cap = health.get("max_batch_size")
        if cap and any(r["batch_size"] > cap for r in report["batch_runs"]):
            logger.warning(
                "Server đang giới hạn MAX_BATCH_SIZE=%s → lô lớn hơn bị cắt nhỏ, "
                "throughput sẽ chững lại từ mốc đó. Đặt env MAX_BATCH_SIZE rồi khởi "
                "động lại API nếu muốn đo mức cao hơn.", cap,
            )

    return report


def best_run(runs: List[dict]) -> Optional[dict]:
    scored = [r for r in runs if r.get("images_per_sec")]
    return max(scored, key=lambda r: r["images_per_sec"]) if scored else None


def merge_reports(report_dir: str) -> dict:
    """Merge every `benchmark_*.json` into one table; works without a GPU."""
    directory = Path(report_dir)
    paths = sorted(p for p in directory.glob("benchmark_*.json")
                   if p.name not in ("benchmark_comparison.json",))
    if not paths:
        raise SystemExit(f"Không thấy file benchmark_*.json nào trong {directory}")

    local_rows: List[List[object]] = []
    http_rows: List[List[object]] = []
    merged: Dict[str, List[dict]] = {"local": [], "http": []}

    for path in paths:
        report = json.loads(path.read_text(encoding="utf-8"))
        mode = report.get("mode")
        key = report.get("model_key", path.stem)
        if mode == "local":
            merged["local"].append(report)
            runs = report.get("runs", [])
            single = next((r for r in runs if r["batch_size"] == 1), None)
            best = best_run(runs)
            local_rows.append([
                key,
                report.get("params_b"),
                ",".join(report.get("sides") or []),
                single["ms_per_image"] if single else None,
                best["batch_size"] if best else None,
                best["ms_per_image"] if best else None,
                best["images_per_sec"] if best else None,
                best.get("peak_vram_mb") if best else None,
                f"{100 * (best.get('parse_ok_rate') or 0):.0f}%" if best else None,
                report.get("env", {}).get("gpu"),
            ])
        elif mode == "http":
            merged["http"].append(report)
            conc = report.get("concurrency_runs", [])
            first = conc[0] if conc else None
            best_conc = max(
                (r for r in conc if r.get("images_per_sec")),
                key=lambda r: r["images_per_sec"], default=None,
            )
            best_batch = best_run(report.get("batch_runs", []))
            http_rows.append([
                key,
                first["latency_ms"].get("p50") if first else None,
                first["latency_ms"].get("p95") if first else None,
                best_conc["concurrency"] if best_conc else None,
                best_conc["images_per_sec"] if best_conc else None,
                best_batch["batch_size"] if best_batch else None,
                best_batch["images_per_sec"] if best_batch else None,
                sum(r["n_errors"] for r in conc),
            ])

    lines = ["# So sánh hiệu năng triển khai giữa các VLM", ""]
    lines.append(
        "Số **tốc độ**, không phải độ chính xác — FA/CER/F1 lấy từ "
        "`result/model_comparison.md` (`scripts/evaluate.py`, batch=1 tuần tự)."
    )
    lines.append("")
    if local_rows:
        lines += [
            "## Local (không qua HTTP) — trần của GPU", "",
            render_table(
                ["model", "tham số (B)", "mặt", "ms/ảnh @batch1", "batch tốt nhất",
                 "ms/ảnh", "ảnh/s", "peak VRAM (MB)", "parse_ok", "GPU"],
                sorted(local_rows, key=lambda r: str(r[0])),
            ),
            "",
        ]
    if http_rows:
        lines += [
            "## HTTP (app thật) — có hàng đợi và mạng nội bộ", "",
            render_table(
                ["model", "p50 @1 luồng (ms)", "p95 @1 luồng (ms)", "đồng thời tốt nhất",
                 "ảnh/s", "batch tốt nhất", "ảnh/s (batch)", "lỗi"],
                sorted(http_rows, key=lambda r: str(r[0])),
            ),
            "",
        ]
    if not local_rows and not http_rows:
        lines.append("_Chưa có report nào đọc được._")

    markdown = "\n".join(lines)
    (directory / "benchmark_comparison.md").write_text(markdown, encoding="utf-8")
    summary = {
        "n_reports": len(paths),
        "local": local_rows,
        "http": http_rows,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    with open(directory / "benchmark_comparison.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print("\n" + markdown)
    logger.info("✅ Đã gộp %d report → %s", len(paths), directory / "benchmark_comparison.md")
    return summary


def parse_int_list(raw: str) -> List[int]:
    return [int(x) for x in raw.split(",") if x.strip()]


def parse_args() -> argparse.Namespace:
    import os

    p = argparse.ArgumentParser(description="Đo hiệu năng phục vụ model CCCD trên nhiều ảnh")
    p.add_argument("--mode", choices=("local", "http", "merge"), default="local",
                   help="local = nạp model trong process; http = bắn vào API đang chạy; "
                        "merge = gộp report đã có thành bảng so sánh")
    p.add_argument("--models", default=None,
                   help=f"[local] danh sách model cần đo, vd 'qwen,internvl'. "
                        f"Có: {','.join(sorted(REGISTRY))}. Mặc định: env MODEL_KEY hoặc qwen")
    p.add_argument("--images", nargs="+", default=["data/Front", "data/Back"],
                   help="File ảnh hoặc thư mục ảnh (truyền cả 2 mặt để đo cả 2 adapter)")
    p.add_argument("--limit", type=int, default=None, help="Chỉ lấy N ảnh đầu MỖI thư mục")
    p.add_argument("--repeat", type=int, default=1, help="Số vòng lặp trên toàn bộ tập ảnh")
    p.add_argument("--batch_sizes", default=None,
                   help="Danh sách batch cần quét, vd '1,2,4,8'. "
                        "Mặc định: local='1,2,4', http=bỏ qua")
    p.add_argument("--concurrency", default="1,2,4",
                   help="[http] số request đồng thời cần quét, vd '1,2,4'")
    p.add_argument("--url", default="http://localhost:8000", help="[http] gốc URL của API")
    p.add_argument("--models_dir", default=None,
                   help="[local] thư mục chứa snapshot base; mặc định env MODELS_DIR hoặc 'models'")
    p.add_argument("--checkpoint_dir", default=None,
                   help="[local] thư mục chứa {model_key}-cccd-lora-{front,back}; "
                        "mặc định env CHECKPOINT_DIR hoặc 'checkpoints'")
    p.add_argument("--report_dir", default="result",
                   help="Thư mục ghi report; local ghi benchmark_local_{model}.json")
    p.add_argument("--report_path", default=None,
                   help="[http] file report cụ thể; mặc định "
                        "{report_dir}/benchmark_http_{model_key}.json")
    p.add_argument("--no_merge", action="store_true",
                   help="[local] không tự gộp bảng so sánh sau khi đo xong")

    args = p.parse_args()
    default_batches = "1,2,4" if args.mode == "local" else ""
    args.batch_sizes = parse_int_list(
        args.batch_sizes if args.batch_sizes is not None else default_batches
    )
    args.concurrency = parse_int_list(args.concurrency) or [1]
    args.models = [
        m.strip() for m in (args.models or os.getenv("MODEL_KEY") or "qwen").split(",")
        if m.strip()
    ]
    unknown = [m for m in args.models if m not in REGISTRY]
    if unknown:
        p.error(f"model không có trong registry: {unknown}. Có: {sorted(REGISTRY)}")
    args.models_dir = args.models_dir or os.getenv("MODELS_DIR") or "models"
    args.checkpoint_dir = args.checkpoint_dir or os.getenv("CHECKPOINT_DIR") or "checkpoints"
    return args


def main() -> None:
    args = parse_args()

    if args.mode == "merge":
        merge_reports(args.report_dir)
        return

    if args.mode == "local":
        reports = bench_local(args)
        if reports and not args.no_merge:
            merge_reports(args.report_dir)
        return

    report = bench_http(args)
    report_path = Path(
        args.report_path
        or Path(args.report_dir) / f"benchmark_http_{report['model_key']}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("✅ Đã lưu report → %s", report_path)


if __name__ == "__main__":
    main()
