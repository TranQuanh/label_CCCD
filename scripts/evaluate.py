"""
evaluate.py
===========
Chạy model (base + LoRA adapter) trên tập Test rồi tính FA / CER / F1.

Đọc test.jsonl (format Qwen-VL), với mỗi ví dụ:
  - gold = JSON trong turn 'gpt'.
  - pred = JSON model sinh ra từ ảnh + prompt theo mặt thẻ.
Sau đó gọi src.utils.metrics.evaluate và in báo cáo + lưu eval_report.json.

Cách dùng:
  python scripts/evaluate.py \
      --test_jsonl data/dataset/test.jsonl \
      --adapter_dir checkpoints/qwen3vl-cccd-lora \
      --image_root . --report_path result/eval_report.json
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import List

from PIL import Image
from tqdm import tqdm

# Cho phép chạy trực tiếp `python scripts/evaluate.py`: thêm repo root vào sys.path.
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.cccd_schema import CardSide, infer_side_from_filename  # noqa: E402
from src.utils.metrics import evaluate, safe_parse  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_test(test_jsonl: str) -> List[dict]:
    """Đọc test.jsonl → list record."""
    records: List[dict] = []
    with open(test_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    p = argparse.ArgumentParser(description="Đánh giá model CCCD trên tập test")
    p.add_argument("--test_jsonl", required=True)
    p.add_argument("--base_model", default="Qwen/Qwen3-VL-8B-Instruct",
                   help="Base khớp với lúc fine-tune (default: Qwen/Qwen3-VL-8B-Instruct)")
    p.add_argument("--adapter_dir", default="checkpoints/qwen3vl-cccd-lora")
    p.add_argument("--image_root", default=".")
    p.add_argument("--report_path", default="result/eval_report.json")
    p.add_argument("--max_new_tokens", type=int, default=512)
    return p.parse_args()


def main() -> None:
    """Entry point: load model, infer test set, tính & lưu metric."""
    # Tái dùng đúng pipeline load + inference của API (4-bit + adapter).
    from app.main import load_inference_model, run_inference, STATE

    args = parse_args()
    STATE["model"], STATE["processor"] = load_inference_model(args.base_model, args.adapter_dir)

    records = load_test(args.test_jsonl)
    image_root = Path(args.image_root)
    preds: List[dict] = []
    golds: List[dict] = []

    for rec in tqdm(records, desc="eval", unit="img"):
        gold = safe_parse(rec["conversations"][1]["value"])
        golds.append(gold)

        img_path = image_root / rec["image"]
        if not img_path.exists():
            img_path = Path(rec["image"])
        side = infer_side_from_filename(rec["image"])
        try:
            image = Image.open(img_path).convert("RGB")
            raw = run_inference(image, side if side != CardSide.UNKNOWN else CardSide.UNKNOWN)
            preds.append(safe_parse(raw))
        except Exception as exc:  # noqa: BLE001
            logger.error("Lỗi %s: %s", rec["image"], exc)
            preds.append({})  # tính là sai toàn bộ trường

    result = evaluate(preds, golds)
    report = result.as_dict()
    logger.info("\n%s", json.dumps(report, ensure_ascii=False, indent=2))

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("✅ Đã lưu báo cáo → %s", report_path)


if __name__ == "__main__":
    main()
