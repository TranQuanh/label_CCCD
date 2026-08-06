"""
lora_setup.py
=============
Tải một VLM ở 4-bit NF4 (bitsandbytes) + bật gradient checkpointing, rồi gắn
PEFT/LoRA adapter — để fine-tune QLoRA vừa khít GPU L4 24GB trên Colab.

Model nào được tải là do [vlm_registry.py](vlm_registry.py) quyết định: mặc định
là Qwen2.5-VL-3B-Instruct (anchor), nhưng cùng đường code này chạy được cho
InternVL3.5-2B và Llama-3.2-11B-Vision với **cùng siêu tham số QLoRA** — đó là điều
kiện cần để so sánh fine-tune giữa các kiến trúc (xem VLM_COMPARISON_PLAN.md).

Vì sao mỗi bước:
  - 4-bit NF4 + double-quant: nén params xuống ~1/3 (vd 7B: ~14GB fp16 → ~4.5GB) →
    còn chỗ cho activation + optimizer state của LoRA.
  - bf16 compute TỐI ƯU cho GPU L4 (kiến trúc Ada Lovelace/Ampere).
  - gradient_checkpointing: đánh đổi compute lấy VRAM (không lưu activation,
    tính lại lúc backward) — bắt buộc để không tràn RAM.
  - prepare_model_for_kbit_training: cast layernorm/embeddings về fp32, bật
    input require_grad để gradient chảy qua khi đã đóng băng base 4-bit.
  - LoRA: chỉ train ~0.1-1% tham số (các ma trận low-rank trên attn/MLP của
    PHẦN NGÔN NGỮ); đóng băng vision tower cho rẻ & ổn định.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import torch

from src.models.vlm_registry import (
    SHARED_LORA_ALPHA,
    SHARED_LORA_DROPOUT,
    SHARED_LORA_R,
    SHARED_LORA_TARGETS,
    VLMSpec,
    assert_no_vision_lora,
    build_lora_target_regex,
    resolve,
)
from src.models.vlm_registry import load_processor as _registry_load_processor

logger = logging.getLogger(__name__)


@dataclass
class LoraSettings:
    """Tham số cấu hình QLoRA (chỉnh qua argparse ở train.py)."""

    model_name: str = "Qwen/Qwen2.5-VL-3B-Instruct"
    # Rank thấp đủ cho tác vụ OCR-extraction; tăng nếu underfit.
    # GIỮ NGUYÊN cho mọi model trong bộ so sánh — đây là biến kiểm soát.
    lora_r: int = SHARED_LORA_R
    lora_alpha: int = SHARED_LORA_ALPHA
    lora_dropout: float = SHARED_LORA_DROPOUT
    # Các lớp linear trong khối attention + MLP của language model.
    target_modules: List[str] = field(default_factory=lambda: list(SHARED_LORA_TARGETS))
    # Đóng băng vision encoder để tiết kiệm VRAM & tránh quên đặc trưng thị giác.
    freeze_vision: bool = True
    # bfloat16 tối ưu cho GPU L4/A100.
    compute_dtype: str = "bfloat16"
    # None → tự suy từ model_name qua registry.
    spec: Optional[VLMSpec] = None

    def resolved_spec(self) -> VLMSpec:
        """Trả về VLMSpec tương ứng (suy từ `model_name` nếu chưa truyền sẵn)."""
        return self.spec if self.spec is not None else resolve(self.model_name)


def _resolve_dtype(name: str) -> torch.dtype:
    """Map tên dtype (str) → torch.dtype."""
    return {"float16": torch.float16, "bfloat16": torch.bfloat16, "float32": torch.float32}[name]


def build_bnb_config(compute_dtype: torch.dtype):
    """
    Dựng BitsAndBytesConfig cho QLoRA (NF4 + double quant).

    Cấu hình này DÙNG CHUNG cho mọi model trong bộ so sánh, và cả evaluate.py /
    app/main.py cũng dựng lại y hệt.

    Args:
        compute_dtype: dtype dùng khi giải nén để tính toán.

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


def load_processor(model_name: str, spec: Optional[VLMSpec] = None):
    """
    Tải AutoProcessor cho model, áp kwarg riêng của họ model đó.

    Kwarg khống chế số token ảnh → khống chế VRAM, và khác nhau theo họ:
    Qwen dùng `min_pixels`/`max_pixels`, InternVL dùng `min_patches`/`max_patches`,
    Llama không có. Chi tiết trong `vlm_registry.REGISTRY`.

    Args:
        model_name: model_id trên HF hoặc thư mục adapter đã lưu processor.
        spec: VLMSpec; None → suy từ `model_name`.

    Returns:
        AutoProcessor đã cấu hình.
    """
    spec = spec if spec is not None else resolve(model_name)
    return _registry_load_processor(model_name, spec)


def load_model_4bit(settings: LoraSettings, use_gradient_checkpointing: bool = True):
    """
    Tải model 4-bit bằng AutoModelForImageTextToText, prepare cho k-bit training,
    gắn LoRA.

    Args:
        settings: LoraSettings.
        use_gradient_checkpointing: True (mặc định).

    Returns:
        (peft_model, processor).
    """
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    # [ĐÃ SỬA]: Dùng AutoModelForImageTextToText thay vì fix cứng Qwen3VLForConditionalGeneration
    from transformers import AutoModelForImageTextToText

    spec = settings.resolved_spec()
    compute_dtype = _resolve_dtype(settings.compute_dtype)
    logger.info(
        "Tải %s [%s] ở 4-bit NF4 (compute=%s)...",
        settings.model_name, spec.key, settings.compute_dtype,
    )
    if spec.gated:
        logger.info("Model gated — cần đã accept license + `huggingface-cli login`")

    model = AutoModelForImageTextToText.from_pretrained(
        settings.model_name,
        quantization_config=build_bnb_config(compute_dtype),
        device_map="auto",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    # Chuẩn bị cho QLoRA: ổn định numeric + nối lại đường gradient.
    # [ĐÃ SỬA] Truyền use_reentrant=False ngay tại đây và KHÔNG gọi
    # gradient_checkpointing_enable() lần nữa — tránh double-enable với
    # reentrant=True mặc định (xung đột làm gradient không chảy → loss kẹt).
    # Trainer (TrainingArguments.gradient_checkpointing=True) sẽ bật lại
    # idempotent cùng use_reentrant=False, an toàn.
    model = prepare_model_for_kbit_training(
        model,
        use_gradient_checkpointing=use_gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
    )
    if use_gradient_checkpointing:
        model.config.use_cache = False  # khắc với gradient checkpointing

    # Đóng băng vision tower (không train) để tiết kiệm VRAM.
    # Tên module khác nhau theo họ model — lấy từ registry, KHÔNG hardcode
    # "visual" (tên riêng của Qwen; InternVL là `vision_tower`, Llama là
    # `vision_model` → hardcode sẽ khiến vision tower KHÔNG bị đóng băng).
    if settings.freeze_vision:
        frozen = 0
        for name, param in model.named_parameters():
            if any(prefix in name for prefix in spec.vision_prefixes):
                param.requires_grad = False
                frozen += 1
        logger.info(
            "Đã đóng băng %d tham số vision tower (prefix=%s)", frozen, spec.vision_prefixes
        )
        if frozen == 0:
            logger.warning(
                "Không match được tham số vision nào với prefix=%s. Kiểm tra lại tên "
                "module: print([n for n, _ in model.named_modules()][:80])",
                spec.vision_prefixes,
            )

    # target_modules dạng REGEX có chặn vision tower. Xem giải thích chi tiết ở
    # vlm_registry.build_lora_target_regex — tóm lại: InternViT và ViT của Llama
    # cũng đặt tên q_proj/k_proj/v_proj nên list tên trần sẽ gắn adapter lên
    # chính các lớp vision đã đóng băng.
    target_regex = build_lora_target_regex(settings.target_modules, spec.vision_prefixes)
    logger.info("LoRA target_modules (regex): %s", target_regex)

    lora_config = LoraConfig(
        r=settings.lora_r,
        lora_alpha=settings.lora_alpha,
        lora_dropout=settings.lora_dropout,
        target_modules=target_regex,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)
    trainable, total = _log_trainable(model)
    if trainable == 0:
        raise RuntimeError(
            f"LoRA không gắn được module nào với regex {target_regex}. "
            f"Kiểm tra tên module thật của {settings.model_name}."
        )
    assert_no_vision_lora(model, spec)

    processor = load_processor(settings.model_name, spec)
    _check_padding_side(processor)
    return model, processor


def _check_padding_side(processor) -> None:
    """
    Cảnh báo nếu tokenizer pad bên trái.

    Collator ở train.py mask prompt bằng `labels[i, :prompt_len] = -100`, tức giả
    định padding nằm bên PHẢI. Nếu processor pad bên trái thì mask sẽ trúng vào
    vùng padding và loss được tính trên chính câu hỏi → loss kẹt không giảm.
    """
    side = getattr(processor.tokenizer, "padding_side", None)
    if side is not None and side != "right":
        logger.warning(
            "padding_side='%s' — collator cần 'right'. Đang ép về 'right'.", side
        )
        processor.tokenizer.padding_side = "right"


def _log_trainable(model) -> Tuple[int, int]:
    """In số tham số train được / tổng số (kiểm tra LoRA đã gắn đúng)."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    pct = 100 * trainable / total if total else 0.0
    logger.info("Trainable params: %s / %s (%.4f%%)", f"{trainable:,}", f"{total:,}", pct)
    if pct > 2.0:
        logger.warning(
            "Trainable %.2f%% cao bất thường (>2%%) — LoRA có thể đã gắn vào vision tower.",
            pct,
        )
    return trainable, total


def trainable_params_pct(model) -> float:
    """Tỉ lệ % tham số trainable — ghi vào report để so sánh ngân sách LoRA."""
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    return 100 * trainable / total if total else 0.0


if __name__ == "__main__":
    # Smoke test thủ công (cần GPU + model đã tải).
    import argparse
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_name", default="Qwen/Qwen2.5-VL-3B-Instruct")
    a = ap.parse_args()
    m, p = load_model_4bit(LoraSettings(model_name=a.model_name))
    print("OK — model & processor sẵn sàng train.")
