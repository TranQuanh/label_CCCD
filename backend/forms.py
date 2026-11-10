"""
forms.py
========
Router danh mục biểu mẫu (`/forms`) + lớp resolve slug→UUID.

Định danh nghiệp vụ của biểu mẫu là `slug` ('atm_open'...), nhưng FK trong DB
trỏ tới `tblFormType.id` (UUID). Mọi nơi khác trong backend khi cần biến một
`form_id` từ client thành UUID phải đi qua `resolve_form_uuid()` — nơi DUY NHẤT
biết hai định danh, tránh lộn xộn.

`required_fields` là JSONB `[{key,label,hint}, ...]`; `layout` là JSONB mô tả
cách hiển thị trường bổ sung. Nội dung biểu mẫu CHỈ được định nghĩa trong
`schema.sql` (seed) — app/admin KHÔNG được tạo hay sửa biểu mẫu. Admin chỉ được
ẨN / HIỆN biểu mẫu:
  - GET   /forms                    — công khai: biểu mẫu đang hiện.
  - GET   /forms/all                — admin: mọi biểu mẫu (kể cả đang ẩn) + số hồ sơ.
  - PATCH /forms/{slug}/visibility  — admin: ẩn / hiện biểu mẫu.

Biểu mẫu bị ẩn: người dùng không thấy trong danh mục, không tạo được hồ sơ mới
(`resolve_form_uuid` trả None), VÀ hồ sơ cũ của biểu mẫu đó bị ẩn khỏi lịch sử
của chủ hồ sơ (xem records.py). Dữ liệu không bị xoá; hiện lại thì hồ sơ hiện lại.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from . import db
from .audit import audit
from .deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])

_COLUMNS = (
    "id, slug, name, description, requires_front, requires_back, "
    "required_fields, layout, is_active"
)


def resolve_form_uuid(slug: str) -> Optional[str]:
    """Map slug → UUID của tblFormType. Trả None nếu không tồn tại/đang ẩn."""
    row = db.fetch_one(
        "SELECT id FROM tblFormType WHERE slug = %s AND is_active = TRUE",
        (slug,),
    )
    return row["id"] if row else None


class FormVisibilityBody(BaseModel):
    """Body cho PATCH /forms/{slug}/visibility (chỉ admin)."""
    is_active: bool


def _serialize(row: dict) -> dict:
    """1 dòng DB → JSON API (id = UUID thực tế, slug = khóa nghiệp vụ)."""
    data = {
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "description": row["description"],
        "requires_front": row["requires_front"],
        "requires_back": row["requires_back"],
        "required_fields": row["required_fields"] or [],
        "layout": row["layout"] or [],
        "is_active": row["is_active"],
    }
    if "record_count" in row:
        data["record_count"] = int(row["record_count"] or 0)
    return data


@router.get("")
def list_forms() -> dict:
    """Danh sách biểu mẫu đang hiện (định danh trả về là slug)."""
    rows = db.fetch_all(
        f"SELECT {_COLUMNS} FROM tblFormType WHERE is_active = TRUE ORDER BY name"
    )
    return {"forms": [_serialize(r) for r in rows]}


@router.get("/all", dependencies=[Depends(require_admin)])
def list_all_forms() -> dict:
    """Admin: mọi biểu mẫu (kể cả đang ẩn) kèm số hồ sơ đã tạo."""
    rows = db.fetch_all(
        f"SELECT f.id, f.slug, f.name, f.description, f.requires_front, "
        f"f.requires_back, f.required_fields, f.layout, f.is_active, "
        f"(SELECT COUNT(*) FROM tblScanRecord r WHERE r.form_type_id = f.id) "
        f"AS record_count "
        f"FROM tblFormType f ORDER BY f.name"
    )
    return {"forms": [_serialize(r) for r in rows]}


@router.patch("/{slug}/visibility")
def set_form_visibility(
    slug: str,
    body: FormVisibilityBody,
    request: Request,
    admin: dict = Depends(require_admin),
) -> dict:
    """Admin ẩn / hiện một biểu mẫu (không sửa nội dung biểu mẫu)."""
    with db.get_conn() as conn:
        row = conn.execute(
            f"UPDATE tblFormType SET is_active = %s WHERE slug = %s "
            f"RETURNING {_COLUMNS}",
            (body.is_active, slug),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                detail="Không tìm thấy biểu mẫu")
        conn.commit()

    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")
    audit(admin["id"], "form.show" if body.is_active else "form.hide",
          "form", str(row["id"]), {"slug": slug, "name": row["name"]}, ip, device)
    return _serialize(row)
