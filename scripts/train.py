"""
train.py
========
Fine-tune QLoRA cho các VLM trong bộ so sánh (Qwen2.5-VL anchor, InternVL3.5-2B,
Llama-3.2-11B-Vision) trên dataset CCCD.

Cùng một đường code, cùng siêu tham số, chỉ khác base model — đó là điều kiện cần
để so sánh công bằng (xem VLM_COMPARISON_PLAN.md mục 3). Mọi thứ riêng theo họ model
(tên module vision, kwarg processor, max_length) đều lấy từ
[src/models/vlm_registry.py](../src/models/vlm_registry.py), không hardcode ở đây.

Đã fix triệt để lỗi Loss 0.0 (do tràn ảnh) và Loss 6.38 (do mất Mask); hai chốt
an toàn ở collator giữ cho hai lỗi đó không quay lại khi đổi base model.
"""

from __future__ import annotations

import argparse
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import torch
from PIL import Image
from torch.utils.data import Dataset

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.lora_setup import LoraSettings, load_model_4bit, trainable_params_pct
from src.models.vlm_registry import (
    SHARED_IMAGE_MAX_SIDE,
    VLMSpec,
    check_available,
    images_arg,
    preprocess_image,
    resolve,
)
from src.utils.cccd_schema import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

IGNORE_INDEX = -100

class CCCDDataset(Dataset):
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
        p = self.image_root / image_ref
        return str(p if p.exists() else image_ref)

@dataclass
class VLMCollator:
    """
    Collator dùng chung cho mọi họ VLM trong bộ so sánh.

    Hai bất biến về tính đúng của loss (đều là bug đã phải sửa — giữ nguyên):
      1. Ảnh được thu nhỏ về 1024px trước khi tokenize để token ảnh không tràn
         `max_length` nuốt mất phần JSON đáp án.
      2. Toàn bộ prompt + image/pad token bị mask `-100`, loss chỉ tính trên phần
         JSON của assistant.
    """

    processor: Any
    dataset: CCCDDataset
    spec: VLMSpec
    max_length: int = 1536
    _warned_truncate: bool = field(default=False, repr=False)

    def _build_messages(self, rec: dict, image: Image.Image) -> List[dict]:
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
        images: List[Image.Image] = []
        full_texts: List[str] = []
        prompt_texts: List[str] = []

        for rec in features:
            img = Image.open(self.dataset.resolve_image(rec["image"])).convert("RGB")

            # --- TỐI ƯU CỐT LÕI: THU NHỎ ẢNH ĐỂ TRÁNH TRÀN TOKEN ---
            # Ngăn ảnh phình to nuốt mất JSON ở cuối, giải quyết lỗi Loss = 0.0.
            # Dùng hàm dùng chung của registry để train/eval/serve KHÔNG BAO GIỜ
            # lệch nhau — lệch là số token ảnh lệch theo và mask prompt sai.
            preprocess_image(img, self.spec)
            images.append(img)

            messages = self._build_messages(rec, img)

            # 1. Text chứa toàn bộ (câu hỏi + câu trả lời)
            full_texts.append(
                self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
            )

            # 2. Text chỉ chứa Prompt (để dùng làm thước đo chiều dài lúc Mask)
            messages_prompt_only = messages[:-1]
            prompt_texts.append(
                self.processor.apply_chat_template(messages_prompt_only, tokenize=False, add_generation_prompt=True)
            )

        # Một số processor (mllama) đòi images dạng lồng [[img], ...] thay vì phẳng.
        imgs = images_arg(images, self.spec)

        # Tokenize toàn bộ hội thoại
        batch = self.processor(
            text=full_texts,
            images=imgs,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=self.max_length,
        )

        # Tokenize prompt để đếm token
        prompt_batch = self.processor(
            text=prompt_texts,
            images=imgs,
            return_tensors="pt",
            padding=False,
            truncation=True,
            max_length=self.max_length,
        )

        labels = batch["input_ids"].clone()
        pad_id = self.processor.tokenizer.pad_token_id

        # Mask các token padding
        if pad_id is not None:
            labels[labels == pad_id] = IGNORE_INDEX

        # Mask các token hình ảnh. Tên thuộc tính khác nhau giữa các họ processor
        # nên dò trên cả processor và tokenizer; không tìm thấy cũng không sao vì
        # token ảnh nằm trong vùng prompt và sẽ bị mask ở bước dưới.
        for holder in (self.processor.tokenizer, self.processor):
            for tok_attr in ("image_token_id", "video_token_id"):
                tok_id = getattr(holder, tok_attr, None)
                if isinstance(tok_id, int):
                    labels[labels == tok_id] = IGNORE_INDEX

        # --- TỐI ƯU CỐT LÕI: KHÔI PHỤC MASK PROMPT ---
        # Che câu hỏi lại, ép AI tính Loss trên câu trả lời, giải quyết lỗi Loss kẹt 6.38
        for i in range(len(features)):
            prompt_len = len(prompt_batch["input_ids"][i])
            # Chỉ Mask phần prompt, chừa lại đoạn cuối là JSON
            labels[i, :prompt_len] = IGNORE_INDEX

        self._sanity_check(batch, labels, features)
        batch["labels"] = labels
        return batch

    def _sanity_check(self, batch, labels, features: List[dict]) -> None:
        """
        Hai chốt an toàn chống tái phát lỗi loss = 0.0 / loss kẹt khi đổi base model.

        Raises:
            RuntimeError: nếu có sample bị mask sạch label (không còn gì để học).
        """
        kept = (labels != IGNORE_INDEX).sum(dim=1)
        if int(kept.min()) == 0:
            worst = int(kept.argmin())
            raise RuntimeError(
                f"Sample '{features[worst].get('image')}' bị mask TOÀN BỘ label "
                f"(seq_len={labels.shape[1]}, max_length={self.max_length}). "
                f"Token ảnh đã tràn và cắt mất phần JSON đáp án → loss sẽ = 0.0. "
                f"Hạ ngân sách token ảnh (processor_kwargs) hoặc nâng --max_length "
                f"cho '{self.spec.key}' trong vlm_registry."
            )
        if batch["input_ids"].shape[1] >= self.max_length and not self._warned_truncate:
            logger.warning(
                "Chuỗi chạm trần max_length=%d → có truncation. Phần JSON đáp án có "
                "thể bị cắt cụt. Kiểm tra bằng: python -m src.models.vlm_registry "
                "--model %s --image <ảnh>",
                self.max_length, self.spec.key,
            )
            self._warned_truncate = True


# Giữ tên cũ để notebook/script đang import không vỡ.
QwenVLCollator = VLMCollator


def build_training_args(args: argparse.Namespace):
    """
    Dựng TrainingArguments — DÙNG CHUNG cho mọi model trong bộ so sánh.

    Không có tham số nào ở đây được phép tuỳ biến theo base model, nếu không so
    sánh sẽ mất tính công bằng.
    """
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
        seed=args.seed,
        data_seed=args.seed,
        bf16=(args.compute_dtype == "bfloat16"),
        fp16=(args.compute_dtype == "float16"),
        gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim="paged_adamw_8bit",
        report_to="none",
        remove_unused_columns=False,
        dataloader_pin_memory=False,
    )

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="QLoRA fine-tune VLM cho CCCD")
    p.add_argument("--train_jsonl", required=True)
    p.add_argument("--val_jsonl", required=True)
    p.add_argument("--image_root", default=".")
    p.add_argument("--output_dir", default="checkpoints/qwen2.5vl-3b-cccd-lora")

    p.add_argument("--model_name", default="Qwen/Qwen2.5-VL-3B-Instruct")
    p.add_argument(
        "--model_key",
        default=None,
        help="Key trong vlm_registry (qwen|internvl|llama_vision). Bỏ trống = suy từ --model_name.",
    )
    p.add_argument("--lora_r", type=int, default=None, help="Mặc định lấy từ registry (16)")
    p.add_argument("--lora_alpha", type=int, default=None, help="Mặc định lấy từ registry (32)")
    p.add_argument("--lora_dropout", type=float, default=None, help="Mặc định lấy từ registry (0.05)")
    p.add_argument("--compute_dtype", default="bfloat16", choices=["float16", "bfloat16"])

    p.add_argument("--epochs", type=float, default=3.0)
    p.add_argument("--batch_size", type=int, default=1)
    p.add_argument("--grad_accum", type=int, default=8)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--max_length",
        type=int,
        default=None,
        help="Bỏ trống = lấy từ registry theo họ model (Qwen 1536 / InternVL 2560 / Llama 1536)",
    )
    return p.parse_args()


def save_run_meta(out_dir: Path, args: argparse.Namespace, spec: VLMSpec, model) -> None:
    """
    Ghi `vlm_meta.json` cạnh adapter.

    evaluate.py và app/main.py đọc file này để tự dùng đúng base model + đúng cấu
    hình tiền xử lý — tránh việc gắn adapter của model này lên base của model khác,
    hoặc eval bằng tiền xử lý khác lúc train.
    """
    meta = {
        "model_id": args.model_name,
        "model_key": spec.key,
        "family": spec.family,
        "max_length": args.max_length,
        "image_max_side": SHARED_IMAGE_MAX_SIDE,
        "image_tokens_in_text": spec.image_tokens_in_text,
        "processor_kwargs": spec.processor_kwargs,
        "lora": {
            "r": args.lora_r,
            "alpha": args.lora_alpha,
            "dropout": args.lora_dropout,
            "target_regex": spec.lora_target_regex,
        },
        "trainable_params_pct": round(trainable_params_pct(model), 4),
        "train": {
            "epochs": args.epochs,
            "lr": args.lr,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "effective_batch": args.batch_size * args.grad_accum,
            "compute_dtype": args.compute_dtype,
            "seed": args.seed,
        },
    }
    path = out_dir / "vlm_meta.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    logger.info("✅ Đã ghi metadata run → %s", path)


def main() -> None:
    from transformers import Trainer
    args = parse_args()

    spec = resolve(args.model_key or args.model_name)
    ok, reason = check_available(spec)
    if not ok:
        raise RuntimeError(f"Không chạy được {spec.model_id}: {reason}")

    # Siêu tham số LoRA và max_length: mặc định lấy từ registry để mọi model dùng
    # cùng ngân sách; CLI chỉ để override khi làm ablation.
    settings = LoraSettings(model_name=args.model_name, spec=spec, compute_dtype=args.compute_dtype)
    if args.lora_r is not None:
        settings.lora_r = args.lora_r
    if args.lora_alpha is not None:
        settings.lora_alpha = args.lora_alpha
    if args.lora_dropout is not None:
        settings.lora_dropout = args.lora_dropout
    args.lora_r, args.lora_alpha, args.lora_dropout = (
        settings.lora_r, settings.lora_alpha, settings.lora_dropout,
    )
    if args.max_length is None:
        args.max_length = spec.max_length
    logger.info(
        "Model=%s [%s] | max_length=%d | LoRA r=%d alpha=%d dropout=%.3f",
        args.model_name, spec.key, args.max_length,
        settings.lora_r, settings.lora_alpha, settings.lora_dropout,
    )

    model, processor = load_model_4bit(settings, use_gradient_checkpointing=True)

    train_ds = CCCDDataset(args.train_jsonl, args.image_root)
    val_ds = CCCDDataset(args.val_jsonl, args.image_root)
    collator = VLMCollator(
        processor=processor, dataset=train_ds, spec=spec, max_length=args.max_length
    )

    trainer = Trainer(
        model=model,
        args=build_training_args(args),
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collator,
    )

    logger.info("🚀 Bắt đầu fine-tune QLoRA...")

    # Huấn luyện từ đầu do checkpoint cũ đã bị hỏng gradient
    logger.info("🆕 Bắt đầu huấn luyện từ đầu với bộ xử lý chuẩn...")
    trainer.train()

    out = Path(args.output_dir)
    model.save_pretrained(out)
    processor.save_pretrained(out)
    save_run_meta(out, args, spec, model)
    logger.info("✅ Đã lưu adapter + processor → %s", out)

if __name__ == "__main__":
    main()
