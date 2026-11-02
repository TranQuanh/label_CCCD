"""
records.py
==========
Router hồ sơ trích xuất (`/scan-records`) — lịch sử từ PostgreSQL.

Đây là nguồn chân lý lịch sử hồ sơ (server là nguồn chân lý, thiết bị chỉ cache/mock).

Quyền hạn (RBAC):
  - POST /scan-records       — user / admin: gửi hồ sơ trích xuất.
  - GET  /scan-records       — user: danh sách hồ sơ của chính mình (không bao gồm hồ sơ bị ẩn).
                               admin: mặc định xem của chính mình; có thể truyền `?user_id=` 
                               để xem của người khác hoặc `?all_users=true` để xem toàn bộ.
  - GET  /scan-records/{id}  — chủ sở hữu / admin.
  - PATCH /scan-records/{id} — chủ sở hữu / admin: cập nhật dữ liệu trích xuất.
  - PATCH /scan-records/{id}/visibility — admin: ẩn / hiện hồ sơ. Hồ sơ bị ẩn
                               không hiện trong lịch sử của chủ hồ sơ (404); admin vẫn thấy.

Mã hồ sơ (`code`) do SERVER cấp: HS<yyyyMMdd>-<6 chữ số ngẫu nhiên>.
"""

from __future__ import annotations

import json
import logging
import random
import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from . import db
from .audit import audit
from .deps import get_current_user, require_admin
from .forms import resolve_form_uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan-records", tags=["scan-records"])

VALID_SIDES = ("front", "back", "both")


def _now_naive() -> datetime:
    """`NOW()` trong PostgreSQL trả timestamp KHÔNG múi giờ — dùng UTC naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _jsonb(value) -> Optional[str]:
    """Dict → chuỗi JSON hợp lệ cho cột JSONB."""
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False)


def _generate_code() -> str:
    """Mã hồ sơ do server cấp: HS<yyyyMMdd>-<6 chữ số>. Retry nếu trùng."""
    now = datetime.now()
    prefix = f"HS{now.strftime('%Y%m%d')}-"
    for _ in range(5):
        candidate = prefix + f"{random.randint(0, 999999):06d}"
        exists = db.fetch_one("SELECT id FROM tblScanRecord WHERE code = %s", (candidate,))
        if exists is None:
            return candidate
    return prefix + f"{now.microsecond % 1000000:06d}"


# ── Models ─────────────────────────────────────────────────────────────────
class SubmitRecordBody(BaseModel):
    form_id: str = Field(min_length=1, max_length=100)
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    supp: dict[str, str] = Field(default_factory=dict)
    card_side: str = Field(default="both", max_length=10)
    parse_ok: bool = True
    is_edited: bool = False


class VisibilityBody(BaseModel):
    """Body cho PATCH /scan-records/{id}/visibility (chỉ admin)."""
    is_hidden: bool


class UpdateRecordBody(BaseModel):
    """Body cho PATCH /scan-records/{id} — cập nhật thông tin đã trích xuất.

    DEF-15: supp và parse_ok là Optional — chỉ ghi đè khi client truyền rõ ràng.
    Nếu không truyền supp thì giữ nguyên giá trị cũ trong DB.
    """
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    supp: Optional[dict[str, str]] = None   # None = giữ nguyên giá trị cũ
    parse_ok: Optional[bool] = None         # None = giữ nguyên giá trị cũ
    is_edited: bool = True


# ── Helpers ─────────────────────────────────────────────────────────────────
def _serialize(row: dict) -> dict:
    """1 dòng DB → JSON API."""
    return {
        "id": row["id"],
        "code": row.get("code"),
        "form_id": row.get("form_slug"),
        "form_name": row.get("form_name"),
        "extracted_data": row["extracted_data"],
        "supp": row.get("supp") or {},
        "card_side": row.get("card_side"),
        "parse_ok": row.get("parse_ok"),
        "is_edited": row.get("is_edited"),
        "is_hidden": bool(row.get("is_hidden")),
        "owner_id": str(row["user_id"]) if row.get("user_id") else None,
        "owner_username": row.get("owner_username"),
        "owner_name": row.get("owner_name"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _record_join() -> str:
    """SELECT ... FROM bảng gốc + biểu mẫu + chủ hồ sơ."""
    return (
        f"SELECT r.id, r.code, r.user_id, r.extracted_data, r.supp, "
        f"r.card_side, r.parse_ok, r.is_edited, r.is_hidden, r.created_at, "
        f"f.slug AS form_slug, f.name AS form_name, "
        f"u.username AS owner_username, u.full_name AS owner_name "
        f"FROM tblScanRecord r "
        f"LEFT JOIN tblFormType f ON f.id = r.form_type_id "
        f"LEFT JOIN tblUser u ON u.id = r.user_id"
    )


def _get_record_accessible(record_id: str, user: dict) -> dict:
    """
    Lấy 1 record mà user được phép xem: owner/admin.
    Hồ sơ bị admin ẩn coi như không tồn tại với người dùng thông thường (chủ hồ sơ).
    """
    role = user["role"]
    if role == "admin":
        query = f"{_record_join()} WHERE r.id = %s"
        params = (record_id,)
    else:
        query = (f"{_record_join()} WHERE r.id = %s AND r.user_id = %s "
                 f"AND r.is_hidden = FALSE")
        params = (record_id, user["id"])

    row = db.fetch_one(query, params)
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")
    return row


# ── Endpoints ──────────────────────────────────────────────────────────────
@router.post("", status_code=status.HTTP_201_CREATED)
def submit_record(
    body: SubmitRecordBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Gửi một hồ sơ trích xuất lên server.
    Mọi tài khoản đã đăng nhập (user/admin) đều có quyền submit.
    """
    form_uuid = resolve_form_uuid(body.form_id.strip())
    if form_uuid is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy biểu mẫu")

    if body.card_side not in VALID_SIDES:
        raise HTTPException(status_code=400, detail=f"card_side phải là: {', '.join(VALID_SIDES)}")
    if not body.extracted_data:
        raise HTTPException(status_code=400, detail="extracted_data không được rỗng")

    code = _generate_code()
    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")

    record_id = db.fetch_one(
        "INSERT INTO tblScanRecord (code, user_id, form_type_id, "
        "extracted_data, supp, parse_ok, is_edited, card_side) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (code, user["id"], form_uuid, _jsonb(body.extracted_data),
         _jsonb(body.supp), body.parse_ok, body.is_edited, body.card_side),
    )["id"]

    audit(user["id"], "record.create", "record", record_id,
          {"code": code, "form_id": body.form_id.strip()}, ip, device)
    return {"message": "Đã gửi hồ sơ", "record_id": record_id, "code": code}


@router.get("")
def list_records(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = Query(None, description="Chỉ admin: xem hồ sơ của user khác"),
    all_users: bool = Query(False, description="Chỉ admin: xem hồ sơ của mọi người dùng"),
) -> dict:
    """
    Lịch sử hồ sơ từ PostgreSQL.

    user: hồ sơ của chính mình (loại bỏ các hồ sơ đã bị admin ẩn).
    admin: hồ sơ của mình; `?user_id=` của user khác; `?all_users=true` của mọi người.
    """
    role = user["role"]

    clauses: list[str] = []
    params: list[Any] = []
    query = f"{_record_join()}"

    if role == "admin":
        if all_users:
            pass
        elif user_id:
            clauses.append("r.user_id = %s")
            params.append(user_id)
        else:
            clauses.append("r.user_id = %s")
            params.append(user["id"])
    else:  # user
        clauses.append("r.user_id = %s")
        params.append(user["id"])
        clauses.append("r.is_hidden = FALSE")

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY r.created_at DESC LIMIT %s OFFSET %s"

    rows = db.fetch_all(query, [*params, limit, offset])
    return {
        "records": [_serialize(r) for r in rows],
        "count": len(rows),
    }


@router.patch("/{record_id}")
def update_record(
    record_id: str,
    body: UpdateRecordBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Cập nhật thông tin một hồ sơ đã gửi (chủ sở hữu / admin)."""
    _get_record_accessible(record_id, user)

    if not body.extracted_data:
        raise HTTPException(status_code=400, detail="extracted_data không được rỗng")

    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")

    # DEF-15: chỉ ghi đè supp/parse_ok khi client truyền rõ ràng (không None).
    # Dùng COALESCE để giữ nguyên giá trị cũ nếu tham số là NULL.
    db.execute(
        "UPDATE tblScanRecord SET "
        "extracted_data = %s, "
        "supp = COALESCE(%s, supp), "
        "parse_ok = COALESCE(%s, parse_ok), "
        "is_edited = %s, "
        "updated_at = NOW() "
        "WHERE id = %s",
        (_jsonb(body.extracted_data),
         _jsonb(body.supp) if body.supp is not None else None,
         body.parse_ok,
         body.is_edited,
         record_id),
    )

    audit(user["id"], "record.update", "record", record_id,
          {"is_edited": body.is_edited}, ip, device)

    row = _get_record_accessible(record_id, user)
    return _serialize(row)


@router.patch("/{record_id}/visibility")
def set_record_visibility(
    record_id: str,
    body: VisibilityBody,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    """Admin ẩn / hiện một hồ sơ."""
    try:
        record_id = str(uuid_mod.UUID(record_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")

    with db.get_conn() as conn:
        row = conn.execute(
            "UPDATE tblScanRecord SET is_hidden = %s, updated_at = NOW() "
            "WHERE id = %s RETURNING id",
            (body.is_hidden, record_id),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")
        conn.commit()

    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")
    audit(admin["id"], "record.hide" if body.is_hidden else "record.show",
          "record", record_id, None, ip, device)
    return _serialize(_get_record_accessible(record_id, admin))


@router.get("/{record_id}")
def get_record(
    record_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Chi tiết một hồ sơ (chủ sở hữu / admin)."""
    row = _get_record_accessible(record_id, user)
    return _serialize(row)