"""
deps.py
=======
Phụ thuộc FastAPI dùng chung cho các router:
  get_current_user     — giải mã Bearer token → user (kèm kiểm tra blacklist/active/tok_ver)
  require_admin        — ép role == 'admin' (dùng cho /users, /audit-logs)
  require_role(min_role) — RBAC: 'user' < 'admin'
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

from . import db, redis_client
from .security import decode_access_token

# Thứ tự quyền: càng về sau càng cao.
ROLE_LEVELS = {"user": 1, "admin": 2}

# Tên cột role dùng chung cho mọi truy vấn đọc user.
ROLE_ORDER = "CASE role WHEN 'admin' THEN 2 ELSE 1 END"


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def parse_uuid(value) -> Optional[str]:
    """Chuỗi UUID hợp lệ → dạng chuẩn; sai định dạng → None (DEF-23: để
    router trả 404/400 thay vì lỗi 500 từ PostgreSQL)."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
) -> dict:
    """
    Lấy user hiện tại từ Bearer token.

    Kiểm tra lần lượt: token hợp lệ → jti chưa bị blacklist → user tồn tại &
    đang active → token_version khớp (đổi role = token cũ vô hiệu).
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized("Thiếu token truy cập (Authorization: Bearer ...)")
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    if payload is None:
        raise _unauthorized("Token không hợp lệ hoặc đã hết hạn")

    if redis_client.is_blacklisted(payload.get("jti", "")):
        raise _unauthorized("Token đã bị thu hồi (đã đăng xuất)")

    # 'sub' thiếu / sai định dạng UUID → 401 thay vì lỗi 500 từ PostgreSQL.
    sub = parse_uuid(payload.get("sub")) if payload.get("sub") else None
    if sub is None:
        raise _unauthorized("Token không hợp lệ")

    user = db.fetch_one(
        "SELECT id, username, email, password_hash, full_name, role, is_active, "
        "token_version FROM tblUser WHERE id = %s",
        (sub,),
    )
    if user is None:
        raise _unauthorized("Tài khoản không tồn tại")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tài khoản đã bị khóa")
    if user["token_version"] != payload.get("tok_ver"):
        raise _unauthorized("Phiên đã bị thu hồi (thông tin tài khoản thay đổi)")

    return user


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Chỉ admin được đi tiếp."""
    if user["role"] != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cần quyền quản trị viên")
    return user


def require_role(min_role: str):
    """RBAC: yêu cầu role tối thiểu. user < admin."""

    def checker(user: dict = Depends(get_current_user)) -> dict:
        if ROLE_LEVELS.get(user["role"], 0) < ROLE_LEVELS[min_role]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cần quyền tối thiểu '{min_role}'",
            )
        return user

    return checker