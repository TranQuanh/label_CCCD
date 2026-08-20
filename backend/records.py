"""
records.py
==========
Router hồ sơ trích xuất (`/scan-records`) — P2: lịch sử từ PostgreSQL + duyệt.

Đây là nguồn chân lý lịch sử hồ sơ (quyết định #3: server là nguồn chân lý, thiết
bị chỉ cache/mock). Nó thay chỗ lưu RAM trong `sessionStore` phía frontend.

Quyền hạn (RBAC):
  - POST /scan-records       — operator+ (viewer không gửi hồ sơ).
  - GET  /scan-records       — operator/admin: hồ sơ của chính mình; admin có thể
                               truyền `?user_id=` để xem của người khác. viewer:
                               chỉ record ĐÃ DUYỆT qua `v_scan_record_masked` (số
                               CCCD bị che) — chốt mâu thuẫn Viewer vs RLS.
  - GET  /scan-records/review-queue — operator+: danh sách chờ duyệt (pending).
  - PATCH /scan-records/{id}/review — operator+: duyệt record → 'reviewed'.
  - GET  /scan-records/{id}  — chủ sở hữu / admin (viewer: qua view đã duyệt).

Mã hồ sơ (`code`) do SERVER cấp (quyết định thiết kế) — client không tự sinh nữa.
Dạng: HS<yyyyMMdd>-<6 chữ số ngẫu nhiên>.
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
from .deps import get_current_user, require_role
from .forms import resolve_form_uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan-records", tags=["scan-records"])

# Chỉ cho phép các giá trị card_side hợp lệ.
VALID_SIDES = ("front", "back", "both")


def _now_naive() -> datetime:
    """`NOW()` trong PostgreSQL trả timestamp KHÔNG múi giờ — dùng UTC naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _jsonb(value) -> Optional[str]:
    """Dict → chuỗi JSON hợp lệ cho cột JSONB (giống audit.__jsonb)."""
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
    # Trường hợp cực hiếm trùng liên tiếp — thêm hậu tố ms để đảm bảo duy nhất.
    return prefix + f"{now.microsecond % 1000000:06d}"


# ── Models ─────────────────────────────────────────────────────────────────
class SubmitRecordBody(BaseModel):
    form_id: str = Field(min_length=1, max_length=100)  # slug
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    supp: dict[str, str] = Field(default_factory=dict)
    card_side: str = Field(default="both", max_length=10)
    parse_ok: bool = True
    raw_output: Optional[str] = None
    is_edited: bool = False


class ReviewBody(BaseModel):
    review_status: str = Field(default="reviewed", max_length=20)


# ── Helpers ─────────────────────────────────────────────────────────────────
def _serialize(row: dict, masked: bool = False) -> dict:
    """1 dòng DB → JSON API. `masked=True` (viewer) → cột đã che sẵn."""
    return {
        "id": row["id"],
        "code": row.get("code"),
        "form_id": row.get("form_slug"),
        "form_name": row.get("form_name"),
        "review_status": row["review_status"],
        "extracted_data": row["extracted_data"],
        "supp": row.get("supp") or {},
        "card_side": row.get("card_side"),
        "parse_ok": row.get("parse_ok"),
        "is_edited": row.get("is_edited"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }


def _record_join(masked: bool) -> str:
    """SELECT ... FROM nguồn dữ liệu (bảng gốc hoặc view che cho viewer)."""
    source = "v_scan_record_masked" if masked else "tblScanRecord"
    return (
        f"SELECT r.id, r.code, r.review_status, r.extracted_data, r.supp, "
        f"r.card_side, r.parse_ok, r.is_edited, r.created_at, "
        f"f.slug AS form_slug, f.name AS form_name "
        f"FROM {source} r LEFT JOIN tblFormType f ON f.id = r.form_type_id"
    )


def _get_record_accessible(record_id: str, user: dict, masked: bool = False) -> dict:
    """
    Lấy 1 record mà user được phép xem: owner/admin (hoặc viewer qua view đã
    duyệt). 404 nếu không tồn tại HOẶC không có quyền (không lộ sự tồn tại).
    """
    role = user["role"]
    if masked:
        query = f"{_record_join(masked=True)} WHERE r.id = %s"
        params = (record_id,)
    elif role == "admin":
        query = f"{_record_join(masked=False)} WHERE r.id = %s"
        params = (record_id,)
    else:
        query = f"{_record_join(masked=False)} WHERE r.id = %s AND r.user_id = %s"
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
    user: dict = Depends(require_role("operator")),
) -> dict:
    """
    Gửi một hồ sơ trích xuất lên server.

    Server sinh mã hồ sơ, đặt `review_status='pending'` (chờ duyệt). Trường bổ
    sung `supp` lưu riêng; `extracted_data` là JSONB tiếng Việt snake_case.
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
        "INSERT INTO tblScanRecord (code, user_id, form_type_id, review_status, "
        "extracted_data, supp, confidence_scores, parse_ok, raw_output, is_edited, card_side) "
        "VALUES (%s, %s, %s, 'pending', %s, %s, NULL, %s, %s, %s, %s) RETURNING id",
        (code, user["id"], form_uuid, _jsonb(body.extracted_data),
         _jsonb(body.supp), body.parse_ok, body.raw_output, body.is_edited, body.card_side),
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
) -> dict:
    """
    Lịch sử hồ sơ từ PostgreSQL.

    viewer: đọc qua `v_scan_record_masked` (chỉ record đã duyệt, số CCCD che).
    operator: hồ sơ của chính mình. admin: của mình, hoặc `?user_id=` của khác.
    """
    role = user["role"]
    masked = role == "viewer"

    clauses: list[str] = []
    params: list[Any] = []
    if masked:
        query = f"{_record_join(masked=True)}"
    elif role == "admin":
        query = f"{_record_join(masked=False)}"
        if user_id:
            clauses.append("r.user_id = %s")
            params.append(user_id)
        else:
            clauses.append("r.user_id = %s")
            params.append(user["id"])
    else:  # operator
        query = f"{_record_join(masked=False)}"
        clauses.append("r.user_id = %s")
        params.append(user["id"])

    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY r.created_at DESC LIMIT %s OFFSET %s"

    rows = db.fetch_all(query, [*params, limit, offset])
    return {
        "records": [_serialize(r, masked=masked) for r in rows],
        "count": len(rows),
        "masked": masked,
    }


@router.get("/review-queue")
def review_queue(
    request: Request,
    user: dict = Depends(require_role("operator")),
    form_id: Optional[str] = Query(None),
    card_side: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    Hàng đợi duyệt: các record `pending` (operator/admin). Filter theo biểu mẫu
    hoặc mặt thẻ nếu cần.
    """
    clauses = ["r.review_status = 'pending'"]
    params: list[Any] = []
    if form_id:
        clauses.append("f.slug = %s")
        params.append(form_id)
    if card_side:
        if card_side not in VALID_SIDES:
            raise HTTPException(status_code=400, detail=f"card_side phải là: {', '.join(VALID_SIDES)}")
        clauses.append("r.card_side = %s")
        params.append(card_side)

    query = (
        f"{_record_join(masked=False)} WHERE {' AND '.join(clauses)} "
        f"ORDER BY r.created_at ASC LIMIT %s OFFSET %s"
    )
    rows = db.fetch_all(query, [*params, limit, offset])
    return {"records": [_serialize(r) for r in rows], "count": len(rows)}


@router.patch("/{record_id}/review")
def review_record(
    record_id: str,
    body: ReviewBody,
    request: Request,
    user: dict = Depends(require_role("operator")),
) -> dict:
    """
    Duyệt một record: `pending → reviewed`. Chỉ operator/admin. Sau khi duyệt,
    record xuất hiện trong lịch sử của viewer (qua view che số CCCD).
    """
    if body.review_status not in ("reviewed", "pending"):
        raise HTTPException(status_code=400, detail="review_status phải là 'reviewed' hoặc 'pending'")

    row = db.fetch_one(
        "SELECT id, code, review_status, user_id FROM tblScanRecord WHERE id = %s",
        (record_id,),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")

    if body.review_status == row["review_status"]:
        return {"message": "Hồ sơ đã ở trạng thái này", "record_id": record_id,
                "review_status": row["review_status"]}

    db.execute(
        "UPDATE tblScanRecord SET review_status = %s, updated_at = NOW() WHERE id = %s",
        (body.review_status, record_id),
    )
    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")
    audit(user["id"], "record.review", "record", record_id,
          {"code": row["code"], "to": body.review_status}, ip, device)
    return {"message": "Đã cập nhật trạng thái duyệt", "record_id": record_id,
            "review_status": body.review_status}


@router.get("/{record_id}")
def get_record(
    record_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Chi tiết một hồ sơ (chủ sở hữu / admin; viewer chỉ xem được bản đã duyệt)."""
    masked = user["role"] == "viewer"
    row = _get_record_accessible(record_id, user, masked=masked)
    return _serialize(row, masked=masked)