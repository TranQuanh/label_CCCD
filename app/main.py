"""
main.py (FastAPI)
=================
API phục vụ model CCCD đã fine-tune: nhận ảnh upload → trả JSON trích xuất.

Tối ưu bộ nhớ khi deploy:
  - Base Qwen2.5-VL-3B load 4-bit NF4 (giống lúc train) để vừa GPU nhỏ / tránh
    tràn RAM, rồi GẮN LoRA adapter qua PeftModel.from_pretrained.
  - Model load 1 lần ở startup (lifespan), tái dùng cho mọi request.

Endpoints:
  GET  /health          → kiểm tra model đã sẵn sàng.
  POST /extract-cccd/   → upload ảnh (+ side tùy chọn) → JSON.

Chạy:
  export ADAPTER_DIR=checkpoints/qwen2.5vl-3b-cccd-lora-back
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
from src.models.vlm_registry import (
    build_gen_kwargs,
    images_arg,
    load_processor,
    preprocess_image,
    resolve,
)
from src.utils.cccd_schema import SYSTEM_PROMPT, CardSide, build_user_prompt

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

BASE_MODEL = os.getenv("BASE_MODEL", "Qwen/Qwen2.5-VL-3B-Instruct")
ADAPTER_DIR = os.getenv("ADAPTER_DIR", "checkpoints/qwen2.5vl-3b-cccd-lora-back")
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))

# State toàn cục giữ model/processor/spec sau khi load.
STATE: dict = {"model": None, "processor": None, "spec": None}


def _resolve_spec(base_model: str, adapter_dir: str):
    """
    Suy VLMSpec cho model đang serve.

    Ưu tiên `vlm_meta.json` mà train.py ghi cạnh adapter — nó là nguồn chân lý về
    base model đã dùng lúc fine-tune, tránh trường hợp BASE_MODEL trong env trỏ
    sai họ model so với adapter.
    """
    meta_path = os.path.join(adapter_dir, "vlm_meta.json")
    if os.path.isfile(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        trained_on = meta.get("model_id")
        if trained_on and trained_on != base_model:
            logger.warning(
                "⚠ BASE_MODEL='%s' khác base lúc train ('%s') — gắn adapter lên base "
                "khác họ sẽ cho output vô nghĩa.", base_model, trained_on,
            )
        if meta.get("model_key"):
            return resolve(meta["model_key"])
    return resolve(base_model)


def load_inference_model(base_model: str, adapter_dir: str):
    """
    Load base 4-bit + gắn LoRA adapter để inference.

    Nếu không tìm thấy adapter_dir → chạy base model thuần (cảnh báo).

    Returns:
        (model, processor) ở chế độ eval.
    """
    # [ĐÃ SỬA] Dùng AutoModelForImageTextToText (khớp lora_setup.py & evaluate.py),
    # KHÔNG fix cứng Qwen3VL → chạy được trên transformers bản ổn định, không cần
    # cài từ source.
    from transformers import AutoModelForImageTextToText, BitsAndBytesConfig

    # bfloat16 khớp lúc train (L4/A100). Đổi float16 nếu GPU không hỗ trợ bf16 (vd T4).
    compute_dtype = torch.bfloat16
    bnb = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=compute_dtype,
    )

    spec = _resolve_spec(base_model, adapter_dir)
    STATE["spec"] = spec
    logger.info("Loading base %s [%s] ở 4-bit...", base_model, spec.key)
    model = AutoModelForImageTextToText.from_pretrained(
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

    # Qua registry để áp đúng kwarg khống chế token ảnh của họ model này.
    processor = load_processor(processor_src, spec)
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
    model, processor, spec = STATE["model"], STATE["processor"], STATE["spec"]
    # Khớp tiền xử lý lúc train qua ĐÚNG hàm dùng chung của registry (thu nhỏ
    # 1024px) → tránh lệch số token ảnh giữa train/serving và tránh OOM với ảnh
    # upload độ phân giải cao. Sửa resize ở đây mà không sửa train là hỏng model.
    preprocess_image(image, spec)
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
    inputs = processor(
        text=[text_input], images=images_arg([image], spec), return_tensors="pt", padding=True
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    # Greedy tường minh, lấy từ registry — cùng một nguồn với evaluate.py. Mỗi model
    # có mặc định sampling riêng trong generation_config.json; để mặc định là output
    # không tái lập được và lệch so với lúc đo metric.
    output_ids = model.generate(**inputs, **build_gen_kwargs(MAX_NEW_TOKENS))
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
