"""
main.py (FastAPI)
=================
API phục vụ model CCCD đã fine-tune: nhận ảnh upload → trả JSON trích xuất.

Tối ưu bộ nhớ khi deploy:
  - Base Qwen3-VL-8B load 4-bit NF4 (giống lúc train) để vừa GPU nhỏ / tránh
    tràn RAM, rồi GẮN LoRA adapter qua PeftModel.from_pretrained.
  - Model load 1 lần ở startup (lifespan), tái dùng cho mọi request.

Endpoints:
  GET  /health          → kiểm tra model đã sẵn sàng.
  POST /extract-cccd/   → upload ảnh (+ side tùy chọn) → JSON.

Chạy:
  export ADAPTER_DIR=checkpoints/qwen3vl-cccd-lora
  uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import io
import json
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import torch
from fastapi import FastAPI, File, Query, UploadFile
from PIL import Image

from src.data_pipeline.auto_label import parse_json_safe
from src.utils.cccd_schema import SYSTEM_PROMPT, CardSide, build_user_prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_MODEL = os.getenv("BASE_MODEL", "Qwen/Qwen3-VL-8B-Instruct")
ADAPTER_DIR = os.getenv("ADAPTER_DIR", "checkpoints/qwen3vl-cccd-lora")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))

# State toàn cục giữ model/processor sau khi load.
STATE: dict = {"model": None, "processor": None}


def load_inference_model(base_model: str, adapter_dir: str):
    """
    Load base 4-bit + gắn LoRA adapter để inference.

    Nếu không tìm thấy adapter_dir → chạy base model thuần (cảnh báo).

    Returns:
        (model, processor) ở chế độ eval.
    """
    from transformers import AutoProcessor, BitsAndBytesConfig

    # Base phải khớp loader class lúc fine-tune (Qwen3-VL) để gắn adapter đúng.
    try:
        from transformers import Qwen3VLForConditionalGeneration as ModelCls
    except ImportError as exc:
        raise ImportError(
            "Cần transformers hỗ trợ Qwen3-VL: "
            "pip install git+https://github.com/huggingface/transformers"
        ) from exc

    compute_dtype = torch.float16  # đồng nhất với T4; đổi bf16 nếu GPU hỗ trợ
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    logger.info("Loading base %s ở 4-bit...", base_model)
    model = ModelCls.from_pretrained(
        base_model,
        quantization_config=bnb,
        device_map="auto",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    processor_src = base_model
    if os.path.isdir(adapter_dir):
        from peft import PeftModel

        logger.info("Gắn LoRA adapter từ %s", adapter_dir)
        model = PeftModel.from_pretrained(model, adapter_dir)
        processor_src = adapter_dir  # processor đã lưu kèm adapter
    else:
        logger.warning("Không thấy adapter '%s' → dùng base model thuần", adapter_dir)

    processor = AutoProcessor.from_pretrained(processor_src, trust_remote_code=True)
    model.eval()
    logger.info("✓ Model sẵn sàng phục vụ")
    return model, processor


@torch.no_grad()
def run_inference(image: Image.Image, side: CardSide) -> str:
    """
    Chạy 1 ảnh qua model, trả chuỗi text sinh ra (chưa parse).

    Args:
        image: Ảnh PIL RGB.
        side: Mặt thẻ (quyết định prompt).

    Returns:
        Chuỗi output thô của model.
    """
    model, processor = STATE["model"], STATE["processor"]
    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": build_user_prompt(side)},
            ],
        },
    ]
    text_input = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = processor(text=[text_input], images=[image], return_tensors="pt", padding=True)
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    output_ids = model.generate(**inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False)
    generated = output_ids[:, inputs["input_ids"].shape[1]:]
    return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model 1 lần lúc khởi động, dọn dẹp khi tắt."""
    STATE["model"], STATE["processor"] = load_inference_model(BASE_MODEL, ADAPTER_DIR)
    yield
    STATE.clear()


app = FastAPI(title="CCCD Extraction API", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    """Kiểm tra model đã load chưa."""
    return {"status": "ok", "model_loaded": STATE["model"] is not None}


@app.post("/extract-cccd/")
async def extract_cccd(
    file: UploadFile = File(..., description="Ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên file)"),
) -> dict:
    """
    Trích xuất thông tin CCCD từ ảnh upload.

    Args:
        file: File ảnh upload.
        side: 'truoc'/'sau' để ép mặt thẻ, hoặc 'auto' để suy từ tên file.

    Returns:
        dict gồm: filename, side, parse_ok, data (JSON đã parse) và raw output.
    """
    raw_bytes = await file.read()
    try:
        image = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Không đọc được ảnh: {exc}"}

    if side == CardSide.FRONT.value:
        card_side = CardSide.FRONT
    elif side == CardSide.BACK.value:
        card_side = CardSide.BACK
    else:
        from src.utils.cccd_schema import infer_side_from_filename

        card_side = infer_side_from_filename(file.filename or "")

    try:
        raw = run_inference(image, card_side)
        parsed = parse_json_safe(raw)
        if parsed is not None and card_side != CardSide.UNKNOWN:
            parsed.setdefault("mat_the", card_side.value)
        return {
            "filename": file.filename,
            "side": card_side.value,
            "parse_ok": parsed is not None,
            "data": parsed if parsed is not None else None,
            "raw": raw if parsed is None else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Lỗi inference")
        return {"error": str(exc)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)
