"""
config.py
=========
Đọc cấu hình từ biến môi trường (env) một cách tập trung. Mọi module backend
đọc giá trị qua module này, không đọc `os.getenv` rải rác.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# ── Kết nối ────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/cccd",
)
REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Redis không kết nối được → trong bấy nhiêu giây không thử lại (request không
# bị chậm do chờ kết nối mỗi lần).
REDIS_RETRY_SECONDS: float = float(os.getenv("REDIS_RETRY_SECONDS", "30"))

# ── Proxy Colab Server ──────────────────────────────────────────────────────
# Public URL (ngrok, tên miền tĩnh) tới Colab Inference Server. Ghi đè bằng env
# INFERENCE_SERVER_URL; đặt rỗng tường minh thì /extract-cccd/* trả 503.
INFERENCE_SERVER_URL: str = os.getenv(
    "INFERENCE_SERVER_URL", "https://perjury-doorstop-selection.ngrok-free.dev"
).strip().rstrip("/")

# Giới hạn kích thước mỗi ảnh upload lên /extract-cccd/* (MB) → vượt thì 413.
MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))

# ── Admin đầu tiên (tùy chọn) ──────────────────────────────────────────────
# Đặt đủ cả 3 biến → lúc khởi động tạo tài khoản admin nếu chưa tồn tại
# (xem bootstrap.py). Không có mật khẩu mặc định trong code.
ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "").strip()
ADMIN_EMAIL: str = os.getenv("ADMIN_EMAIL", "").strip()
ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "")

# ── CORS ───────────────────────────────────────────────────────────────────
# CORS_ORIGINS: danh sách origin phân tách dấu phẩy (vd "https://app.example.vn").
# Để trống → chế độ dev: chỉ cho phép http(s)://localhost|127.0.0.1 (mọi cổng).
CORS_ORIGINS: list[str] = [
    o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
]
CORS_DEV_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

# ── Bảo mật / token ────────────────────────────────────────────────────────
# JWT_SECRET nên là chuỗi ngẫu nhiên ≥ 16 ký tự, khác 'dev-secret'. Khóa yếu
# chỉ bị chặn khi APP_ENV=production; chạy cục bộ thì chỉ cảnh báo.
_JWT_MIN_LEN = 16
APP_ENV: str = os.getenv("APP_ENV", "").strip().lower()
JWT_SECRET: str = os.getenv("JWT_SECRET", "") or "dev-secret"
if JWT_SECRET == "dev-secret" or len(JWT_SECRET) < _JWT_MIN_LEN:
    if APP_ENV == "production":
        raise RuntimeError(
            "JWT_SECRET chưa đặt, bằng 'dev-secret' hoặc ngắn hơn "
            f"{_JWT_MIN_LEN} ký tự trong khi APP_ENV=production. Hãy đặt JWT_SECRET "
            "là một chuỗi ngẫu nhiên dài (vd: python -c \"import secrets; "
            "print(secrets.token_urlsafe(48))\")."
        )
    logger.warning(
        "JWT_SECRET yếu hoặc chưa đặt — chỉ dùng cho phát triển cục bộ. "
        "KHÔNG dùng cấu hình này cho môi trường thật."
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
# Backend máy cục bộ luôn chạy chế độ Proxy nhẹ (inference xử lý trên Colab GPU)
SKIP_MODEL_LOAD: bool = True