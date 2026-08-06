"""
compare_models.py
=================
Gộp nhiều file `eval_report.json` (do evaluate.py sinh) thành một bảng so sánh
fine-tune-vs-fine-tune giữa các kiến trúc VLM.

Tự gom nhóm theo `run.model_key` và tách theo `run.mode` (`zero_shot` /
`fine_tuned`) nên chỉ cần trỏ vào thư mục chứa report, không phải liệt kê tay:

    python scripts/compare_models.py --report_dir result

Xuất 2 file: `result/model_comparison.json` và `result/model_comparison.md`
(bảng chính + bảng FA theo từng trường, tách mặt trước / mặt sau).

Lưu ý khi đọc số: tập test chỉ ~10% dữ liệu nên chênh lệch vài phần trăm FA có thể
là nhiễu. Cột Δ FA (fine-tuned − zero-shot) đáng tin hơn cột FA tuyệt đối vì nó
ghép cặp trên cùng model. Xem VLM_COMPARISON_PLAN.md mục 9 về bootstrap CI /
McNemar test trước khi kết luận model nào thắng.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.cccd_schema import BACK_FIELDS, FRONT_FIELDS, SIDE_FIELD

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DASH = "-"


def collect_reports(report_dir: Optional[str], report_list: Optional[str]) -> List[dict]:
    """
    Nạp các report, bỏ qua file không phải output của evaluate.py.

    Args:
        report_dir: thư mục chứa `*.json`.
        report_list: danh sách đường dẫn phân tách bằng dấu phẩy.

    Returns:
        List report dict, mỗi phần tử thêm khóa `_path`.
    """
    paths: List[Path] = []
    if report_list:
        paths += [Path(p.strip()) for p in report_list.split(",") if p.strip()]
    if report_dir:
        paths += sorted(Path(report_dir).glob("*.json"))

    reports: List[dict] = []
    seen: set = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not path.exists():
            logger.warning("Bỏ qua (không tồn tại): %s", path)
            continue
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "field_accuracy" not in data:
            logger.info("Bỏ qua (không phải eval report): %s", path)
            continue
        if "run" not in data:
            logger.warning(
                "%s thiếu khối 'run' (sinh bởi evaluate.py bản cũ) → coi là fine_tuned/unknown",
                path,
            )
            data["run"] = {"model_key": path.stem, "mode": "fine_tuned"}
        data["_path"] = str(path)
        reports.append(data)
    return reports


def group_by_model(reports: List[dict]) -> Dict[str, Dict[str, dict]]:
    """Gom thành {model_key: {mode: report}}; trùng thì giữ file mới nhất."""
    grouped: Dict[str, Dict[str, dict]] = {}
    for rep in reports:
        key = rep["run"].get("model_key", "unknown")
        mode = rep["run"].get("mode", "fine_tuned")
        slot = grouped.setdefault(key, {})
        if mode in slot:
            older, newer = slot[mode], rep
            if Path(newer["_path"]).stat().st_mtime < Path(older["_path"]).stat().st_mtime:
                older, newer = newer, older
            logger.warning(
                "Trùng %s/%s: dùng %s, bỏ %s", key, mode, newer["_path"], older["_path"]
            )
            slot[mode] = newer
        else:
            slot[mode] = rep
    return grouped


def _fmt(value: object, digits: int = 4) -> str:
    """Format số cho bảng markdown; None → '-'."""
    if value is None:
        return DASH
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _latency(rep: Optional[dict]) -> str:
    """Chuỗi 'p50 / p95' từ report."""
    if not rep or "latency_ms" not in rep:
        return DASH
    lat = rep["latency_ms"]
    return f"{lat.get('p50', DASH)} / {lat.get('p95', DASH)}"


def build_main_table(grouped: Dict[str, Dict[str, dict]]) -> List[str]:
    """Bảng chính (mục 8.1 của plan doc)."""
    header = (
        "| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | "
        "JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |"
    )
    sep = "|" + "---|" * 11
    rows = [header, sep]

    for key in sorted(grouped):
        zs = grouped[key].get("zero_shot")
        ft = grouped[key].get("fine_tuned")
        primary = ft or zs
        run = primary["run"]

        fa_zs = zs["field_accuracy"] if zs else None
        fa_ft = ft["field_accuracy"] if ft else None
        delta = (fa_ft - fa_zs) if (fa_zs is not None and fa_ft is not None) else None

        rows.append(
            "| {name} | {params} | {fa_zs} | {fa_ft} | {delta} | {cer} | {f1} | "
            "{parse} | {vram} | {lat} | {trainable} |".format(
                name=run.get("model_id", key),
                params=_fmt(run.get("params_b") or None, 1),
                fa_zs=_fmt(fa_zs),
                fa_ft=_fmt(fa_ft),
                delta=(f"{delta:+.4f}" if delta is not None else DASH),
                cer=_fmt(primary.get("cer")),
                f1=_fmt(primary.get("f1")),
                parse=_fmt(primary.get("json_parse_rate")),
                vram=_fmt(primary.get("peak_vram_mb"), 1),
                lat=_latency(primary),
                trainable=_fmt(run.get("trainable_params_pct"), 4),
            )
        )
    return rows


def build_per_field_table(grouped: Dict[str, Dict[str, dict]], fields: List[str], title: str) -> List[str]:
    """Bảng FA theo từng trường cho một mặt thẻ (mục 8.2 của plan doc)."""
    models = sorted(grouped)
    present = [
        f for f in fields
        if any(f in (grouped[m].get("fine_tuned") or {}).get("per_field_accuracy", {}) for m in models)
    ]
    if not present:
        return []

    lines = [f"### {title}", ""]
    lines.append("| Trường | " + " | ".join(models) + " |")
    lines.append("|" + "---|" * (len(models) + 1))
    for fname in present:
        cells = []
        for m in models:
            ft = grouped[m].get("fine_tuned")
            acc = (ft or {}).get("per_field_accuracy", {}).get(fname)
            cells.append(_fmt(acc))
        lines.append(f"| `{fname}` | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def build_markdown(grouped: Dict[str, Dict[str, dict]]) -> str:
    """Dựng toàn bộ file markdown báo cáo."""
    lines = [
        "# So sánh VLM fine-tune — trích xuất CCCD",
        "",
        "Sinh tự động bởi `scripts/compare_models.py`. Mọi dòng dùng **cùng tập test, "
        "cùng prompt/schema, cùng `metrics.evaluate`, cùng greedy decoding**.",
        "",
        "## Bảng chính",
        "",
    ]
    lines += build_main_table(grouped)
    lines += [
        "",
        "> Δ FA = FA(fine-tuned) − FA(zero-shot): đóng góp thuần của QLoRA cho kiến trúc đó.",
        "> Các cột CER / F1 / parse / VRAM / latency lấy từ dòng fine-tuned (nếu có).",
        "",
        "## FA theo từng trường (fine-tuned)",
        "",
    ]
    lines += build_per_field_table(grouped, FRONT_FIELDS + [SIDE_FIELD], "Mặt trước")
    lines += build_per_field_table(grouped, BACK_FIELDS + [SIDE_FIELD], "Mặt sau")

    missing = [
        f"- **{k}**: thiếu run `{mode}`"
        for k in sorted(grouped)
        for mode in ("zero_shot", "fine_tuned")
        if mode not in grouped[k]
    ]
    if missing:
        lines += ["## Còn thiếu", ""] + missing + [""]

    lines += [
        "## Trước khi kết luận",
        "",
        "Tập test ~10% dữ liệu ⇒ chênh lệch vài % FA có thể là nhiễu. Cần ≥2 seed, "
        "bootstrap CI 95% cho FA, và McNemar test trên exact-match từng trường khi so "
        "từng cặp model (VLM_COMPARISON_PLAN.md mục 9).",
        "",
    ]
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    p = argparse.ArgumentParser(description="Gộp eval report thành bảng so sánh model")
    p.add_argument("--report_dir", default="result", help="Thư mục chứa *.json report")
    p.add_argument("--reports", default=None, help="Danh sách file report, phân tách bằng dấu phẩy")
    p.add_argument("--report_path", default="result/model_comparison.json")
    p.add_argument("--markdown_path", default="result/model_comparison.md")
    return p.parse_args()


def main() -> None:
    """Entry point: nạp report → gom nhóm → xuất JSON + markdown."""
    args = parse_args()

    reports = collect_reports(args.report_dir, args.reports)
    if not reports:
        raise SystemExit(
            f"Không tìm thấy eval report nào trong '{args.report_dir}'. "
            f"Chạy scripts/evaluate.py trước."
        )
    grouped = group_by_model(reports)
    logger.info(
        "Đã nạp %d report cho %d model: %s",
        len(reports), len(grouped), ", ".join(sorted(grouped)),
    )

    summary = {
        key: {
            mode: {
                "field_accuracy": rep["field_accuracy"],
                "cer": rep["cer"],
                "f1": rep["f1"],
                "precision": rep["precision"],
                "recall": rep["recall"],
                "json_parse_rate": rep.get("json_parse_rate"),
                "peak_vram_mb": rep.get("peak_vram_mb"),
                "latency_ms": rep.get("latency_ms"),
                "per_field_accuracy": rep.get("per_field_accuracy", {}),
                "run": rep["run"],
                "source": rep["_path"],
            }
            for mode, rep in modes.items()
        }
        for key, modes in grouped.items()
    }
    for key, modes in grouped.items():
        zs, ft = modes.get("zero_shot"), modes.get("fine_tuned")
        if zs and ft:
            summary[key]["delta_fa"] = round(ft["field_accuracy"] - zs["field_accuracy"], 4)

    out_json = Path(args.report_path)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    out_md = Path(args.markdown_path)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(build_markdown(grouped))

    logger.info("✅ Đã lưu %s và %s", out_json, out_md)
    print()
    print("\n".join(build_main_table(grouped)))
    print()


if __name__ == "__main__":
    main()
