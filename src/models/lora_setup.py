"""
lora_setup.py
=============
Tải Qwen3-VL-8B-Instruct ở 4-bit NF4 (bitsandbytes) + bật gradient checkpointing,
rồi gắn PEFT/LoRA adapter — để fine-tune QLoRA vừa khít GPU T4 15GB trên Colab.

LƯU Ý: Qwen3-VL cần `transformers` cài từ source (>= bản hỗ trợ Qwen3-VL) thì mới
có class `Qwen3VLForConditionalGeneration`. model_name có thể là HF ID hoặc PATH
LOCAL (đã `huggingface-cli download` về máy/Drive).

Vì sao mỗi bước:
  - 4-bit NF4 + double-quant: nén 7B params từ ~14GB (fp16) xuống ~4.5GB → còn
    chỗ cho activation + optimizer state của LoRA.
  - bf16 compute KHÔNG dùng được trên T4 (kiến trúc Turing) → mặc định float16.
  - gradient_checkpointing: đánh đổi compute lấy VRAM (không lưu activation,
    tính lại lúc backward) — bắt buộc với T4.
  - prepare_model_for_kbit_training: cast layernorm/embeddings về fp32, bật
    input require_grad để gradient chảy qua khi đã đóng băng base 4-bit.
  - LoRA: chỉ train ~0.1-1% tham số (các ma trận low-rank trên attn/MLP của
    PHẦN NGÔN NGỮ); đóng băng vision tower cho rẻ & ổn định.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Tuple

import torch

logger = logging.getLogger(__name__)


@dataclass
class LoraSettings:
    """Tham số cấu hình QLoRA (chỉnh qua argparse ở train.py)."""

    model_name: str = "Qwen/Qwen3-VL-8B-Instruct"
    # Rank thấp đủ cho tác vụ OCR-extraction; tăng nếu underfit.
    lora_r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    # Các lớp linear trong khối attention + MLP của language model.
    target_modules: List[str] = field(
        default_factory=lambda: [
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ]
    )
    # Đóng băng vision encoder để tiết kiệm VRAM & tránh quên đặc trưng thị giác.
    freeze_vision: bool = True
    # float16 cho T4; đổi bfloat16 nếu chạy A100/L4/RTX 30xx+.
    compute_dtype: str = "float16"


def _resolve_dtype(name: str) -> torch.dtype:
    """Map tên dtype (str) → torch.dtype."""
    return {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[name]


def build_bnb_config(compute_dtype: torch.dtype):
    """
    Dựng BitsAndBytesConfig cho QLoRA (NF4 + double quant).

    Args:
        compute_dtype: dtype dùng khi giải nén để tính toán (fp16 cho T4).

    Returns:
        transformers.BitsAndBytesConfig.
    """
    from transformers import BitsAndBytesConfig

    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )


def load_processor(model_name: str, min_pixels: int = 256 * 28 * 28,
                   max_pixels: int = 1280 * 28 * 28):
    """
    Tải AutoProcessor cho Qwen2-VL.

    min/max_pixels khống chế số token ảnh → khống chế VRAM. CCCD là ảnh chữ nên
    giữ độ phân giải vừa phải (max ~1280*28*28) là đủ nét mà không nổ token.

    Returns:
        AutoProcessor đã cấu hình.
    """
    from transformers import AutoProcessor

    processor = AutoProcessor.from_pretrained(
        model_name, trust_remote_code=True, min_pixels=min_pixels, max_pixels=max_pixels
    )
    return processor


def load_model_4bit(settings: LoraSettings, use_gradient_checkpointing: bool = True):
    """
    Tải Qwen2-VL 4-bit, prepare cho k-bit training, gắn LoRA.

    Args:
        settings: LoraSettings.
        use_gradient_checkpointing: True (mặc định) — bắt buộc với T4.

    Returns:
        (peft_model, processor).
    """
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    try:
        from transformers import Qwen3VLForConditionalGeneration as ModelCls
    except ImportError as exc:  # transformers chưa đủ mới
        raise ImportError(
            "Không import được Qwen3VLForConditionalGeneration. Hãy cài transformers "
            "từ source: pip install git+https://github.com/huggingface/transformers"
        ) from exc

    compute_dtype = _resolve_dtype(settings.compute_dtype)
    logger.info("Tải %s ở 4-bit NF4 (compute=%s)...", settings.model_name, settings.compute_dtype)

    model = ModelCls.from_pretrained(
        settings.model_name,
        quantization_config=build_bnb_config(compute_dtype),
        device_map="auto",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    # Chuẩn bị cho QLoRA: ổn định numeric + nối lại đường gradient.
    model = prepare_model_for_kbit_training(
        model, use_gradient_checkpointing=use_gradient_checkpointing
    )
    if use_gradient_checkpointing:
        model.gradient_checkpointing_enable()
        model.config.use_cache = False  # khắc với gradient checkpointing

    # Đóng băng vision tower (không train) để tiết kiệm VRAM.
    if settings.freeze_vision:
        frozen = 0
        for name, param in model.named_parameters():
            if "visual" in name:
                param.requires_grad = False
                frozen += 1
        logger.info("Đã đóng băng %d tham số vision tower", frozen)

    lora_config = LoraConfig(
        r=settings.lora_r,
        lora_alpha=settings.lora_alpha,
        lora_dropout=settings.lora_dropout,
        target_modules=settings.target_modules,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    _log_trainable(model)

    processor = load_processor(settings.model_name)
    return model, processor


def _log_trainable(model) -> Tuple[int, int]:
    """In số tham số train được / tổng số (kiểm tra LoRA đã gắn đúng)."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    pct = 100 * trainable / total if total else 0.0
    logger.info("Trainable params: %s / %s (%.4f%%)", f"{trainable:,}", f"{total:,}", pct)
    return trainable, total


if __name__ == "__main__":
    # Smoke test thủ công (cần GPU + model đã tải).
    logging.basicConfig(level=logging.INFO)
    m, p = load_model_4bit(LoraSettings())
    print("OK — model & processor sẵn sàng train.")
