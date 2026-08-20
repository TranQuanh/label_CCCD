"""
forms.py
========
Router danh mục biểu mẫu (`GET /forms`) + lớp resolve slug→UUID.

Định danh nghiệp vụ của biểu mẫu là `slug` ('atm_open'...), nhưng FK trong DB
trỏ tới `tblFormType.id` (UUID). Mọi nơi khác trong backend khi cần biến một
`form_id` từ client thành UUID phải đi qua `resolve_form_uuid()` — nơi DUY NHẤT
biết hai định danh, tránh lộn xộn.

P2: `required_fields` là JSONB `[{key,label,hint}, ...]` — /forms là nguồn duy
nhất cung cấp metadata trường bổ sung; frontend render động theo nó (kFormTypes
chỉ còn dành cho chế độ mock).
"""

from __future__ import annotations

import logging
import uuid as uuid_mod
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from . import db
from .deps import require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/forms", tags=["forms"])


def resolve_form_uuid(slug: str) -> Optional[str]:
    """Map slug → UUID của tblFormType. Trả None nếu không tồn tại/đang tắt."""
    row = db.fetch_one(
        "SELECT id FROM tblFormType WHERE slug = %s AND is_active = TRUE",
        (slug,),
    )
    return row["id"] if row else None


class SuppFieldDef(BaseModel):
    key: str = Field(min_length=1, max_length=50)
    label: str = Field(min_length=1, max_length=255)
    hint: str = Field(default="", max_length=255)


class FormBody(BaseModel):
    slug: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    requires_front: bool = True
    requires_back: bool = False
    required_fields: list[SuppFieldDef] = []
    is_active: bool = True


class UpdateFormBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    requires_front: Optional[bool] = None
    requires_back: Optional[bool] = None
    required_fields: Optional[list[SuppFieldDef]] = None
    is_active: Optional[bool] = None


def _serialize(row: dict) -> dict:
    """1 dòng DB → JSON API (id = slug, required_fields = list {key,label,hint})."""
    return {
        "id": row["slug"],
        "slug": row["slug"],
        "name": row["name"],
        "description": row["description"],
        "requires_front": row["requires_front"],
        "requires_back": row["requires_back"],
        "required_fields": row["required_fields"] or [],
        "is_active": row["is_active"],
    }


@router.get("")
def list_forms() -> dict:
    """Danh sách biểu mẫu đang kích hoạt (định danh trả về là slug)."""
    rows = db.fetch_all(
        "SELECT id, slug, name, description, requires_front, requires_back, "
        "required_fields, is_active FROM tblFormType WHERE is_active = TRUE "
        "ORDER BY name"
    )
    return {"forms": [_serialize(r) for r in rows]}


def get_form_or_404(slug: str) -> dict:
    """Lấy biểu mẫu theo slug; 404 nếu thiếu — dùng cho endpoint cần form."""
    row = db.fetch_one(
        "SELECT id, slug, name, description, requires_front, requires_back, "
        "required_fields, is_active FROM tblFormType WHERE slug = %s AND is_active = TRUE",
        (slug,),
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy biểu mẫu")
    return row


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(require_admin)])
def create_form(body: FormBody) -> dict:
    """Admin tạo loại biểu mẫu mới (required_fields có đủ key/label/hint)."""
    exists = db.fetch_one("SELECT id FROM tblFormType WHERE slug = %s", (body.slug.strip(),))
    if exists:
        raise HTTPException(status_code=409, detail="Slug đã tồn tại")
    fields = [f.model_dump() for f in body.required_fields]
    db.execute(
        "INSERT INTO tblFormType (slug, name, description, requires_front, "
        "requires_back, required_fields, is_active) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
        (body.slug.strip(), body.name.strip(), body.description.strip(),
         body.requires_front, body.requires_back, _to_jsonb(fields), body.is_active),
    )
    return {"message": "Đã tạo biểu mẫu", "slug": body.slug.strip()}


@router.put("/{slug}", dependencies=[Depends(require_admin)])
def update_form(slug: str, body: UpdateFormBody) -> dict:
    """Admin sửa biểu mẫu (đổi tên/mô tả/cờ yêu cầu 2 mặt/các trường bổ sung)."""
    exists = db.fetch_one("SELECT id FROM tblFormType WHERE slug = %s", (slug,))
    if exists is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy biểu mẫu")

    updates: list[str] = []
    params: list = []
    if body.name is not None:
        updates.append("name = %s")
        params.append(body.name.strip())
    if body.description is not None:
        updates.append("description = %s")
        params.append(body.description.strip())
    if body.requires_front is not None:
        updates.append("requires_front = %s")
        params.append(body.requires_front)
    if body.requires_back is not None:
        updates.append("requires_back = %s")
        params.append(body.requires_back)
    if body.required_fields is not None:
        updates.append("required_fields = %s")
        params.append(_to_jsonb([f.model_dump() for f in body.required_fields]))
    if body.is_active is not None:
        updates.append("is_active = %s")
        params.append(body.is_active)

    if updates:
        db.execute(
            f"UPDATE tblFormType SET {', '.join(updates)} WHERE slug = %s",
            [*params, slug],
        )
    return {"message": "Đã cập nhật biểu mẫu", "slug": slug}


def _to_jsonb(value) -> str:
    """List[dict] → chuỗi JSON hợp lệ cho cột JSONB (dùng json.dumps)."""
    import json

    return json.dumps(value, ensure_ascii=False)