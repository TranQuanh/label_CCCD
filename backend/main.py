"""
main.py (FastAPI)
=================
Backend API phục vụ hệ thống e-KYC CCCD:
  1. API Người dùng, Xác thực & RBAC, Biểu mẫu, Lịch sử hồ sơ (/api/v1/*) trên PostgreSQL + Redis.
  2. Proxy chuyển tiếp trích xuất CCCD (/extract-cccd/*) sang Colab Inference Server (GPU).
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from typing import List

import requests
from fastapi import FastAPI, File, Query, UploadFile

from . import audit, auth, config, db, forms, records, redis_client, users

INFERENCE_SERVER_URL = config.INFERENCE_SERVER_URL
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo kết nối DB/Redis và cấu hình Proxy inference sang Colab."""
    db.init_db()
    redis_client.get_redis()

    logger.info(f"🚀 Backend sẵn sàng. Chuyển tiếp AI inference lên Colab: {INFERENCE_SERVER_URL}")
    yield
    db.close_db()


app = FastAPI(title="CCCD Extraction API", version="2.1.0", lifespan=lifespan)

# ── P1: xác thực & quản lý tài khoản — toàn bộ app API gom dưới /api/v1 ─────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(forms.router, prefix="/api/v1")

# ── P2: hồ sơ trích xuất (lịch sử từ PostgreSQL) ───────────────────────────
app.include_router(records.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    """Trạng thái server + DB + Redis + proxy inference."""
    return {
        "status": "ok",
        "model_loaded": False,
        "lite_mode": True,
        "proxy_mode": True,
        "inference_server_url": INFERENCE_SERVER_URL,
        "db": db.ping(),
        "redis": redis_client.get_redis() is not None,
    }


@app.post("/extract-cccd/")
def extract_cccd(
    file: UploadFile = File(..., description="Ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên file)"),
) -> dict:
    """
    Proxy endpoint: Tiếp nhận ảnh từ Flutter, gửi sang Colab GPU và trả kết quả trích xuất.
    """
    try:
        # 1. Đọc file upload
        file_bytes = file.file.read()
        files_payload = {"file": (file.filename, file_bytes, file.content_type)}

        # 2. Chuyển tiếp request sang Colab Inference Server
        logger.info(f"🚀 [PROXY REQUEST] Gửi ảnh '{file.filename}' (side={side}) sang Colab ({INFERENCE_SERVER_URL})...")
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/",
            params={"side": side},
            files=files_payload,
            timeout=120,
        )
        result = response.json()

        # 3. In log kết quả trả về từ Colab
        card_side = result.get("side", side)
        logger.info(f"================ COLAB RESPONSE [{card_side}] ================")
        logger.info(f"📁 Filename : {result.get('filename')}")
        logger.info(f"⏱️ Latency  : {result.get('latency_ms')} ms")
        logger.info(f"✅ Parse OK : {result.get('parse_ok')}")

        if result.get("data"):
            logger.info("📄 PARSED DATA (JSON từ Model):")
            logger.info(json.dumps(result.get("data"), ensure_ascii=False, indent=2))
        else:
            logger.warning(f"⚠️ RAW OUTPUT (Không parse được JSON): {result.get('raw')}")
            logger.warning(f"⚠️ Lỗi (nếu có): {result.get('error')}")

        logger.info("============================================================")
        return result

    except Exception as exc:
        logger.exception("❌ Lỗi kết nối Proxy tới Colab Server")
        return {"filename": file.filename, "error": f"Lỗi Proxy Colab: {str(exc)}"}


@app.post("/extract-cccd/batch")
def extract_cccd_batch(
    files: List[UploadFile] = File(..., description="Nhiều ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên từng file)"),
) -> dict:
    """
    Proxy endpoint: Tiếp nhận danh sách ảnh từ Flutter, gửi sang Colab GPU theo batch.
    """
    try:
        files_payload = [("files", (f.filename, f.file.read(), f.content_type)) for f in files]
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/batch",
            params={"side": side},
            files=files_payload,
            timeout=300,
        )
        return response.json()
    except Exception as exc:
        logger.exception("❌ Lỗi kết nối tới Colab Server (Batch)")
        return {"error": f"Lỗi Proxy Colab: {str(exc)}", "n_images": len(files)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
