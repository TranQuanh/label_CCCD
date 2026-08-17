"""
rescore.py
==========
Chấm lại điểm từ file `*_preds.jsonl` **không cần GPU**, và hỗ trợ chạy lại chỉ
phần ảnh bị hỏng thay vì cả tập test.

Vì sao cần: `metrics.evaluate` chỉ ăn cặp (pred, gold), nên mọi thay đổi ở khâu
*parse* (không phải khâu sinh) đều chấm lại được offline — miễn là còn giữ chuỗi
thô. `evaluate.py` nay đã ghi thêm trường `raw`, các file preds sinh TRƯỚC bản
sửa đó thì không có, nên phần ảnh parse hỏng buộc phải sinh lại bằng GPU.

Ba chế độ:

    # 1) Lọc ra mini test set chỉ gồm ảnh có pred rỗng (parse hỏng / lỗi)
    python scripts/rescore.py missing \
        --preds  result/front/eval_internvl_zeroshot_front_preds.jsonl \
        --test_jsonl data/dataset/Front/test.jsonl \
        --out    /tmp/test_missing.jsonl

    # 2) Ghép preds mới (chạy trên mini set) đè lên preds cũ
    python scripts/rescore.py merge \
        --base  result/front/eval_internvl_zeroshot_front_preds.jsonl \
        --patch /tmp/eval_internvl_zeroshot_front_preds.jsonl \
        --out   result/front/eval_internvl_zeroshot_front_preds.jsonl

    # 3) Tính lại FA / CER / F1 từ preds (ưu tiên parse lại từ `raw` nếu có)
    python scripts/rescore.py rescore \
        --preds  result/front/eval_internvl_zeroshot_front_preds.jsonl \
        --report result/front/eval_internvl_zeroshot_front.json \
        --out    result/front/eval_internvl_zeroshot_front.json

Các số KHÔNG phụ thuộc parser (`latency_ms`, `peak_vram_mb`, khối `run`) được giữ
nguyên từ report cũ — chấm lại không làm thay đổi tốc độ hay VRAM của lần chạy đó.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.metrics import evaluate, safe_parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def read_jsonl(path: Path) -> List[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: List[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def key_of(record: dict) -> str:
    """Khoá ghép = TÊN FILE ảnh.

    Đường dẫn trong preds là đường tuyệt đối trên Colab
    (`/content/drive/.../cccd_front_1.png`) còn trong test.jsonl có thể chỉ là
    basename sau bước copy lên SSD — so nguyên chuỗi là trượt hết.
    """
    return Path(str(record.get("image", ""))).name


# ── Chế độ 1: lọc ảnh cần chạy lại ──────────────────────────────────────────
def cmd_missing(args: argparse.Namespace) -> None:
    preds = read_jsonl(Path(args.preds))
    test = read_jsonl(Path(args.test_jsonl))

    # Ảnh cần chạy lại = pred rỗng. Có `raw` rồi thì KHÔNG cần GPU nữa: chỉ việc
    # chạy chế độ `rescore`, nên những dòng đó bị loại khỏi danh sách.
    need = {
        key_of(p)
        for p in preds
        if not p.get("pred") and not str(p.get("raw", "")).strip()
    }
    has_raw = sum(1 for p in preds if str(p.get("raw", "")).strip())

    selected = [rec for rec in test if key_of(rec) in need]
    write_jsonl(Path(args.out), selected)

    logger.info("Tổng preds        : %d", len(preds))
    logger.info("Có sẵn `raw`      : %d  → chấm lại offline được, không cần GPU", has_raw)
    logger.info("Pred rỗng, mất raw: %d  → phải sinh lại", len(need))
    logger.info("Khớp trong test   : %d  → đã ghi %s", len(selected), args.out)
    if len(selected) != len(need):
        logger.warning(
            "⚠ %d ảnh cần chạy lại nhưng KHÔNG tìm thấy trong test_jsonl "
            "(sai --test_jsonl, hoặc lệch mặt thẻ Front/Back?)",
            len(need) - len(selected),
        )
    if not selected:
        logger.info("✅ Không có ảnh nào phải chạy lại bằng GPU.")


# ── Chế độ 2: ghép preds mới đè lên preds cũ ────────────────────────────────
def cmd_merge(args: argparse.Namespace) -> None:
    base = read_jsonl(Path(args.base))
    patch = {key_of(r): r for r in read_jsonl(Path(args.patch))}

    merged: List[dict] = []
    n_replaced = 0
    for row in base:
        new = patch.get(key_of(row))
        if new is None:
            merged.append(row)
            continue
        # Giữ nguyên `gold` của file gốc: gold đến từ dataset, không phải từ model.
        # Nếu hai file lệch gold thì mini set đã dựng từ nhãn khác → dừng, đừng lặng lẽ trộn.
        if new.get("gold") and row.get("gold") and new["gold"] != row["gold"]:
            raise SystemExit(
                f"❌ Gold lệch nhau ở {key_of(row)} — mini set dựng từ nhãn khác "
                f"với lần chạy gốc. Kiểm tra lại --test_jsonl trước khi ghép."
            )
        merged.append({**row, **{k: v for k, v in new.items() if k != "gold"}})
        n_replaced += 1

    unmatched = set(patch) - {key_of(r) for r in base}
    write_jsonl(Path(args.out), merged)

    logger.info("Dòng gốc     : %d", len(base))
    logger.info("Đã thay thế  : %d", n_replaced)
    if unmatched:
        logger.warning("⚠ %d dòng trong --patch không có trong --base, đã BỎ QUA: %s",
                       len(unmatched), sorted(unmatched)[:5])
    logger.info("💾 Đã ghi → %s", args.out)


# ── Chế độ 3: tính lại metric ───────────────────────────────────────────────
def cmd_rescore(args: argparse.Namespace) -> None:
    rows = read_jsonl(Path(args.preds))

    preds: List[dict] = []
    golds: List[dict] = []
    n_parse_ok = 0
    n_from_raw = 0
    n_errors = 0

    for row in rows:
        gold = row.get("gold") or {}
        raw = row.get("raw")
        if isinstance(raw, str) and raw.strip():
            # Có chuỗi thô → parse LẠI bằng safe_parse hiện tại. Đây chính là chỗ
            # thay đổi parser phát huy tác dụng mà không cần chạy GPU.
            if raw.startswith("<EXCEPTION>"):
                pred = {}
                n_errors += 1
            else:
                pred = safe_parse(raw)
                n_from_raw += 1
        else:
            pred = row.get("pred") or {}
        if pred:
            n_parse_ok += 1
        preds.append(pred)
        golds.append(gold)

    result = evaluate(preds, golds)
    report: Dict[str, object] = result.as_dict()

    # Các số không phụ thuộc parser: bê nguyên từ report cũ.
    if args.report:
        old = json.loads(Path(args.report).read_text(encoding="utf-8"))
        for key in ("run", "latency_ms", "peak_vram_mb"):
            if key in old:
                report[key] = old[key]
        old_fa = old.get("field_accuracy")
        old_parse = old.get("json_parse_rate")
    else:
        old_fa = old_parse = None

    report["json_parse_rate"] = round(n_parse_ok / len(rows), 4) if rows else 0.0
    report["n_errors"] = n_errors
    report["rescored"] = {
        "n_parsed_from_raw": n_from_raw,
        "n_from_stored_pred": len(rows) - n_from_raw - n_errors,
    }

    out = Path(args.out or args.preds).with_suffix(".json") if not args.out else Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    logger.info("Số ảnh            : %d  (parse lại từ raw: %d)", len(rows), n_from_raw)
    if old_parse is not None:
        logger.info("JSON parse rate   : %.2f%%  →  %.2f%%",
                    old_parse * 100, report["json_parse_rate"] * 100)
    else:
        logger.info("JSON parse rate   : %.2f%%", report["json_parse_rate"] * 100)
    if old_fa is not None:
        logger.info("Field Accuracy    : %.2f%%  →  %.2f%%  (%+.2f điểm)",
                    old_fa * 100, result.field_accuracy * 100,
                    (result.field_accuracy - old_fa) * 100)
    else:
        logger.info("Field Accuracy    : %.2f%%", result.field_accuracy * 100)
    logger.info("CER / F1          : %.4f / %.2f%%", result.cer, result.f1 * 100)
    logger.info("💾 Đã ghi → %s", out)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Chấm lại điểm từ *_preds.jsonl mà không cần GPU",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="mode", required=True)

    m = sub.add_parser("missing", help="Lọc mini test set gồm ảnh phải sinh lại")
    m.add_argument("--preds", required=True)
    m.add_argument("--test_jsonl", required=True)
    m.add_argument("--out", required=True)
    m.set_defaults(func=cmd_missing)

    g = sub.add_parser("merge", help="Ghép preds mới đè lên preds cũ")
    g.add_argument("--base", required=True)
    g.add_argument("--patch", required=True)
    g.add_argument("--out", required=True)
    g.set_defaults(func=cmd_merge)

    r = sub.add_parser("rescore", help="Tính lại FA/CER/F1 từ preds")
    r.add_argument("--preds", required=True)
    r.add_argument("--report", default=None, help="Report cũ, để lấy latency/VRAM/run")
    r.add_argument("--out", default=None, help="Mặc định ghi đè --report")
    r.set_defaults(func=cmd_rescore)

    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    if args.mode == "rescore" and not args.out and args.report:
        args.out = args.report
    args.func(args)
