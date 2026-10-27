"""
audit.py
========
Nhật ký kiểm toán (append-only) + endpoint `GET /audit-logs` (admin).

`audit()` được gọi từ mọi endpoint quan trọng (register/login/logout/đổi role...)
để ghi vết hoạt động. Không có endpoint nào sửa/xoá log.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from . import db
from .deps import get_current_user, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def audit(
    user_id: Optional[str],
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    device_info: Optional[str] = None,
) -> None:
    """Ghi một dòng audit log. Lỗi ghi log KHÔNG làm hỏng nghiệp vụ chính."""
    try:
        db.execute(
            "INSERT INTO tblAuditLog (user_id, action, target_type, target_id, "
            "metadata, ip_address, device_info) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (user_id, action, target_type, target_id,
             __jsonb(metadata), ip_address, device_info),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không ghi được audit log (%s): %s", action, exc)


def __jsonb(value: Optional[dict]) -> Optional[Any]:
    """Chuyển dict sang JSON hợp lệ cho cột JSONB."""
    if value is None:
        return None
    import json

    return json.dumps(value, ensure_ascii=False)


@router.get("", dependencies=[Depends(require_admin)])
def list_audit_logs(
    user_id: Optional[str] = Query(None),
    action_type: Optional[str] = Query(None),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """Danh sách nhật ký kiểm toán (admin-only), filter theo user/action/thời gian."""
    clauses: list[str] = []
    params: list[Any] = []

    if user_id:
        clauses.append("a.user_id = %s")
        params.append(user_id)
    if action_type:
        clauses.append("a.action = %s")
        params.append(action_type)
    if start_date:
        clauses.append("a.created_at >= %s")
        params.append(start_date)
    if end_date:
        clauses.append("a.created_at < %s")
        params.append(end_date)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = db.fetch_all(
        f"SELECT a.id, a.user_id, u.username, u.email, a.action, a.target_type, "
        f"a.target_id, a.metadata, a.ip_address, a.device_info, a.created_at "
        f"FROM tblAuditLog a LEFT JOIN tblUser u ON u.id = a.user_id {where} "
        f"ORDER BY a.created_at DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    return {"logs": rows, "count": len(rows)}