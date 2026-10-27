"""Merge eval reports into one comparison table (JSON + markdown).

    python scripts/compare_models.py --report_dir result
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.cccd_schema import BACK_FIELDS, FRONT_FIELDS, SIDE_FIELD
from src.utils.console import force_utf8_output

# Must run before basicConfig: the printed table contains `Δ` and Vietnamese text.
force_utf8_output()

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DASH = "-"

# Baselines have no zero-shot/fine-tuned pair, so they get their own table.
VLM_MODES: Tuple[str, ...] = ("zero_shot", "fine_tuned")
BASELINE_MODE: str = "rule_based"

_PRIMARY_ORDER: Tuple[str, ...] = ("fine_tuned", BASELINE_MODE, "zero_shot")


def primary_report(modes: Dict[str, dict]) -> Optional[dict]:
    for mode in _PRIMARY_ORDER:
        if mode in modes:
            return modes[mode]
    return None


def is_baseline(modes: Dict[str, dict]) -> bool:
    return set(modes) == {BASELINE_MODE}


def collect_reports(report_dir: Optional[str], report_list: Optional[str]) -> List[dict]:
    """Load reports from a directory and/or a comma-separated list; each gets a `_path` key."""
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
    """Group into {model_key: {mode: report}}, keeping the newest file on a clash."""
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
    if value is None:
        return DASH
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _latency(rep: Optional[dict]) -> str:
    if not rep or "latency_ms" not in rep:
        return DASH
    lat = rep["latency_ms"]
    return f"{lat.get('p50', DASH)} / {lat.get('p95', DASH)}"


def build_main_table(grouped: Dict[str, Dict[str, dict]]) -> List[str]:
    """Main table: only VLMs, which have a zero-shot/fine-tuned pair."""
    header = (
        "| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | "
        "JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |"
    )
    sep = "|" + "---|" * 11
    rows = [header, sep]

    for key in sorted(grouped):
        if is_baseline(grouped[key]):
            continue
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


def build_baseline_table(grouped: Dict[str, Dict[str, dict]]) -> List[str]:
    """Baseline table; its columns differ because Δ FA and Trainable % do not apply."""
    keys = [key for key in sorted(grouped) if is_baseline(grouped[key])]
    if not keys:
        return []

    lines = [
        "## Baseline OCR truyền thống",
        "",
        "Không dùng `train.jsonl` ở bất kỳ khâu nào ⇒ **không có cột Δ FA**. Cùng tập "
        "test, cùng schema, cùng `metrics.evaluate`, cùng tiền xử lý ảnh 1024px như "
        "các VLM.",
        "",
        "| Baseline | Detector | Recognizer | FA | CER ↓ | micro-F1 | Trường điền được | "
        "Dòng OCR/ảnh | Latency p50/p95 (ms) | Ảnh 1024px |",
        "|" + "---|" * 10,
    ]
    for key in keys:
        rep = grouped[key][BASELINE_MODE]
        run = rep["run"]
        max_side = run.get("image_max_side")
        lines.append(
            "| {name} | {det} | {rec} | {fa} | {cer} | {f1} | {fill} | {nlines} | {lat} | {side} |".format(
                name=run.get("model_id", key),
                det=run.get("detector", DASH),
                rec=run.get("recognizer", DASH),
                fa=_fmt(rep.get("field_accuracy")),
                cer=_fmt(rep.get("cer")),
                f1=_fmt(rep.get("f1")),
                fill=_fmt(rep.get("field_fill_rate")),
                nlines=_fmt(rep.get("ocr_lines_per_image"), 1),
                lat=_latency(rep),
                side=("có" if max_side == 1024 else f"không ({max_side})"),
            )
        )
    lines.append("")
    if any(grouped[key][BASELINE_MODE]["run"].get("canonicalize") for key in keys):
        lines += [
            "> ⚠ Có dòng chạy với `--canonicalize`: parser được ép `noi_cap`/`quoc_tich` "
            "về câu mẫu. Đó là **ablation** đo phần lệch do quy ước trình bày, không "
            "phải số headline — xem `field_parser` docstring.",
            "",
        ]
    return lines


def build_overall_table(grouped: Dict[str, Dict[str, dict]]) -> List[str]:
    """Ranking of every run by FA; the only table putting VLMs and baselines side by side."""
    rows: List[Tuple[float, str]] = []
    for key in sorted(grouped):
        for mode, rep in grouped[key].items():
            run = rep["run"]
            rows.append((
                rep.get("field_accuracy") or 0.0,
                "| {name} | {mode} | {fa} | {cer} | {f1} | {lat} |".format(
                    name=run.get("model_id", key),
                    mode=mode,
                    fa=_fmt(rep.get("field_accuracy")),
                    cer=_fmt(rep.get("cer")),
                    f1=_fmt(rep.get("f1")),
                    lat=_latency(rep),
                ),
            ))
    if not rows:
        return []

    rows.sort(key=lambda item: -item[0])
    return [
        "## Xếp hạng chung (mọi lần chạy)",
        "",
        "| Model / Baseline | Chế độ | FA | CER ↓ | micro-F1 | Latency p50/p95 (ms) |",
        "|" + "---|" * 6,
        *[row for _fa, row in rows],
        "",
        "> `rule_based` = baseline OCR, **chưa từng thấy dữ liệu train**. Đặt cạnh "
        "`fine_tuned` để thấy khoảng cách, không phải để kết luận kiến trúc nào hơn.",
        "",
    ]


def build_per_field_table(grouped: Dict[str, Dict[str, dict]], fields: List[str], title: str) -> List[str]:
    """Per-field FA for one card side, using each model's primary report."""
    models = sorted(grouped)
    chosen = {m: (primary_report(grouped[m]) or {}) for m in models}
    present = [
        f for f in fields
        if any(f in chosen[m].get("per_field_accuracy", {}) for m in models)
    ]
    if not present:
        return []

    headers = [
        f"{m} ({BASELINE_MODE})" if is_baseline(grouped[m]) else m
        for m in models
    ]
    lines = [f"### {title}", ""]
    lines.append("| Trường | " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * (len(models) + 1))
    for fname in present:
        cells = [_fmt(chosen[m].get("per_field_accuracy", {}).get(fname)) for m in models]
        lines.append(f"| `{fname}` | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def build_markdown(grouped: Dict[str, Dict[str, dict]]) -> str:
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
    ]
    lines += build_baseline_table(grouped)
    lines += build_overall_table(grouped)
    lines += ["## FA theo từng trường", "",
              "Mỗi model lấy bản fine-tuned; baseline OCR lấy bản `rule_based`.", ""]
    lines += build_per_field_table(grouped, FRONT_FIELDS + [SIDE_FIELD], "Mặt trước")
    lines += build_per_field_table(grouped, BACK_FIELDS + [SIDE_FIELD], "Mặt sau")

    # Baselines only ever have `rule_based`, so they are not missing a run.
    missing = [
        f"- **{k}**: thiếu run `{mode}`"
        for k in sorted(grouped)
        if not is_baseline(grouped[k])
        for mode in VLM_MODES
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
    p = argparse.ArgumentParser(description="Gộp eval report thành bảng so sánh model")
    p.add_argument("--report_dir", default="result", help="Thư mục chứa *.json report")
    p.add_argument("--reports", default=None, help="Danh sách file report, phân tách bằng dấu phẩy")
    p.add_argument("--report_path", default="result/model_comparison.json")
    p.add_argument("--markdown_path", default="result/model_comparison.md")
    return p.parse_args()


def main() -> None:
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
                # OCR baselines only.
                "field_fill_rate": rep.get("field_fill_rate"),
                "ocr_lines_per_image": rep.get("ocr_lines_per_image"),
                "engine_config": rep.get("engine_config"),
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
    if any(not is_baseline(modes) for modes in grouped.values()):
        print("\n".join(build_main_table(grouped)))
        print()
    baseline_table = build_baseline_table(grouped)
    if baseline_table:
        print("\n".join(baseline_table))


if __name__ == "__main__":
    main()
