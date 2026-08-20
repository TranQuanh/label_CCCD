"""
config.py
=========
Đọc cấu hình từ biến môi trường (env) một cách tập trung. Mọi module backend
đọc giá trị qua module này, không đọc `os.getenv` rải rác.

Các biến:
  DATABASE_URL   chuỗi kết nối PostgreSQL (bắt buộc khi có DB)
  REDIS_URL      chuỗi kết nối Redis (dùng cho blacklist token)
  JWT_SECRET     khóa bí mật ký access token; thiếu → random + cảnh báo
  ACCESS_TTL_MIN / REFRESH_TTL_DAYS / MAX_LOGIN_FAILS / LOCK_MINUTES
  EMAIL_VERIFICATION_ENABLED   cờ bật xác minh email (mặc định tắt)
  SKIP_MODEL_LOAD  1 → chạy chế độ "lite": bỏ nạp model, chỉ auth/forms/records
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

# ── Bảo mật / token ────────────────────────────────────────────────────────
# Khóa ký JWT. Nếu chưa đặt trong env → sinh ngẫu nhiên (mọi access token mất
# hiệu lực mỗi lần khởi động server — chỉ nên dùng cho phát triển).
JWT_SECRET: str = os.getenv("JWT_SECRET") or secrets.token_urlsafe(48)
if "JWT_SECRET" not in os.environ:
    logger.warning(
        "Chưa đặt JWT_SECRET → dùng khóa random, token sẽ bị vô hiệu khi restart. "
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
# 1 → không nạp model VLM (chạy được auth/forms/records trên máy không GPU).
SKIP_MODEL_LOAD: bool = os.getenv("SKIP_MODEL_LOAD", "0").lower() in ("1", "true", "yes", "on")