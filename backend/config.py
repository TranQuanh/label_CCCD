"""
config.py
=========
Đọc cấu hình từ biến môi trường (env) một cách tập trung. Mọi module backend
đọc giá trị qua module này, không đọc `os.getenv` rải rác.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


# ── Nạp file backend/.env (nếu có) ─────────────────────────────────────────
# Bộ đọc tối giản, không cần cài python-dotenv. Mỗi dòng dạng KEY=VALUE; bỏ
# qua dòng trống và dòng bắt đầu bằng '#'. Biến môi trường đã đặt sẵn (vd.
# $env:SMTP_USER) được ưu tiên hơn giá trị trong .env.
ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            os.environ.setdefault(key, value)


_load_env_file(ENV_FILE)

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

# ── Gửi email (quên mật khẩu) ──────────────────────────────────────────────
# Đọc từ backend/.env (đã git ignore) — xem mẫu backend/.env.example.
# Gmail: bật Xác minh 2 bước → tạo App Password 16 ký tự (bỏ dấu cách) tại
# https://myaccount.google.com/apppasswords rồi điền vào SMTP_PASSWORD.
# Để SMTP_USER hoặc SMTP_PASSWORD rỗng → KHÔNG gửi mail, mã OTP được in ra
# console của uvicorn (dùng khi test/demo).
SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587") or "587")  # 587 = STARTTLS, 465 = SSL
SMTP_USER: str = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "").replace(" ", "")
SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "SmartID").strip() or "SmartID"
SMTP_TIMEOUT_SECONDS: int = 15

# Mã OTP đặt lại mật khẩu
RESET_CODE_TTL_MIN: int = 10         # mã hết hạn sau 10 phút
RESET_RESEND_SECONDS: int = 60       # phải chờ 60 giây mới xin mã mới
RESET_MAX_ATTEMPTS: int = 5          # nhập sai 5 lần → mã bị huỷ

# ── Chế độ chạy ────────────────────────────────────────────────────────────
# Backend máy cục bộ luôn chạy chế độ Proxy nhẹ (inference xử lý trên Colab GPU)
SKIP_MODEL_LOAD: bool = True