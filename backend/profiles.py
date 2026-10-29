"""
profiles.py
===========
Router Profile CCCD (`/profiles`) — mỗi người dùng có NHIỀU profile CCCD
(thông tin thẻ của chính họ/người thân). Các profile ngang hàng, không có
profile "mặc định": khi điền biểu mẫu người dùng tự chọn profile cần dùng.

Đây là nguồn chân lý (bảng `tblCccdProfile`); thiết bị chỉ cache. Khác với
thông tin tài khoản (tblUser) — router này không đụng tới tài khoản/RBAC.

Quyền hạn: mọi endpoint yêu cầu đăng nhập và CHỈ thao tác profile của chính
user hiện tại. Profile không tồn tại hoặc thuộc người khác → 404 (không lộ sự
tồn tại).
  - GET    /profiles        — danh sách profile (created_at tăng dần).
  - POST   /profiles        — tạo profile.
  - PUT    /profiles/{id}   — cập nhật dữ liệu profile.
  - DELETE /profiles/{id}   — xoá profile.

Số CCCD (`data.so_cccd`, so sánh sau khi chỉ giữ chữ số) không được trùng giữa
các profile của cùng một user → 409. Thao tác ghi khoá dòng tblUser của user
(`FOR UPDATE`) để kiểm trùng + ghi là nguyên tử, không bị race.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import db
from .audit import audit
from .deps import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/profiles", tags=["profiles"])

_DUPLICATE_MSG = "Số CCCD này đã có trong profile khác"
_NOT_FOUND_MSG = "Không tìm thấy profile"
_EMPTY_MSG = "Dữ liệu profile không được rỗng"
_COLUMNS = "id, data, created_at, updated_at"


# ── Models ─────────────────────────────────────────────────────────────────
class ProfileBody(BaseModel):
    data: dict[str, Any] = Field(default_factory=dict)


# ── Helpers ─────────────────────────────────────────────────────────────────
def _jsonb(value) -> Optional[str]:
    """Dict → chuỗi JSON hợp lệ cho cột JSONB (giống records._jsonb)."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _client_meta(request: Request) -> tuple[Optional[str], Optional[str]]:
    """(ip_address, device_info) cho audit."""
    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")
    return ip, device


def _norm_id(value) -> str:
    """Chuẩn hoá số CCCD để so trùng: chỉ giữ chữ số (khớp
    `Validators.normalizeIdNumber` phía client)."""
    return re.sub(r"\D", "", str(value or ""))


def _lock_user(conn, user_id) -> None:
    """Khoá dòng tblUser của user trong transaction hiện tại — tuần tự hoá các
    thao tác ghi profile của cùng một user (tránh 2 request song song cùng vượt
    kiểm trùng số CCCD)."""
    conn.execute("SELECT id FROM tblUser WHERE id = %s FOR UPDATE", (user_id,))


def _parse_uuid(profile_id: str) -> str:
    """Id sai định dạng UUID → 404 (thay vì lỗi 500 từ PostgreSQL)."""
    try:
        return str(uuid.UUID(profile_id))
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=404, detail=_NOT_FOUND_MSG)


def _serialize(row: dict) -> dict:
    """1 dòng DB → JSON API."""
    data = row.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except ValueError:
            data = {}
    return {
        "id": str(row["id"]),
        "data": data or {},
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
    }


def _ensure_unique_cccd(conn, user_id, data: dict, exclude_id: Optional[str] = None) -> None:
    """Số CCCD trùng với profile khác của cùng user → 409.

    Chạy trên `conn` của transaction ghi (sau `_lock_user`) để kiểm trùng và
    ghi là nguyên tử."""
    target = _norm_id(data.get("so_cccd"))
    if not target:
        return
    rows = conn.execute(
        "SELECT id, data->>'so_cccd' AS so_cccd FROM tblCccdProfile WHERE user_id = %s",
        (user_id,),
    ).fetchall()
    for r in rows:
        if exclude_id is not None and str(r["id"]) == exclude_id:
            continue
        if _norm_id(r.get("so_cccd")) == target:
            raise HTTPException(status_code=409, detail=_DUPLICATE_MSG)


# ── Endpoints ──────────────────────────────────────────────────────────────
@router.get("")
def list_profiles(user: dict = Depends(get_current_user)) -> dict:
    """Danh sách Profile CCCD của user hiện tại (cũ → mới)."""
    rows = db.fetch_all(
        f"SELECT {_COLUMNS} FROM tblCccdProfile WHERE user_id = %s ORDER BY created_at ASC",
        (user["id"],),
    )
    return {"profiles": [_serialize(r) for r in rows]}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Tạo Profile CCCD mới."""
    if not body.data:
        raise HTTPException(status_code=400, detail=_EMPTY_MSG)

    ip, device = _client_meta(request)
    with db.get_conn() as conn:
        # Khoá theo user rồi mới kiểm trùng (lỗi → pool tự rollback).
        _lock_user(conn, user["id"])
        _ensure_unique_cccd(conn, user["id"], body.data)
        row = conn.execute(
            f"INSERT INTO tblCccdProfile (user_id, data) VALUES (%s, %s) RETURNING {_COLUMNS}",
            (user["id"], _jsonb(body.data)),
        ).fetchone()
        conn.commit()

    # Không ghi số CCCD/họ tên vào audit (dữ liệu cá nhân).
    audit(user["id"], "profile.create", "cccd_profile", row["id"], None, ip, device)
    return _serialize(row)


@router.put("/{profile_id}")
def update_profile(
    profile_id: str,
    body: ProfileBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Cập nhật dữ liệu một Profile CCCD của user hiện tại."""
    profile_id = _parse_uuid(profile_id)
    if not body.data:
        raise HTTPException(status_code=400, detail=_EMPTY_MSG)

    ip, device = _client_meta(request)
    with db.get_conn() as conn:
        _lock_user(conn, user["id"])
        _ensure_unique_cccd(conn, user["id"], body.data, exclude_id=profile_id)
        row = conn.execute(
            f"UPDATE tblCccdProfile SET data = %s, updated_at = NOW() "
            f"WHERE id = %s AND user_id = %s RETURNING {_COLUMNS}",
            (_jsonb(body.data), profile_id, user["id"]),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND_MSG)
        conn.commit()

    audit(user["id"], "profile.update", "cccd_profile", profile_id, None, ip, device)
    return _serialize(row)


@router.delete("/{profile_id}")
def delete_profile(
    profile_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Xoá một Profile CCCD của user hiện tại."""
    profile_id = _parse_uuid(profile_id)
    ip, device = _client_meta(request)
    with db.get_conn() as conn:
        deleted = conn.execute(
            "DELETE FROM tblCccdProfile WHERE id = %s AND user_id = %s RETURNING id",
            (profile_id, user["id"]),
        ).fetchone()
        if deleted is None:
            raise HTTPException(status_code=404, detail=_NOT_FOUND_MSG)
        conn.commit()

    audit(user["id"], "profile.delete", "cccd_profile", profile_id, None, ip, device)
    return {"message": "Đã xoá profile"}
