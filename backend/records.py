"""
records.py
==========
Router hồ sơ trích xuất (`/scan-records`) — P2: lịch sử từ PostgreSQL.

Đây là nguồn chân lý lịch sử hồ sơ (quyết định #3: server là nguồn chân lý, thiết
bị chỉ cache/mock). Nó thay chỗ lưu RAM trong `sessionStore` phía frontend.

Quyền hạn (RBAC):
  - POST /scan-records       — mọi người dùng đã đăng nhập (user/admin).
  - GET  /scan-records       — hồ sơ của chính mình (đầy đủ nội dung).
  - GET/PATCH /scan-records/{id} — CHỈ chủ sở hữu (kể cả admin cũng chỉ xem/sửa
                               được hồ sơ của chính mình).
  - GET  /scan-records?all_users=true     — admin: danh sách hồ sơ của mọi người
                               dùng, CHỈ thông tin quản lý (mã, biểu mẫu, người
                               tạo, thời gian, trạng thái). KHÔNG trả nội dung
                               CCCD (`extracted_data`) hay trường bổ sung (`supp`):
                               admin không được xem thông tin của người dùng.
  - PATCH /scan-records/{id}/visibility   — admin: ẩn / hiện hồ sơ.

Hồ sơ hiện với chủ hồ sơ khi CẢ hồ sơ đang hiện (`is_hidden = FALSE`) VÀ biểu
mẫu của nó đang hiện (`tblFormType.is_active`). Ngược lại coi như không tồn tại
với chủ hồ sơ (không thấy trong lịch sử, xem/sửa → 404). Dữ liệu không bị xoá.

Mã hồ sơ (`code`) do SERVER cấp (quyết định thiết kế) — client không tự sinh nữa.
Dạng: HS<yyyyMMdd>-<6 chữ số ngẫu nhiên>.

THAY ĐỔI QUAN TRỌNG (theo yêu cầu user):
- Bỏ requirement admin review: bỏ review_status
- Chỉ còn 2 role: admin và user (bỏ viewer, operator → user)
- Xoá chức năng review queue
"""

from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator

from . import db
from .audit import audit
from .deps import get_current_user, parse_uuid, require_admin
from .forms import resolve_form_uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scan-records", tags=["scan-records"])

# Chỉ cho phép các giá trị card_side hợp lệ.
VALID_SIDES = ("front", "back", "both")

# DEF-20: giới hạn kích thước payload hồ sơ/profile (chặn body khổng lồ làm
# phình DB). Không kiểm tra nội dung số CCCD.
MAX_PAYLOAD_KEYS = 50
MAX_PAYLOAD_VALUE_LEN = 1000


def check_payload_limits(value: dict, field_name: str) -> dict:
    """Tối đa 50 khóa, mỗi khóa/giá trị (đổi sang chuỗi để đo) tối đa 1000 ký
    tự. Vượt → ValueError (Pydantic trả 422). Dùng chung với profiles.py."""
    if len(value) > MAX_PAYLOAD_KEYS:
        raise ValueError(f"{field_name} có tối đa {MAX_PAYLOAD_KEYS} trường")
    for key, item in value.items():
        if len(str(key)) > MAX_PAYLOAD_VALUE_LEN:
            raise ValueError(
                f"{field_name}: tên trường dài quá {MAX_PAYLOAD_VALUE_LEN} ký tự"
            )
        text = item if isinstance(item, str) else str(item)
        if len(text) > MAX_PAYLOAD_VALUE_LEN:
            raise ValueError(
                f"{field_name}: giá trị '{str(key)[:50]}' dài quá "
                f"{MAX_PAYLOAD_VALUE_LEN} ký tự"
            )
    return value


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
    is_edited: bool = False

    @field_validator("extracted_data", "supp")
    @classmethod
    def _limit_payload(cls, value: dict, info) -> dict:
        return check_payload_limits(value, info.field_name)


class VisibilityBody(BaseModel):
    """Body cho PATCH /scan-records/{id}/visibility (chỉ admin)."""
    is_hidden: bool


class UpdateRecordBody(BaseModel):
    """Body cho PATCH /scan-records/{id} — cập nhật thông tin đã trích xuất."""
    extracted_data: dict[str, Any] = Field(default_factory=dict)
    supp: dict[str, str] = Field(default_factory=dict)
    parse_ok: bool = True
    is_edited: bool = True  # mặc định True vì user đang sửa tay

    @field_validator("extracted_data", "supp")
    @classmethod
    def _limit_payload(cls, value: dict, info) -> dict:
        return check_payload_limits(value, info.field_name)


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
        "created_at": _created_at_utc(row),
    }


def _created_at_utc(row: dict) -> Optional[str]:
    """DEF-25: created_at dạng ISO UTC có offset ('+00:00') để client đổi về
    giờ máy. Cột là TIMESTAMP không múi giờ ghi bằng NOW() theo múi giờ session
    Postgres, nên `_record_join` đổi sang timestamptz (`created_at_tz`)."""
    aware = row.get("created_at_tz")
    if aware is not None:
        return aware.astimezone(timezone.utc).isoformat()
    naive = row.get("created_at")
    return naive.isoformat() if naive else None


def _serialize_admin(row: dict) -> dict:
    """1 dòng DB → JSON cho admin: CHỈ thông tin quản lý, không có nội dung
    CCCD (`extracted_data`) hay trường bổ sung (`supp`)."""
    return {
        "id": str(row["id"]),
        "code": row.get("code"),
        "form_id": row.get("form_slug"),
        "form_name": row.get("form_name"),
        "form_active": row.get("form_active") is not False,
        "is_edited": bool(row.get("is_edited")),
        "is_hidden": bool(row.get("is_hidden")),
        "owner_id": str(row["user_id"]) if row.get("user_id") else None,
        "owner_username": row.get("owner_username"),
        "created_at": _created_at_utc(row),
    }


def _record_join() -> str:
    """SELECT ... FROM bảng gốc + biểu mẫu + chủ hồ sơ."""
    return (
        f"SELECT r.id, r.code, r.user_id, r.extracted_data, r.supp, "
        f"r.card_side, r.parse_ok, r.is_edited, r.is_hidden, r.created_at, "
        f"(r.created_at AT TIME ZONE current_setting('TimeZone')) AS created_at_tz, "
        f"f.slug AS form_slug, f.name AS form_name, f.is_active AS form_active, "
        f"u.username AS owner_username, u.full_name AS owner_name "
        f"FROM tblScanRecord r "
        f"LEFT JOIN tblFormType f ON f.id = r.form_type_id "
        f"LEFT JOIN tblUser u ON u.id = r.user_id"
    )


def _admin_join() -> str:
    """SELECT cho admin — KHÔNG lấy cột nội dung (extracted_data, supp)."""
    return (
        f"SELECT r.id, r.code, r.user_id, r.is_edited, r.is_hidden, r.created_at, "
        f"(r.created_at AT TIME ZONE current_setting('TimeZone')) AS created_at_tz, "
        f"f.slug AS form_slug, f.name AS form_name, f.is_active AS form_active, "
        f"u.username AS owner_username "
        f"FROM tblScanRecord r "
        f"LEFT JOIN tblFormType f ON f.id = r.form_type_id "
        f"LEFT JOIN tblUser u ON u.id = r.user_id"
    )


# Hồ sơ hiện với chủ hồ sơ: chính hồ sơ đang hiện VÀ biểu mẫu đang hiện
# (hồ sơ không gắn biểu mẫu — dữ liệu cũ — vẫn hiện).
_VISIBLE_TO_OWNER = "r.is_hidden = FALSE AND (f.id IS NULL OR f.is_active = TRUE)"


def _get_record_accessible(record_id: str, user: dict) -> dict:
    """
    Lấy 1 record của CHÍNH user (kể cả admin — admin không được xem nội dung hồ
    sơ của người khác). 404 nếu không tồn tại / không phải chủ / đang bị ẩn
    (hồ sơ ẩn hoặc biểu mẫu ẩn) — không lộ sự tồn tại.
    Id sai định dạng UUID → 404 (DEF-23, thay vì lỗi 500 từ PostgreSQL).
    """
    record_id = parse_uuid(record_id)
    if record_id is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")
    row = db.fetch_one(
        f"{_record_join()} WHERE r.id = %s AND r.user_id = %s AND {_VISIBLE_TO_OWNER}",
        (record_id, user["id"]),
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy hồ sơ")
    return row


def _get_record_admin(record_id: str) -> dict:
    """Admin: thông tin quản lý của một hồ sơ bất kỳ (không có nội dung)."""
    row = db.fetch_one(f"{_admin_join()} WHERE r.id = %s", (record_id,))
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

    Server sinh mã hồ sơ.
    Trường bổ sung `supp` lưu riêng; `extracted_data` là JSONB tiếng Việt snake_case.
    Mọi người dùng đã đăng nhập (user/admin) đều có thể submit.
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


_ADMIN_STATUS_FILTERS = ("all", "visible", "hidden", "form_hidden")


@router.get("")
def list_records(
    request: Request,
    user: dict = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    all_users: bool = Query(False, description="Chỉ admin: hồ sơ của mọi người dùng"),
    user_id: Optional[str] = Query(None, description="Admin: lọc theo người tạo"),
    form_id: Optional[str] = Query(None, max_length=100, description="Admin: lọc theo slug biểu mẫu"),
    status_filter: str = Query("all", alias="status", description="Admin: all|visible|hidden|form_hidden"),
    q: Optional[str] = Query(None, max_length=100, description="Admin: tìm mã hồ sơ / tên đăng nhập"),
    start_date: Optional[date] = Query(None, description="Admin: từ ngày (YYYY-MM-DD)"),
    end_date: Optional[date] = Query(None, description="Admin: đến hết ngày (YYYY-MM-DD)"),
) -> dict:
    """
    - Mặc định: lịch sử hồ sơ của CHÍNH người gọi (đầy đủ nội dung), trừ hồ sơ
      đang ẩn hoặc thuộc biểu mẫu đang ẩn.
    - Admin + (`all_users=true` hoặc `user_id=`): danh sách QUẢN LÝ hồ sơ của mọi
      người, kèm bộ lọc. KHÔNG trả nội dung CCCD / trường bổ sung. Trả thêm
      `total` để phân trang.
    """
    is_admin = user["role"] == "admin"
    if is_admin and (all_users or user_id):
        return _list_records_admin(
            limit=limit, offset=offset, user_id=user_id, form_id=form_id,
            status_filter=status_filter, q=q,
            start_date=start_date, end_date=end_date,
        )

    rows = db.fetch_all(
        f"{_record_join()} WHERE r.user_id = %s AND {_VISIBLE_TO_OWNER} "
        f"ORDER BY r.created_at DESC LIMIT %s OFFSET %s",
        (user["id"], limit, offset),
    )
    return {
        "records": [_serialize(r) for r in rows],
        "count": len(rows),
    }


def _list_records_admin(
    *,
    limit: int,
    offset: int,
    user_id: Optional[str],
    form_id: Optional[str],
    status_filter: str,
    q: Optional[str],
    start_date: Optional[date],
    end_date: Optional[date],
) -> dict:
    """Danh sách quản lý hồ sơ cho admin (không có nội dung hồ sơ)."""
    clauses: list[str] = []
    params: list[Any] = []

    if user_id:
        # DEF-23: user_id sai định dạng UUID → 400 thay vì lỗi 500.
        parsed = parse_uuid(user_id)
        if parsed is None:
            raise HTTPException(status_code=400, detail="user_id không hợp lệ")
        clauses.append("r.user_id = %s")
        params.append(parsed)
    if form_id:
        clauses.append("f.slug = %s")
        params.append(form_id.strip())
    if status_filter not in _ADMIN_STATUS_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"status phải là: {', '.join(_ADMIN_STATUS_FILTERS)}",
        )
    if status_filter == "visible":
        clauses.append(_VISIBLE_TO_OWNER)
    elif status_filter == "hidden":
        clauses.append("r.is_hidden = TRUE")
    elif status_filter == "form_hidden":
        clauses.append("f.is_active = FALSE")
    if q and q.strip():
        clauses.append("(r.code ILIKE %s OR u.username ILIKE %s)")
        pattern = f"%{q.strip()}%"
        params.extend([pattern, pattern])
    if start_date:
        clauses.append("r.created_at >= %s")
        params.append(start_date)
    if end_date:
        # Tính TRỌN ngày cuối (đến trước 00:00 ngày hôm sau).
        clauses.append("r.created_at < %s")
        params.append(end_date + timedelta(days=1))

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.fetch_one(
        "SELECT COUNT(*) AS n FROM tblScanRecord r "
        "LEFT JOIN tblFormType f ON f.id = r.form_type_id "
        f"LEFT JOIN tblUser u ON u.id = r.user_id{where}",
        params,
    )["n"]
    rows = db.fetch_all(
        f"{_admin_join()}{where} ORDER BY r.created_at DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return {
        "records": [_serialize_admin(r) for r in rows],
        "count": len(rows),
        "total": int(total),
    }


# Xoá endpoint review-queue vì không cần chức năng review
# Xoá endpoint review vì không cần admin duyệt


@router.patch("/{record_id}")
def update_record(
    record_id: str,
    body: UpdateRecordBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Cập nhật thông tin một hồ sơ đã gửi (CHỈ chủ sở hữu).

    Chỉ cho phép sửa `extracted_data`, `supp`, `parse_ok`, `is_edited`.
    Không thay đổi `code`, `form_type_id`, `created_at`.
    `is_edited` tự động đặt True để đánh dấu đã qua tay người dùng.
    """
    # Kiểm tra record tồn tại và user có quyền (id sai định dạng → 404)
    record_id = str(_get_record_accessible(record_id, user)["id"])

    if not body.extracted_data:
        raise HTTPException(status_code=400, detail="extracted_data không được rỗng")

    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")

    db.execute(
        "UPDATE tblScanRecord SET extracted_data = %s, supp = %s, "
        "parse_ok = %s, is_edited = %s, updated_at = NOW() WHERE id = %s",
        (_jsonb(body.extracted_data), _jsonb(body.supp),
         body.parse_ok, body.is_edited, record_id),
    )

    audit(user["id"], "record.update", "record", record_id,
          {"is_edited": body.is_edited}, ip, device)

    # Trả về record sau khi cập nhật
    row = _get_record_accessible(record_id, user)
    return _serialize(row)


@router.patch("/{record_id}/visibility")
def set_record_visibility(
    record_id: str,
    body: VisibilityBody,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    """
    Admin ẩn / hiện một hồ sơ. Hồ sơ bị ẩn không còn xuất hiện trong lịch sử
    của chủ hồ sơ và chủ hồ sơ không xem/sửa được; dữ liệu vẫn giữ nguyên.
    """
    record_id = parse_uuid(record_id)
    if record_id is None:
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
    # Trả thông tin quản lý (không có nội dung hồ sơ).
    return _serialize_admin(_get_record_admin(record_id))


@router.get("/{record_id}")
def get_record(
    record_id: str,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """Chi tiết một hồ sơ (CHỈ chủ sở hữu — admin cũng không xem được hồ sơ
    của người khác)."""
    row = _get_record_accessible(record_id, user)
    return _serialize(row)