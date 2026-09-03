"""
config.py
=========
Đọc cấu hình từ biến môi trường (env) một cách tập trung. Mọi module backend
đọc giá trị qua module này, không đọc `os.getenv` rải rác.
"""

from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger(__name__)

# ── Kết nối ────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cccd",
)
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Proxy Colab Server ──────────────────────────────────────────────────────
# Đường dẫn ngrok Public URL tới Colab Inference Server
INFERENCE_SERVER_URL: str = os.getenv(
    "INFERENCE_SERVER_URL",
    "https://perjury-doorstop-selection.ngrok-free.dev",
)

# ── Bảo mật / token ────────────────────────────────────────────────────────
JWT_SECRET: str = os.getenv("JWT_SECRET", "dev-secret")
if "JWT_SECRET" not in os.environ:
    logger.warning(
        "Chưa đặt JWT_SECRET → dùng khóa ngầm định dev-secret. "
        "Đặt JWT_SECRET trong env cho môi trường thật."
    )

JWT_ALGORITHM: str = "HS256"
ACCESS_TTL_MIN: int = int(os.getenv("ACCESS_TTL_MIN", "60"))
REFRESH_TTL_DAYS: int = int(os.getenv("REFRESH_TTL_DAYS", "30"))

# ── Khóa tài khoản sau nhiều lần đăng nhập sai ─────────────────────────────
MAX_LOGIN_FAILS: int = int(os.getenv("MAX_LOGIN_FAILS", "5"))
LOCK_MINUTES: int = int(os.getenv("LOCK_MINUTES", "15"))

# ── Tính năng tùy chọn ─────────────────────────────────────────────────────
EMAIL_VERIFICATION_ENABLED: bool = os.getenv("EMAIL_VERIFICATION_ENABLED", "false").lower() in (
    "1", "true", "yes", "on",
)

# ── Chế độ chạy ────────────────────────────────────────────────────────────
# Mặc định = 1 (true) để máy local luôn chạy nhẹ dạng Proxy forwarding lên Colab
SKIP_MODEL_LOAD: bool = os.getenv("SKIP_MODEL_LOAD", "1").lower() in ("1", "true", "yes", "on")