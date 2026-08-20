"""
users.py
========
Router quản lý tài khoản (`/users/*`) — admin-only, RBAC.

Guards:
  - Không cho admin tự hạ quyền chính mình.
  - Không cho vô hiệu hóa / hạ quyền admin cuối cùng.
  - Đổi role hoặc khóa tài khoản → `token_version++` + revoke mọi refresh token
    (buộc người đó đăng nhập lại). Đây là cơ chế thu hồi quyền khớp tài liệu.
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import db
from .audit import audit
from .deps import ROLE_LEVELS, require_admin
from .security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

VALID_ROLES = tuple(ROLE_LEVELS.keys())


class CreateUserBody(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    role: str = Field(default="operator")


class UpdateUserBody(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


def _revoke_tokens(user_id: str) -> None:
    """Vô hiệu hóa toàn bộ phiên của user (revoke refresh + bump token_version)."""
    db.execute(
        "UPDATE tblUser SET token_version = token_version + 1 WHERE id = %s",
        (user_id,),
    )
    db.execute(
        "UPDATE tblRefreshToken SET revoked_at = NOW() "
        "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()",
        (user_id,),
    )


def _count_active_admins() -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS n FROM tblUser WHERE role = 'admin' AND is_active = TRUE"
    )
    return int(row["n"])


@router.get("")
def list_users() -> dict:
    """Danh sách tài khoản (không trả password_hash)."""
    rows = db.fetch_all(
        "SELECT id, username, email, full_name, role, is_active, "
        "failed_login_count, locked_until, created_at, updated_at "
        "FROM tblUser ORDER BY created_at DESC"
    )
    return {"users": rows, "count": len(rows)}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserBody, request: Request, admin: dict = Depends(require_admin)):
    """Admin tạo tài khoản mới (không cần người dùng đăng ký)."""
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ (chấp nhận: {', '.join(VALID_ROLES)})")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 8 ký tự")

    username = body.username.strip()
    email = body.email.strip().lower()
    exists = db.fetch_one(
        "SELECT id FROM tblUser WHERE username = %s OR email = %s", (username, email)
    )
    if exists:
        raise HTTPException(status_code=409, detail="Tên đăng nhập hoặc email đã tồn tại")

    user_id = db.fetch_one(
        "INSERT INTO tblUser (username, email, password_hash, full_name, role) "
        "VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (username, email, hash_password(body.password), body.full_name.strip(), body.role),
    )["id"]
    ip = request.client.host if request.client else None
    audit(admin["id"], "user.create", "user", user_id, {"username": username}, ip)
    return {"message": "Đã tạo tài khoản", "user_id": user_id}


@router.put("/{user_id}")
def update_user(
    user_id: str,
    body: UpdateUserBody,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    """Admin sửa role/full_name/khóa mở + reset mật khẩu."""
    target = db.fetch_one("SELECT * FROM tblUser WHERE id = %s", (user_id,))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    # ── Guards ──────────────────────────────────────────────────────────────
    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ (chấp nhận: {', '.join(VALID_ROLES)})")

    # Không cho admin tự hạ quyền chính mình.
    if user_id == admin["id"] and body.role is not None and body.role != "admin":
        raise HTTPException(status_code=400, detail="Không thể hạ quyền của chính bạn")

    # Không cho vô hiệu hóa / hạ quyền admin cuối cùng.
    if target["role"] == "admin" and target["is_active"]:
        if body.role is not None and body.role != "admin":
            if _count_active_admins() <= 1:
                raise HTTPException(status_code=400, detail="Không thể hạ quyền admin cuối cùng")
        if body.is_active is False and _count_active_admins() <= 1:
            raise HTTPException(status_code=400, detail="Không thể khóa admin cuối cùng")

    # ── Áp dụng thay đổi ────────────────────────────────────────────────────
    updates: list[str] = []
    params: list = []

    if body.full_name is not None:
        updates.append("full_name = %s")
        params.append(body.full_name.strip())
    if body.password is not None:
        if len(body.password) < 8:
            raise HTTPException(status_code=400, detail="Mật khẩu phải có ít nhất 8 ký tự")
        updates.append("password_hash = %s")
        params.append(hash_password(body.password))
    if body.role is not None and body.role != target["role"]:
        updates.append("role = %s")
        params.append(body.role)
    if body.is_active is not None and body.is_active != target["is_active"]:
        updates.append("is_active = %s")
        params.append(body.is_active)

    if updates:
        updates.append("updated_at = NOW()")
        db.execute(
            f"UPDATE tblUser SET {', '.join(updates)} WHERE id = %s",
            [*params, user_id],
        )

    # Role đổi hoặc khóa → vô hiệu toàn bộ phiên của người đó.
    changed_privilege = (
        (body.role is not None and body.role != target["role"])
        or (body.is_active is not None and body.is_active != target["is_active"])
    )
    if changed_privilege:
        _revoke_tokens(user_id)

    ip = request.client.host if request.client else None
    audit(admin["id"], "user.update", "user", user_id, body.model_dump(exclude_none=True), ip)
    return {"message": "Đã cập nhật tài khoản"}