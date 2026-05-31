"""
train.py
========
Fine-tune QLoRA cho Qwen3-VL-8B trên dataset CCCD bằng Hugging Face `Trainer`.

Thiết kế cho Colab T4 15GB:
  - Model 4-bit + gradient checkpointing (xem src/models/lora_setup.py).
  - batch_size nhỏ + gradient_accumulation lớn để có effective batch hợp lý.
  - Đánh giá (eval loss) trên tập Val SAU MỖI EPOCH, lưu adapter tốt nhất.
  - Chỉ lưu LoRA adapter (vài chục MB), không lưu base 7B.

Data collator tự viết: dựng messages (image + prompt) → apply_chat_template →
process_vision_info, rồi MASK phần prompt (label = -100) để loss chỉ tính trên
câu trả lời JSON của assistant.

Cách dùng:
  python scripts/train.py \
      --train_jsonl data/dataset/train.jsonl \
      --val_jsonl   data/dataset/val.jsonl \
      --image_root  . \
      --output_dir  checkpoints/qwen3vl-cccd-lora \
      --epochs 3 --batch_size 1 --grad_accum 8 --lr 1e-4
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import torch
from PIL import Image
from torch.utils.data import Dataset

# Cho phép chạy trực tiếp `python scripts/train.py`: thêm repo root vào sys.path
# (mặc định Python chỉ đưa thư mục scripts/ vào path nên `import src` sẽ lỗi).
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.lora_setup import LoraSettings, load_model_4bit  # noqa: E402
from src.utils.cccd_schema import SYSTEM_PROMPT  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

IGNORE_INDEX = -100  # token bị mask khỏi loss


class CCCDDataset(Dataset):
    """
    Dataset đọc JSONL format Qwen-VL.

    Mỗi item giữ nguyên record {image, conversations}; việc tokenize/đóng ảnh
    để collator lo (để tận dụng padding động theo batch).
    """

    def __init__(self, jsonl_path: str, image_root: str) -> None:
        self.image_root = Path(image_root)
        self.records: List[dict] = []
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self.records.append(json.loads(line))
        logger.info("Loaded %d ví dụ từ %s", len(self.records), jsonl_path)

    def __len__(self) -> int:
        return len(self.records)

    def __getitem__(self, idx: int) -> dict:
        return self.records[idx]

    def resolve_image(self, image_ref: str) -> str:
        """Resolve đường dẫn ảnh tương đối theo image_root (fallback path gốc)."""
        p = self.image_root / image_ref
        return str(p if p.exists() else image_ref)


@dataclass
class QwenVLCollator:
    """
    Collator: chuyển batch record → tensor input cho Qwen2-VL, mask prompt.

    Attributes:
        processor: AutoProcessor của Qwen2-VL.
        dataset: để resolve đường dẫn ảnh.
        max_length: cắt chuỗi quá dài (an toàn VRAM).
    """

    processor: Any
    dataset: CCCDDataset
    max_length: int = 1536

    def _build_messages(self, rec: dict, image: Image.Image) -> List[dict]:
        """Dựng messages 3-turn (system + human + gpt) từ record."""
        human = rec["conversations"][0]["value"].replace("<image>", "").strip()
        gpt = rec["conversations"][1]["value"]
        return [
            {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": human},
                ],
            },
            {"role": "assistant", "content": [{"type": "text", "text": gpt}]},
        ]

    def __call__(self, features: List[dict]) -> Dict[str, torch.Tensor]:
        """Tokenize + pad + tạo labels mask cho cả batch."""
        images: List[Image.Image] = []
        full_texts: List[str] = []
        prompt_texts: List[str] = []

        for rec in features:
            img = Image.open(self.dataset.resolve_image(rec["image"])).convert("RGB")
            images.append(img)
            messages = self._build_messages(rec, img)
            # Chuỗi đầy đủ (có câu trả lời) để học.
            full_texts.append(
                self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            )
            # Chuỗi chỉ-prompt (đến lượt assistant) để biết phần cần MASK.
            prompt_texts.append(
                self.processor.apply_chat_template(
                    messages[:-1], tokenize=False, add_generation_prompt=True
                )
            )

        batch = self.processor(
            text=full_texts,
            images=images,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )

        labels = batch["input_ids"].clone()
        # Mask padding.
        pad_id = self.processor.tokenizer.pad_token_id
        labels[labels == pad_id] = IGNORE_INDEX
        # Mask token ảnh (không phải mục tiêu sinh).
        for tok_attr in ("image_token_id", "video_token_id"):
            tok_id = getattr(self.processor.tokenizer, tok_attr, None)
            if tok_id is not None:
                labels[labels == tok_id] = IGNORE_INDEX

        # Mask phần prompt theo độ dài chuỗi prompt từng ví dụ.
        prompt_lens = [
            self.processor(text=[pt], images=[im], return_tensors="pt")["input_ids"].shape[1]
            for pt, im in zip(prompt_texts, images)
        ]
        for i, plen in enumerate(prompt_lens):
            labels[i, :plen] = IGNORE_INDEX

        batch["labels"] = labels
        return batch


def build_training_args(args: argparse.Namespace):
    """Dựng TrainingArguments; eval+save mỗi epoch, giữ adapter tốt nhất."""
    from transformers import TrainingArguments

    return TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        weight_decay=0.01,
        logging_steps=10,
        eval_strategy="epoch",
        save_strategy="epoch",
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=(args.compute_dtype == "bfloat16"),
        fp16=(args.compute_dtype == "float16"),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",  # optimizer 8-bit để tiết kiệm VRAM trên T4
        report_to="none",
        remove_unused_columns=False,  # bắt buộc: ta tự quản input đa phương thức
        dataloader_pin_memory=False,
    )


def parse_args() -> argparse.Namespace:
    """Định nghĩa & parse CLI args."""
    p = argparse.ArgumentParser(description="QLoRA fine-tune Qwen2-VL cho CCCD")
    # Dữ liệu
    p.add_argument("--train_jsonl", required=True)
    p.add_argument("--val_jsonl", required=True)
    p.add_argument("--image_root", default=".")
    p.add_argument("--output_dir", default="checkpoints/qwen3vl-cccd-lora")
    # Model / LoRA
    p.add_argument("--model_name", default="Qwen/Qwen3-VL-8B-Instruct",
                   help="HF ID hoặc path local đã tải sẵn (default: Qwen/Qwen3-VL-8B-Instruct)")
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--lora_dropout", type=float, default=0.05)
    p.add_argument("--compute_dtype", default="float16", choices=["float16", "bfloat16"])
    # Train
    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--batch_size", type=int, default=1)
    p.add_argument("--grad_accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--max_length", type=int, default=1536)
    return p.parse_args()


def main() -> None:
    """Entry point: load model 4-bit + LoRA, train, lưu adapter."""
    from transformers import Trainer

    args = parse_args()
    settings = LoraSettings(
        model_name=args.model_name,
        lora_r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        compute_dtype=args.compute_dtype,
    )
    model, processor = load_model_4bit(settings, use_gradient_checkpointing=True)

    train_ds = CCCDDataset(args.train_jsonl, args.image_root)
    val_ds = CCCDDataset(args.val_jsonl, args.image_root)
    collator = QwenVLCollator(processor=processor, dataset=train_ds, max_length=args.max_length)

    trainer = Trainer(
        model=model,
        args=build_training_args(args),
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
    )

    logger.info("🚀 Bắt đầu fine-tune QLoRA...")
    trainer.train()

    # Chỉ lưu LoRA adapter + processor (vài chục MB).
    out = Path(args.output_dir)
    model.save_pretrained(out)
    processor.save_pretrained(out)
    logger.info("✅ Đã lưu adapter + processor → %s", out)


if __name__ == "__main__":
    main()
