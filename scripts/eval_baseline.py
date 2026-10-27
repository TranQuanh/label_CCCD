"""Score the OCR baselines on the test set, with the same metrics and report shape
as the VLM branch. `mode` is `rule_based`, so there is no Δ FA column."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List

from PIL import Image
from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.baselines.field_parser import filled_ratio, parse_ocr_lines
from src.baselines.ocr_engines import OcrLine
from src.baselines.ocr_registry import (
    build_engine,
    check_available,
    preprocess_for_ocr,
    resolve,
)
from src.models.vlm_registry import SHARED_IMAGE_MAX_SIDE
from src.utils.cccd_schema import infer_side_from_filename
from src.utils.console import force_utf8_output
from src.utils.metrics import evaluate, safe_parse

# Must run before basicConfig: logging handlers capture sys.stderr at that point.
force_utf8_output()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_jsonl(path: str) -> List[dict]:
    records: List[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Đánh giá baseline OCR trên tập test CCCD")
    parser.add_argument("--test_jsonl", required=True)
    parser.add_argument("--engine", default="paddleocr",
                        help="Key trong ocr_registry: paddleocr | paddle_vietocr")
    parser.add_argument("--image_root", default=".")
    parser.add_argument("--report_path", default="result/eval_baseline.json")
    parser.add_argument(
        "--image_max_side", type=int, default=SHARED_IMAGE_MAX_SIDE,
        help=f"Cạnh dài ảnh đầu vào (mặc định {SHARED_IMAGE_MAX_SIDE} = y hệt nhánh VLM). "
             f"0 = ảnh gốc, CHỈ dùng cho ablation vì nó cho baseline lợi thế mà VLM không có.",
    )
    parser.add_argument(
        "--det_limit_side_len", type=int, default=None,
        help="Cạnh dài mà PP-OCR thu ảnh về TRƯỚC KHI detect. Bỏ trống = bám theo "
             "--image_max_side (đúng biến kiểm soát). 0 = không thu nhỏ khi detect.",
    )
    parser.add_argument("--min_conf", type=float, default=0.0,
                        help="Bỏ các hộp text có độ tin cậy thấp hơn ngưỡng")
    parser.add_argument(
        "--canonicalize", action="store_true",
        help="Bật luật chuẩn hoá noi_cap/quoc_tich theo phân bố nhãn. MẶC ĐỊNH TẮT — "
             "đây là ablation đo phần lệch do quy ước trình bày, không phải số headline.",
    )
    parser.add_argument(
        "--gpu", action="store_true",
        help="Cho nửa PaddleOCR (detection) dùng GPU. Cần bản paddlepaddle-gpu khớp "
             "CUDA; bản CPU mặc định của requirements-ocr.txt sẽ bỏ qua kèm cảnh báo.",
    )
    parser.add_argument(
        "--device", default=None,
        help="Device cho nửa VietOCR chạy trên torch (vd cuda:0 / cpu). Bỏ trống = TỰ "
             "chọn cuda:0 nếu có GPU. Không ảnh hưởng nửa PaddleOCR — dùng --gpu cho nửa đó.",
    )
    parser.add_argument("--vietocr_weights", default=None, help="Trọng số VietOCR tuỳ chọn")
    parser.add_argument("--batch_size", type=int, default=16,
                        help="Số crop dòng đưa vào VietOCR mỗi lượt")
    parser.add_argument("--limit", type=int, default=0, help="Chỉ chạy N ảnh đầu (gỡ lỗi)")

    parser.add_argument(
        "--ocr_cache", default=None,
        help="Đọc lại output OCR đã lưu thay vì chạy engine → chấm lại parser không cần GPU",
    )
    parser.add_argument(
        "--ocr_out", default=None,
        help="Nơi ghi cache OCR. Bỏ trống = <report_path>_ocr.jsonl",
    )
    parser.add_argument("--no_save_ocr", action="store_true", help="Không ghi cache OCR")
    parser.add_argument("--predictions_path", default=None,
                        help="Bỏ trống = <report_path>_preds.jsonl")
    parser.add_argument(
        "--no_save_predictions", action="store_true",
        help="Không ghi file dự đoán. Mặc định LUÔN ghi vì bootstrap CI và McNemar "
             "test cần kết quả từng ảnh, mà report chỉ có số tổng hợp.",
    )
    return parser.parse_args()


def load_ocr_cache(path: str) -> Dict[str, List[OcrLine]]:
    """Load the OCR cache keyed by file name, since stored paths may be absolute."""
    cache: Dict[str, List[OcrLine]] = {}
    for record in load_jsonl(path):
        key = Path(str(record.get("image", ""))).name
        cache[key] = [OcrLine.from_dict(item) for item in record.get("lines", [])]
    return cache


def load_previous_report(path: str) -> dict:
    """Read the report about to be overwritten; `{}` when absent or unreadable."""
    report_path = Path(path)
    if not report_path.is_file():
        return {}
    try:
        return json.loads(report_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def main() -> None:
    args = parse_args()

    # The detection limit follows the input size, otherwise `--image_max_side 0`
    # is a half ablation: crops at full resolution, detection still at 1024px.
    det_limit = (
        args.det_limit_side_len
        if args.det_limit_side_len is not None
        else args.image_max_side
    )

    # Ablations must be loud: their numbers look exactly like headline numbers.
    if args.image_max_side <= 0:
        logger.warning(
            "⚠ ABLATION full-res: ảnh KHÔNG thu nhỏ về %dpx. Đây KHÔNG phải số "
            "headline — baseline được lợi thế độ phân giải mà 3 VLM không có.",
            SHARED_IMAGE_MAX_SIDE,
        )
    if args.canonicalize:
        logger.warning(
            "⚠ ABLATION canonicalize: parser bị ép noi_cap/quoc_tich về câu mẫu "
            "theo phân bố nhãn, tức đoán trúng nhờ biết trước nhãn chứ không nhờ "
            "đọc. Đây KHÔNG phải số headline."
        )

    spec = resolve(args.engine)
    records = load_jsonl(args.test_jsonl)
    if args.limit:
        records = records[: args.limit]
    if not records:
        raise SystemExit(f"Không có record nào trong {args.test_jsonl}")

    cache = load_ocr_cache(args.ocr_cache) if args.ocr_cache else {}
    if cache:
        logger.info("📂 Đã nạp cache OCR cho %d ảnh từ %s", len(cache), args.ocr_cache)

    # Build the engine only when images actually need reading, so re-scoring the
    # parser works on machines without paddle/vietocr.
    engine = None
    missing = [rec for rec in records if Path(str(rec["image"])).name not in cache]
    if missing:
        ok, reason = check_available(spec)
        if not ok:
            raise SystemExit(f"Không chạy được baseline '{spec.key}': {reason}")
        logger.info("🔄 Đang dựng engine %s (%d/%d ảnh chưa có cache)...",
                    spec.key, len(missing), len(records))
        engine = build_engine(
            spec,
            use_gpu=args.gpu,
            device=args.device,
            min_conf=args.min_conf,
            det_limit_side_len=det_limit,
            vietocr_weights=args.vietocr_weights,
            batch_size=args.batch_size,
        )

    image_root = Path(args.image_root)
    preds: List[dict] = []
    golds: List[dict] = []
    raws: List[str] = []
    ocr_rows: List[dict] = []
    latencies_ms: List[float] = []
    ocr_ms: List[float] = []
    n_lines_total = 0
    n_parse_ok = 0
    n_errors = 0
    n_from_cache = 0
    fill_sum = 0.0

    if args.gpu:
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.reset_peak_memory_stats()
        except ImportError:
            pass

    if engine is not None and records:
        # Without a warmup the first image's model loading skews p95 latency.
        first = image_root / records[0]["image"]
        if not first.exists():
            first = Path(records[0]["image"])
        if first.exists():
            probe = Image.open(first).convert("RGB")
            preprocess_for_ocr(probe, args.image_max_side)
            engine.warmup(probe)

    logger.info("🚀 Bắt đầu chấm điểm baseline %s trên tập Test...", spec.key)
    for record in tqdm(records, desc="Đánh giá", unit="ảnh"):
        gold = safe_parse(record["conversations"][1]["value"])
        golds.append(gold)

        image_name = Path(str(record["image"])).name
        side = infer_side_from_filename(record["image"])

        try:
            started = time.perf_counter()
            lines = cache.get(image_name)
            if lines is None:
                image_path = image_root / record["image"]
                if not image_path.exists():
                    image_path = Path(record["image"])
                image = Image.open(image_path).convert("RGB")
                preprocess_for_ocr(image, args.image_max_side)
                lines = engine.read(image)  # type: ignore[union-attr]
            else:
                n_from_cache += 1
            ocr_ms.append((time.perf_counter() - started) * 1000)

            parsed = parse_ocr_lines(lines, side, canonicalize=args.canonicalize)
            latencies_ms.append((time.perf_counter() - started) * 1000)

            n_lines_total += len(lines)
            fill_sum += filled_ratio(parsed)
            if any(value for value in parsed.values()):
                n_parse_ok += 1

            preds.append(parsed)
            # `raw` stays JSON so rescore.py and notebook 05 can call safe_parse on it.
            raws.append(json.dumps(parsed, ensure_ascii=False))
            ocr_rows.append({
                "image": record["image"],
                "side": side.value,
                "lines": [line.as_dict() for line in lines],
            })

        except Exception as exc:  # noqa: BLE001
            logger.error("❌ Lỗi khi xử lý ảnh %s: %s", record["image"], exc)
            preds.append({})
            raws.append(f"<EXCEPTION> {exc}")
            ocr_rows.append({"image": record["image"], "side": side.value, "lines": []})
            n_errors += 1

    if not args.no_save_ocr and engine is not None:
        ocr_path = (
            Path(args.ocr_out)
            if args.ocr_out
            else Path(args.report_path).with_name(Path(args.report_path).stem + "_ocr.jsonl")
        )
        ocr_path.parent.mkdir(parents=True, exist_ok=True)
        with open(ocr_path, "w", encoding="utf-8") as handle:
            for row in ocr_rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        logger.info("💾 Đã ghi cache OCR (%d ảnh) → %s", len(ocr_rows), ocr_path)
        logger.info("   Chỉnh field_parser rồi chạy lại với --ocr_cache %s (không cần GPU)", ocr_path)

    if not args.no_save_predictions:
        pred_path = (
            Path(args.predictions_path)
            if args.predictions_path
            else Path(args.report_path).with_name(Path(args.report_path).stem + "_preds.jsonl")
        )
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pred_path, "w", encoding="utf-8") as handle:
            for record, pred, gold, raw in zip(records, preds, golds, raws):
                handle.write(json.dumps(
                    {"image": record["image"], "pred": pred, "gold": gold, "raw": raw},
                    ensure_ascii=False,
                ) + "\n")
        logger.info("💾 Đã ghi %d dự đoán → %s", len(preds), pred_path)

    result = evaluate(preds, golds)
    report = result.as_dict()

    engine_info = engine.describe() if engine is not None else {"engine": spec.name, "from_cache": True}
    report["run"] = {
        "model_key": spec.key,
        "model_id": spec.name,
        "family": spec.family,
        "params_b": spec.params_b or None,
        # Not zero_shot: there is no fine-tuned counterpart to compute Δ FA against.
        "mode": "rule_based",
        "adapter_dir": None,
        "image_max_side": args.image_max_side,
        "det_limit_side_len": det_limit,
        "decoding": "rule-based field parser (không sinh token)",
        "canonicalize": args.canonicalize,
        "detector": spec.detector,
        "recognizer": spec.recognizer,
        "engine_config": engine_info,
        "ocr_cache": args.ocr_cache,
        "trainable_params_pct": None,
        "train_max_length": None,
    }
    report["json_parse_rate"] = round(n_parse_ok / len(records), 4) if records else 0.0
    report["n_errors"] = n_errors
    # Separates "could not read" from "read but wrong", which need different fixes.
    report["field_fill_rate"] = round(fill_sum / len(records), 4) if records else 0.0
    report["ocr_lines_per_image"] = round(n_lines_total / len(records), 1) if records else 0.0

    if latencies_ms:
        ordered = sorted(latencies_ms)
        timing = {
            "p50": round(statistics.median(ordered), 1),
            "p95": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 1),
            "mean": round(statistics.fmean(ordered), 1),
        }
        # A cache hit skips detection+recognition, so the measured time is parser-only.
        # Like rescore.py, the parser-independent latency is carried over from the
        # report being overwritten; `latency_ms` is left out when there is none to carry,
        # rather than set to None, because consumers fall back on a missing key only.
        if n_from_cache:
            report["parser_latency_ms"] = timing
            previous = load_previous_report(args.report_path)
            if previous.get("latency_ms"):
                report["latency_ms"] = previous["latency_ms"]
                report["latency_note"] = (
                    "latency_ms giữ từ lần chạy OCR đầy đủ trước đó; parser_latency_ms "
                    "là của lần chấm lại này."
                )
            else:
                report["latency_note"] = (
                    f"{n_from_cache}/{len(records)} ảnh đọc từ --ocr_cache nên bỏ qua "
                    f"detection+recognition, và report cũ không có latency để giữ lại. "
                    f"Chạy lại KHÔNG có --ocr_cache để có latency so sánh được với VLM."
                )
        else:
            report["latency_ms"] = timing
    if ocr_ms and not n_from_cache:
        report["ocr_latency_ms"] = {"mean": round(statistics.fmean(ocr_ms), 1)}
    report["n_from_cache"] = n_from_cache

    if args.gpu:
        try:
            import torch

            if torch.cuda.is_available():
                report["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)
                # Paddle allocates VRAM through its own allocator, invisible to torch.
                report["peak_vram_note"] = (
                    "Chỉ tính phần torch cấp phát (VietOCR). PaddleOCR dùng allocator "
                    "riêng nên không nằm trong con số này."
                )
        except ImportError:
            pass

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)

    logger.info(
        "FA=%.4f | CER=%.4f | F1=%.4f | fill=%.1f%% | %.1f dòng/ảnh | p50=%sms",
        report["field_accuracy"], report["cer"], report["f1"],
        100 * report["field_fill_rate"], report["ocr_lines_per_image"],
        (report.get("latency_ms") or {}).get("p50", "-"),
    )
    if n_from_cache:
        logger.warning("⚠ %d/%d ảnh đọc từ cache OCR: %s",
                       n_from_cache, len(records), report["latency_note"])
    logger.info("✅ Đã lưu báo cáo → %s", report_path)


if __name__ == "__main__":
    main()
