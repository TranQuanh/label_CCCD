"""
forms.py
========
Router danh mục biểu mẫu (`GET /forms`) + lớp resolve slug→UUID.

Định danh nghiệp vụ của biểu mẫu là `slug` ('atm_open'...), nhưng FK trong DB
trỏ tới `tblFormType.id` (UUID). Mọi nơi khác trong backend khi cần biến một
`form_id` từ client thành UUID phải đi qua `resolve_form_uuid()` — nơi DUY NHẤT
biết hai định danh, tránh lộn xộn.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status

from . import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])


def resolve_form_uuid(slug: str) -> Optional[str]:
    """Map slug → UUID của tblFormType. Trả None nếu không tồn tại/đang tắt."""
    row = db.fetch_one(
        "SELECT id FROM tblFormType WHERE slug = %s AND is_active = TRUE",
        (slug,),
    )
    return row["id"] if row else None


@router.get("")
def list_forms() -> dict:
    """Danh sách biểu mẫu đang kích hoạt (định danh trả về là slug)."""
    rows = db.fetch_all(
        "SELECT id, slug, name, description, requires_front, requires_back, "
        "required_fields, is_active FROM tblFormType WHERE is_active = TRUE "
        "ORDER BY name"
    )
    forms = [
        {
            "id": row["slug"],            # API dùng slug — đây là khoá nghiệp vụ
            "slug": row["slug"],
            "name": row["name"],
            "description": row["description"],
            "requires_front": row["requires_front"],
            "requires_back": row["requires_back"],
            "required_fields": row["required_fields"] or [],
        }
        for row in rows
    ]
    return {"forms": forms}


def get_form_or_404(slug: str) -> dict:
    """Lấy biểu mẫu theo slug; 404 nếu thiếu — dùng cho endpoint cần form."""
    row = db.fetch_one(
        "SELECT id, slug, name, description, requires_front, requires_back, "
        "required_fields FROM tblFormType WHERE slug = %s AND is_active = TRUE",
        (slug,),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy biểu mẫu")
    return row