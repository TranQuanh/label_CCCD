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
from .auth import _validate_password, _validate_username
from .deps import ROLE_LEVELS, parse_uuid, require_admin
from .security import hash_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"], dependencies=[Depends(require_admin)])

VALID_ROLES = tuple(ROLE_LEVELS.keys())


class CreateUserBody(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)
    role: str = Field(default="user")


class UpdateUserBody(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=255)
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


def _client_ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _get_target(user_id: str) -> tuple[str, dict]:
    """(id chuẩn hoá, dòng tblUser). Id sai định dạng / không tồn tại → 404."""
    parsed = parse_uuid(user_id)
    if parsed is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    target = db.fetch_one("SELECT * FROM tblUser WHERE id = %s", (parsed,))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    return parsed, target


@router.get("")
def list_users() -> dict:
    """Danh sách tài khoản (không trả password_hash) + số hồ sơ đã tạo."""
    rows = db.fetch_all(
        "SELECT u.id, u.username, u.email, u.full_name, u.role, u.is_active, "
        "u.failed_login_count, u.locked_until, u.created_at, u.updated_at, "
        "(SELECT COUNT(*) FROM tblScanRecord r WHERE r.user_id = u.id) AS record_count "
        "FROM tblUser u ORDER BY u.created_at DESC"
    )
    return {"users": rows, "count": len(rows)}


@router.get("/{user_id}")
def get_user(user_id: str) -> dict:
    """
    Chi tiết TÀI KHOẢN (admin). Chỉ thông tin tài khoản và hoạt động — KHÔNG có
    Profile CCCD hay nội dung hồ sơ (admin không được xem thông tin người dùng).
    """
    parsed, target = _get_target(user_id)
    stats = db.fetch_one(
        "SELECT "
        "(SELECT COUNT(*) FROM tblScanRecord WHERE user_id = %s) AS record_count, "
        "(SELECT COUNT(*) FROM tblScanRecord WHERE user_id = %s AND is_hidden) "
        "  AS hidden_record_count, "
        "(SELECT COUNT(*) FROM tblRefreshToken WHERE user_id = %s "
        "  AND revoked_at IS NULL AND expires_at > NOW()) AS active_sessions, "
        "(SELECT MAX(created_at) FROM tblAuditLog WHERE user_id = %s "
        "  AND action = 'auth.login') AS last_login_at",
        (parsed, parsed, parsed, parsed),
    )
    return {
        "id": str(target["id"]),
        "username": target["username"],
        "email": target["email"],
        "full_name": target["full_name"],
        "role": target["role"],
        "is_active": target["is_active"],
        "failed_login_count": target["failed_login_count"],
        "locked_until": target["locked_until"],
        "created_at": target["created_at"],
        "updated_at": target["updated_at"],
        "record_count": int(stats["record_count"] or 0),
        "hidden_record_count": int(stats["hidden_record_count"] or 0),
        "active_sessions": int(stats["active_sessions"] or 0),
        "last_login_at": stats["last_login_at"],
    }


@router.post("/{user_id}/unlock")
def unlock_user(user_id: str, request: Request, admin: dict = Depends(require_admin)) -> dict:
    """Gỡ khóa tạm do đăng nhập sai nhiều lần (không đổi trạng thái khóa bởi admin)."""
    parsed, _ = _get_target(user_id)
    db.execute(
        "UPDATE tblUser SET failed_login_count = 0, locked_until = NULL, "
        "updated_at = NOW() WHERE id = %s",
        (parsed,),
    )
    audit(admin["id"], "user.unlock", "user", parsed, None, _client_ip(request))
    return {"message": "Đã gỡ khóa đăng nhập tạm thời"}


@router.post("/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: str, request: Request, admin: dict = Depends(require_admin)
) -> dict:
    """Đăng xuất tài khoản khỏi MỌI thiết bị (thu hồi mọi token)."""
    parsed, _ = _get_target(user_id)
    if str(parsed) == str(admin["id"]):
        raise HTTPException(
            status_code=400,
            detail="Không thể tự đăng xuất mọi thiết bị ở đây — dùng Đăng xuất",
        )
    _revoke_tokens(parsed)
    audit(admin["id"], "user.revoke_sessions", "user", parsed, None, _client_ip(request))
    return {"message": "Đã đăng xuất tài khoản khỏi mọi thiết bị"}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_user(body: CreateUserBody, request: Request, admin: dict = Depends(require_admin)):
    """Admin tạo tài khoản mới (không cần người dùng đăng ký)."""
    if body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ (chấp nhận: {', '.join(VALID_ROLES)})")
    # DEF-17: cùng quy tắc mật khẩu với /auth/register (≥8 ký tự, chữ + số).
    pw_err = _validate_password(body.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    username = body.username.strip()
    email = body.email.strip().lower()
    # DEF-14: cùng quy tắc tên đăng nhập với /auth/register.
    un_err = _validate_username(username)
    if un_err:
        raise HTTPException(status_code=400, detail=un_err)
    # DEF-13/14: kiểm trùng không phân biệt hoa thường (bằng truy vấn).
    exists = db.fetch_one(
        "SELECT id FROM tblUser WHERE lower(username) = lower(%s) "
        "OR lower(email) = lower(%s)",
        (username, email),
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
    # DEF-23: id sai định dạng UUID → 404 thay vì lỗi 500 từ PostgreSQL.
    parsed_id = parse_uuid(user_id)
    if parsed_id is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")
    user_id = parsed_id
    target = db.fetch_one("SELECT * FROM tblUser WHERE id = %s", (user_id,))
    if target is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài khoản")

    # ── Guards ──────────────────────────────────────────────────────────────
    if body.role is not None and body.role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail=f"Role không hợp lệ (chấp nhận: {', '.join(VALID_ROLES)})")

    # Không cho admin tự hạ quyền chính mình.
    # (psycopg trả cột UUID dạng uuid.UUID → so sánh dạng chuỗi.)
    is_self = str(user_id) == str(admin["id"])
    if is_self and body.role is not None and body.role != "admin":
        raise HTTPException(status_code=400, detail="Không thể hạ quyền của chính bạn")
    # Không cho admin tự khóa chính mình.
    if is_self and body.is_active is False:
        raise HTTPException(status_code=400, detail="Không thể khóa tài khoản của chính bạn")

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
        pw_err = _validate_password(body.password)
        if pw_err:
            raise HTTPException(status_code=400, detail=pw_err)
        updates.append("password_hash = %s")
        params.append(hash_password(body.password))
    if body.role is not None and body.role != target["role"]:
        updates.append("role = %s")
        params.append(body.role)
    if body.is_active is not None and body.is_active != target["is_active"]:
        updates.append("is_active = %s")
        params.append(body.is_active)
    # DEF-16: admin mở khóa (is_active=True) → xoá luôn bộ đếm sai mật khẩu và
    # khóa tạm, để người dùng đăng nhập lại từ đầu.
    if body.is_active is True:
        updates.append("failed_login_count = 0")
        updates.append("locked_until = NULL")

    if updates:
        updates.append("updated_at = NOW()")
        db.execute(
            f"UPDATE tblUser SET {', '.join(updates)} WHERE id = %s",
            [*params, user_id],
        )

    # Role đổi, khóa/mở khóa HOẶC reset mật khẩu → vô hiệu toàn bộ phiên của
    # người đó (DEF-38: reset mật khẩu thường dùng để cứu tài khoản bị chiếm,
    # nên token cũ của kẻ chiếm phải mất hiệu lực).
    changed_privilege = (
        (body.role is not None and body.role != target["role"])
        or (body.is_active is not None and body.is_active != target["is_active"])
        or (body.password is not None)
    )
    if changed_privilege:
        _revoke_tokens(user_id)

    ip = request.client.host if request.client else None
    # Không bao giờ ghi mật khẩu (dạng rõ) vào audit log — chỉ đánh dấu có reset.
    meta = body.model_dump(exclude_none=True, exclude={"password"})
    if body.password is not None:
        meta["password_reset"] = True
    audit(admin["id"], "user.update", "user", user_id, meta, ip)
    return {"message": "Đã cập nhật tài khoản"}