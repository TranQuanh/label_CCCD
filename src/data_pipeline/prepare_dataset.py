"""
prepare_dataset.py
==================
Bước 3: chia dữ liệu đã DUYỆT TAY 100% thành Train/Val/Test (80/10/10) và
augment CHỈ trên tập Train.
[ĐÃ SỬA] Mỗi file ảnh (front/back) là một cá thể độc lập, không gom nhóm.
"""

from __future__ import annotations

import argparse
import json
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from PIL import Image, ImageEnhance, ImageFilter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def group_key(image_path: str) -> str:
    """Lấy nguyên tên gốc của file ảnh làm key, mỗi ảnh 1 nhóm riêng."""
    return Path(image_path).stem

def load_reviewed(input_path: Path, require_reviewed: bool) -> List[dict]:
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
        logger.warning("Bỏ qua %d record CHƯA duyệt tay", skipped)
    logger.info("Đã load %d record hợp lệ", len(records))
    return records

def split_groups(
    records: List[dict], ratios: Tuple[float, float, float], seed: int
) -> Dict[str, List[dict]]:
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
        logger.info("[%s] %d ảnh", name, len(split[name]))
    return split

def augment_image(img: Image.Image, rng: random.Random) -> Image.Image:
    out = img.rotate(rng.uniform(-3, 3), expand=False, fillcolor=(255, 255, 255))
    out = ImageEnhance.Brightness(out).enhance(rng.uniform(0.85, 1.15))
    out = ImageEnhance.Contrast(out).enhance(rng.uniform(0.85, 1.15))
    out = ImageEnhance.Sharpness(out).enhance(rng.uniform(0.8, 1.4))
    if rng.random() < 0.3:
        out = out.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.3, 0.8)))
    return out

def make_clean_record(rec: dict, image_path: str) -> dict:
    return {
        "image": str(image_path).replace("\\", "/"),
        "conversations": rec["conversations"],
    }

def augment_train(
    train_records: List[dict], aug_dir: Path, image_root: Path, n_aug: int, seed: int
) -> List[dict]:
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

    logger.info("[train] augment: %d gốc → %d sau augment", len(train_records), len(out))
    return out

def write_jsonl(records: List[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    logger.info("Đã ghi %d record → %s", len(records), path)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split 80/10/10 + augment train-only")
    parser.add_argument("--input", required=True)
    parser.add_argument("--out_dir", default="data/dataset")
    parser.add_argument("--aug_dir", default="data/aug")
    parser.add_argument("--image_root", default=".")
    parser.add_argument("--n_aug", type=int, default=2)
    parser.add_argument("--ratios", default="0.8,0.1,0.1")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--allow_unreviewed", action="store_true")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    ratios = tuple(float(x) for x in args.ratios.split(","))
    image_root = Path(args.image_root)

    records = load_reviewed(Path(args.input), require_reviewed=not args.allow_unreviewed)
    if not records:
        logger.error("Không có record nào để xử lý!")
        return

    split = split_groups(records, ratios, args.seed)
    out_dir = Path(args.out_dir)

    for name in ("val", "test"):
        clean = [make_clean_record(r, r["image"]) for r in split[name]]
        write_jsonl(clean, out_dir / f"{name}.jsonl")

    train_clean = [make_clean_record(r, r["image"]) for r in split["train"]]
    train_aug = augment_train(train_clean, Path(args.aug_dir), image_root, args.n_aug, args.seed)
    write_jsonl(train_aug, out_dir / "train.jsonl")
    logger.info("✅ Hoàn tất. Dataset tại: %s/", out_dir)

if __name__ == "__main__":
    main()