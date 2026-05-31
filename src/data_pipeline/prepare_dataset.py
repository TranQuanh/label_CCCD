"""
prepare_dataset.py
==================
Bước 3: chia dữ liệu đã DUYỆT TAY 100% thành Train/Val/Test (80/10/10) và
augment CHỈ trên tập Train (chống data leakage).

Điểm quan trọng về chống leakage:
  1. Chia theo NHÓM (group) = mã thẻ gốc, để mặt trước & mặt sau của CÙNG 1
     người không bị tách sang 2 tập khác nhau (tránh "nhìn lén" thông tin).
  2. Augment (xoay nhẹ, đổi sáng/tương phản, blur, nhiễu) chỉ sinh ảnh mới cho
     TẬP TRAIN; Val/Test giữ nguyên ảnh gốc để đánh giá trung thực.

Input : JSONL đã duyệt (mọi record có _meta.reviewed == True).
Output: train.jsonl / val.jsonl / test.jsonl theo format Qwen-VL
        (đã loại bỏ khối _meta, chỉ giữ image + conversations).

Cách dùng:
  python -m src.data_pipeline.prepare_dataset \
      --input data/reviewed/raw_draft.jsonl \
      --out_dir data/dataset \
      --aug_dir data/aug --n_aug 2 --seed 42
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageEnhance, ImageFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Token phân biệt mặt thẻ — strip để lấy "group id" của cùng 1 thẻ.
_SIDE_TOKENS = re.compile(r"(front|back|truoc|sau|_mt|_ms|mattruoc|matsau)", re.IGNORECASE)


def group_key(image_path: str) -> str:
    """
    Suy ra khóa nhóm (định danh 1 thẻ) từ tên ảnh bằng cách bỏ token mặt thẻ.

    Ví dụ: 'cccd_001_front.jpg' & 'cccd_001_back.jpg' → cùng group 'cccd_001'.
    """
    stem = Path(image_path).stem
    return _SIDE_TOKENS.sub("", stem).strip("_-").lower()


def load_reviewed(input_path: Path, require_reviewed: bool) -> List[dict]:
    """
    Đọc JSONL, (tùy chọn) chỉ giữ record đã duyệt tay.

    Args:
        input_path: File JSONL nguồn.
        require_reviewed: True → bỏ qua record chưa reviewed và cảnh báo.

    Returns:
        Danh sách record hợp lệ.
    """
    records: List[dict] = []
    skipped = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if require_reviewed and not rec.get("_meta", {}).get("reviewed", False):
                skipped += 1
                continue
            records.append(rec)
    if skipped:
        logger.warning("Bỏ qua %d record CHƯA duyệt tay (dùng --allow_unreviewed để giữ)", skipped)
    logger.info("Đã load %d record hợp lệ", len(records))
    return records


def split_groups(
    records: List[dict], ratios: Tuple[float, float, float], seed: int
) -> Dict[str, List[dict]]:
    """
    Chia record theo nhóm thẻ thành train/val/test.

    Args:
        records: Toàn bộ record.
        ratios: (train, val, test) — tổng = 1.0.
        seed: Seed cố định để tái lập.

    Returns:
        dict {"train": [...], "val": [...], "test": [...]}.
    """
    assert abs(sum(ratios) - 1.0) < 1e-6, "Tỷ lệ split phải cộng = 1.0"

    groups: Dict[str, List[dict]] = defaultdict(list)
    for rec in records:
        groups[group_key(rec["image"])].append(rec)

    keys = sorted(groups.keys())
    random.Random(seed).shuffle(keys)

    n = len(keys)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    buckets = {
        "train": keys[:n_train],
        "val": keys[n_train : n_train + n_val],
        "test": keys[n_train + n_val :],
    }
    split: Dict[str, List[dict]] = {}
    for name, gkeys in buckets.items():
        split[name] = [rec for k in gkeys for rec in groups[k]]
        logger.info("[%s] %d nhóm → %d ảnh", name, len(gkeys), len(split[name]))
    return split


def augment_image(img: Image.Image, rng: random.Random) -> Image.Image:
    """
    Sinh 1 biến thể augment NHẸ (giữ chữ vẫn đọc được).

    Áp dụng ngẫu nhiên: xoay ±3°, đổi sáng/tương phản, blur nhẹ.
    KHÔNG lật ngang/dọc (chữ trên thẻ sẽ ngược → vô nghĩa với OCR).
    """
    out = img.rotate(rng.uniform(-3, 3), expand=False, fillcolor=(255, 255, 255))
    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.85, 1.15))
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(0.85, 1.15))
    out = ImageEnhance.Sharpness(out).enhance(rng.uniform(0.8, 1.4))
    if rng.random() < 0.3:
        out = out.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.8)))
    return out


def make_clean_record(rec: dict, image_path: str) -> dict:
    """Tạo record CHUẨN Qwen-VL (bỏ _meta), trỏ tới image_path cho trước."""
    return {
        "image": str(image_path).replace("\\", "/"),
        "conversations": rec["conversations"],
    }


def augment_train(
    train_records: List[dict], aug_dir: Path, image_root: Path, n_aug: int, seed: int
) -> List[dict]:
    """
    Sinh ảnh augment cho tập train; trả về danh sách record (gốc + augment).

    Args:
        train_records: Record train (đã clean schema phía ngoài).
        aug_dir: Thư mục lưu ảnh augment.
        image_root: Gốc để resolve đường dẫn ảnh tương đối.
        n_aug: Số biến thể augment mỗi ảnh (0 = không augment).
        seed: Seed tái lập.

    Returns:
        Danh sách record train mở rộng.
    """
    if n_aug <= 0:
        return train_records

    aug_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    out: List[dict] = list(train_records)

    for rec in train_records:
        src = (image_root / rec["image"])
        if not src.exists():
            src = Path(rec["image"])
        if not src.exists():
            logger.warning("Bỏ augment, không thấy ảnh: %s", rec["image"])
            continue
        try:
            base = Image.open(src).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bỏ augment %s: %s", src.name, exc)
            continue

        for i in range(n_aug):
            aug_img = augment_image(base, rng)
            aug_name = f"{src.stem}_aug{i}{src.suffix}"
            aug_path = aug_dir / aug_name
            aug_img.save(aug_path, quality=92)
            out.append(make_clean_record(rec, aug_path))

    logger.info("[train] augment: %d gốc → %d sau augment (n_aug=%d)", len(train_records), len(out), n_aug)
    return out


def write_jsonl(records: List[dict], path: Path) -> None:
    """Ghi danh sách record ra file JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("Đã ghi %d record → %s", len(records), path)


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
    parser = argparse.ArgumentParser(description="Split 80/10/10 + augment train-only")
    parser.add_argument("--input", required=True, help="JSONL đã duyệt tay")
    parser.add_argument("--out_dir", default="data/dataset", help="Nơi lưu train/val/test.jsonl")
    parser.add_argument("--aug_dir", default="data/aug", help="Nơi lưu ảnh augment")
    parser.add_argument("--image_root", default=".", help="Gốc resolve đường dẫn ảnh")
    parser.add_argument("--n_aug", type=int, default=2, help="Số biến thể augment/ảnh train")
    parser.add_argument("--ratios", default="0.8,0.1,0.1", help="train,val,test")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--allow_unreviewed", action="store_true",
        help="Cho phép cả record chưa duyệt tay (mặc định loại bỏ)",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point CLI."""
    args = parse_args()
    ratios = tuple(float(x) for x in args.ratios.split(","))  # type: ignore[assignment]
    image_root = Path(args.image_root)

    records = load_reviewed(Path(args.input), require_reviewed=not args.allow_unreviewed)
    if not records:
        logger.error("Không có record nào để xử lý!")
        return

    split = split_groups(records, ratios, args.seed)  # type: ignore[arg-type]
    out_dir = Path(args.out_dir)

    # Val/Test: clean schema, KHÔNG augment.
    for name in ("val", "test"):
        clean = [make_clean_record(r, r["image"]) for r in split[name]]
        write_jsonl(clean, out_dir / f"{name}.jsonl")

    # Train: clean schema rồi augment.
    train_clean = [make_clean_record(r, r["image"]) for r in split["train"]]
    train_aug = augment_train(train_clean, Path(args.aug_dir), image_root, args.n_aug, args.seed)
    write_jsonl(train_aug, out_dir / "train.jsonl")

    logger.info("✅ Hoàn tất. Dataset tại: %s/", out_dir)


if __name__ == "__main__":
    main()
