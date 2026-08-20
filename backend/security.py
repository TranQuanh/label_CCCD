"""
security.py
===========
Thao tác bảo mật dùng chung: hash mật khẩu (bcrypt), tạo/kiểm tra JWT access
token, tạo refresh token ngẫu nhiên + băm.

Mọi thứ liên quan token chỉ nằm ở đây:
  - Access token: JWT HS256, claims `sub` (user_id), `role`, `tok_ver`, `jti`.
  - Refresh token: chuỗi ngẫu nhiên 64 ký tự; DB chỉ lưu SHA-256 (kẻ đọc DB
    không thể dùng lại token đánh cắp được).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt
import jwt

from . import config


# ── Mật khẩu (bcrypt) ─────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """Băm mật khẩu bằng bcrypt (salt tự sinh, nhúng trong output)."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """So sánh mật khẩu với hash bcrypt."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


# ── Access token (JWT) ─────────────────────────────────────────────────────
def create_access_token(user_id: str, role: str, token_version: int) -> tuple[str, str]:
    """
    Tạo JWT access token.

    Returns:
        (token, jti) — jti là id duy nhất của token này, dùng để blacklist.
    """
    jti = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "tok_ver": token_version,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=config.ACCESS_TTL_MIN),
        "type": "access",
    }
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    return token, jti


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    """Giải mã JWT; trả None nếu hết hạn/sai chữ ký/không phải access token."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    return payload


# ── Refresh token (ngẫu nhiên + băm trong DB) ─────────────────────────────
def generate_refresh_token() -> str:
    """Refresh token ngẫu nhiên 64 ký tự (chỉ xuất hiện 1 lần, không lưu thô)."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Băm refresh token trước khi lưu vào DB (SHA-256 hex)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()