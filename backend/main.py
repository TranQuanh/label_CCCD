"""
main.py (FastAPI)
=================
Backend API phục vụ hệ thống e-KYC CCCD:
  1. API Người dùng, Xác thực & RBAC, Biểu mẫu, Lịch sử hồ sơ, Profile CCCD
     (/api/v1/*, Profile CCCD tại /api/v1/profiles) trên PostgreSQL + Redis.
  2. Proxy chuyển tiếp trích xuất CCCD (/extract-cccd/*) sang Colab Inference Server (GPU).
     Bắt buộc đăng nhập (Bearer token) — ảnh CCCD là dữ liệu cá nhân.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import requests
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from . import audit, auth, bootstrap, config, db, forms, profiles, records, redis_client, users
from .deps import get_current_user

INFERENCE_SERVER_URL = config.INFERENCE_SERVER_URL
MAX_UPLOAD_BYTES = config.MAX_UPLOAD_MB * 1024 * 1024
VALID_SIDES = ("truoc", "sau", "auto")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Khởi tạo kết nối DB/Redis và cấu hình Proxy inference sang Colab."""
    db.init_db()
    # Tạo admin đầu tiên nếu đặt ADMIN_USERNAME/ADMIN_EMAIL/ADMIN_PASSWORD
    # (tự bắt lỗi bên trong — không làm sập khởi động).
    bootstrap.bootstrap_admin()
    redis_client.get_redis()

    if INFERENCE_SERVER_URL:
        logger.info(f"🚀 Backend sẵn sàng. Chuyển tiếp AI inference lên Colab: {INFERENCE_SERVER_URL}")
    else:
        logger.warning(
            "⚠️ Chưa đặt INFERENCE_SERVER_URL → /extract-cccd/* sẽ trả 503 cho tới khi cấu hình."
        )
    yield
    db.close_db()


app = FastAPI(title="CCCD Extraction API", version="2.1.0", lifespan=lifespan)

# ── CORS (DEF-02) ──────────────────────────────────────────────────────────
# Cho phép Flutter Web (chạy ở origin khác) gọi API.
#   - CORS_ORIGINS đặt (phân tách dấu phẩy) → chỉ các origin đó.
#   - CORS_ORIGINS trống → chế độ dev: chỉ http(s)://localhost / 127.0.0.1 (mọi cổng).
# allow_credentials=False: app không dùng cookie — access token đi qua header
# Authorization, nên không cần (và không nên) bật credentials.
if config.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=config.CORS_DEV_ORIGIN_REGEX,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )

# ── P1: xác thực & quản lý tài khoản — toàn bộ app API gom dưới /api/v1 ─────
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(forms.router, prefix="/api/v1")

# ── P2: hồ sơ trích xuất (lịch sử từ PostgreSQL) ───────────────────────────
app.include_router(records.router, prefix="/api/v1")

# ── Profile CCCD của người dùng (nhiều profile / user, bảng tblCccdProfile) ─
app.include_router(profiles.router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    """Trạng thái server + DB + Redis + proxy inference.

    status = 'ok' khi DB và Redis đều OK, 'degraded' nếu một trong hai lỗi
    (vẫn HTTP 200). Redis tắt không làm chậm: redis_client tạm ngưng thử lại.
    """
    db_ok = db.ping()
    redis_ok = redis_client.ping()
    return {
        "status": "ok" if db_ok and redis_ok else "degraded",
        "model_loaded": False,
        "lite_mode": True,
        "proxy_mode": True,
        "inference_server_url": INFERENCE_SERVER_URL,
        "db": db_ok,
        "redis": redis_ok,
    }


# ── Kiểm tra đầu vào proxy ─────────────────────────────────────────────────

def _require_inference_server() -> None:
    if not INFERENCE_SERVER_URL:
        raise HTTPException(status_code=503, detail="Chưa cấu hình máy chủ AI (INFERENCE_SERVER_URL)")


def _validate_side(side: str) -> None:
    if side not in VALID_SIDES:
        raise HTTPException(
            status_code=400,
            detail=f"Tham số side không hợp lệ (chấp nhận: {', '.join(VALID_SIDES)})",
        )


def _sniff_image_type(head: bytes) -> Optional[str]:
    """Nhận dạng ảnh qua magic bytes (client không gửi content-type chuẩn)."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _read_image(file: UploadFile) -> tuple[bytes, str]:
    """
    Đọc ảnh upload, ép giới hạn kích thước (413) và kiểu ảnh (415).

    Trả (bytes, content_type). Chấp nhận content_type image/*; nếu client gửi
    application/octet-stream (Flutter http.MultipartFile mặc định) hoặc không
    gửi thì nhận dạng qua magic bytes (JPEG/PNG/WEBP); không nhận dạng được
    (vd HEIC) thì vẫn chuyển tiếp octet-stream để Colab quyết định như trước.
    Chỉ trả 415 khi content_type khai báo rõ không phải ảnh (vd text/plain).
    """
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Ảnh '{file.filename}' vượt quá {config.MAX_UPLOAD_MB} MB",
        )
    ctype = (file.content_type or "").lower()
    if ctype.startswith("image/"):
        return data, ctype
    if ctype in ("", "application/octet-stream"):
        return data, _sniff_image_type(data[:16]) or "application/octet-stream"
    raise HTTPException(status_code=415, detail="Chỉ chấp nhận tệp ảnh (image/*)")


@app.post("/extract-cccd/")
def extract_cccd(
    file: UploadFile = File(..., description="Ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên file)"),
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Proxy endpoint: Tiếp nhận ảnh từ Flutter, gửi sang Colab GPU và trả kết quả trích xuất.
    """
    _require_inference_server()
    _validate_side(side)
    file_bytes, ctype = _read_image(file)
    files_payload = {"file": (file.filename, file_bytes, ctype)}

    try:
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/",
            params={"side": side},
            files=files_payload,
            timeout=120,
        )
    except requests.RequestException:
        # Chỉ log chi tiết phía server; không lộ URL/exception ra client.
        logger.exception("❌ Lỗi kết nối Proxy tới Colab Server")
        raise HTTPException(status_code=502, detail="Không kết nối được máy chủ AI")

    if not (200 <= response.status_code < 300):
        logger.error(f"❌ Colab trả HTTP {response.status_code} cho '{file.filename}' (side={side})")
        raise HTTPException(status_code=502, detail="Máy chủ AI trả lỗi. Thử lại sau.")
    try:
        result = response.json()
    except ValueError:
        logger.error(f"❌ Colab trả dữ liệu không phải JSON cho '{file.filename}'")
        raise HTTPException(status_code=502, detail="Máy chủ AI trả dữ liệu không hợp lệ")
    if not isinstance(result, dict):
        raise HTTPException(status_code=502, detail="Máy chủ AI trả dữ liệu không hợp lệ")

    # Chỉ log metadata — KHÔNG log data/raw (chứa số CCCD, họ tên, địa chỉ...).
    logger.info(
        f"[PROXY] filename={file.filename} side={result.get('side', side)} "
        f"latency_ms={result.get('latency_ms')} parse_ok={result.get('parse_ok')}"
    )
    return result


@app.post("/extract-cccd/batch")
def extract_cccd_batch(
    files: List[UploadFile] = File(..., description="Nhiều ảnh CCCD (jpg/png)"),
    side: str = Query("auto", description="truoc | sau | auto (suy từ tên từng file)"),
    _user: dict = Depends(get_current_user),
) -> dict:
    """
    Proxy endpoint: Tiếp nhận danh sách ảnh từ Flutter, gửi sang Colab GPU theo batch.
    """
    _require_inference_server()
    _validate_side(side)
    files_payload = []
    for f in files:
        data, ctype = _read_image(f)
        files_payload.append(("files", (f.filename, data, ctype)))

    try:
        response = requests.post(
            f"{INFERENCE_SERVER_URL}/extract-cccd/batch",
            params={"side": side},
            files=files_payload,
            timeout=300,
        )
    except requests.RequestException:
        logger.exception("❌ Lỗi kết nối tới Colab Server (Batch)")
        raise HTTPException(status_code=502, detail="Không kết nối được máy chủ AI")

    if not (200 <= response.status_code < 300):
        logger.error(f"❌ Colab (batch) trả HTTP {response.status_code} cho {len(files)} ảnh")
        raise HTTPException(status_code=502, detail="Máy chủ AI trả lỗi. Thử lại sau.")
    try:
        result = response.json()
    except ValueError:
        logger.error("❌ Colab (batch) trả dữ liệu không phải JSON")
        raise HTTPException(status_code=502, detail="Máy chủ AI trả dữ liệu không hợp lệ")
    logger.info(f"[PROXY BATCH] n_images={len(files)} side={side}")
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
