"""
audit.py
========
Nhật ký kiểm toán (append-only) + endpoint `GET /audit-logs` (admin).

`audit()` được gọi từ mọi endpoint quan trọng (register/login/logout/đổi role...)
để ghi vết hoạt động. Không có endpoint nào sửa/xoá log.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from . import db
from .deps import get_current_user, parse_uuid, require_admin

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audit-logs", tags=["audit"])

# Độ dài tối đa cột (schema.sql): ip_address VARCHAR(45), device_info VARCHAR(255).
IP_MAX_LEN = 45
DEVICE_INFO_MAX_LEN = 255


def clip(value: Optional[str], max_len: int) -> Optional[str]:
    """Cắt chuỗi về tối đa `max_len` ký tự (DEF-05: tránh lỗi 500 do vượt độ
    dài cột). None giữ nguyên None."""
    if value is None:
        return None
    return value[:max_len]


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
             __jsonb(metadata), clip(ip_address, IP_MAX_LEN),
             clip(device_info, DEVICE_INFO_MAX_LEN)),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không ghi được audit log (%s): %s", action, exc)


def __jsonb(value: Optional[dict]) -> Optional[Any]:
    """Chuyển dict sang JSON hợp lệ cho cột JSONB."""
    if value is None:
        return None
    import json

    return json.dumps(value, ensure_ascii=False)


# Nhóm hành động cho bộ lọc (khớp tiền tố của `action`).
ACTION_GROUPS = {
    "auth": "auth.",
    "user": "user.",
    "record": "record.",
    "profile": "profile.",
    "form": "form.",
}

# Sự kiện bảo mật: đăng nhập sai, đổi mật khẩu, mọi thay đổi tài khoản do admin,
# ẩn/hiện hồ sơ và biểu mẫu.
SECURITY_ACTIONS = (
    "auth.login_failed",
    "auth.change_password",
    "auth.change_password_failed",
    "user.create",
    "user.update",
    "user.unlock",
    "user.revoke_sessions",
    "user.bootstrap_admin",
    "record.hide",
    "record.show",
    "form.hide",
    "form.show",
)


@router.get("", dependencies=[Depends(require_admin)])
def list_audit_logs(
    user_id: Optional[str] = Query(None, description="Người thực hiện"),
    target_id: Optional[str] = Query(None, description="Đối tượng bị tác động"),
    action_type: Optional[str] = Query(None, max_length=100),
    action_group: Optional[str] = Query(None, description="auth|user|record|profile|form"),
    security_only: bool = Query(False, description="Chỉ sự kiện bảo mật"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None, description="Tính trọn ngày cuối"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> dict:
    """
    Nhật ký kiểm toán (admin-only). Lọc theo người thực hiện, đối tượng, hành
    động / nhóm hành động, sự kiện bảo mật, khoảng ngày. Trả `total` để phân
    trang và `target_label` (tên đăng nhập / mã hồ sơ / tên biểu mẫu) để hiển
    thị thay cho UUID. Không có nội dung CCCD trong nhật ký.
    """
    clauses: list[str] = []
    params: list[Any] = []

    if user_id:
        # DEF-23: user_id sai định dạng UUID → 400 thay vì 500 từ PostgreSQL.
        parsed = parse_uuid(user_id)
        if parsed is None:
            raise HTTPException(status_code=400, detail="user_id không hợp lệ")
        clauses.append("a.user_id = %s")
        params.append(parsed)
    if target_id:
        parsed_target = parse_uuid(target_id)
        if parsed_target is None:
            raise HTTPException(status_code=400, detail="target_id không hợp lệ")
        clauses.append("a.target_id = %s")
        params.append(parsed_target)
    if action_type:
        clauses.append("a.action = %s")
        params.append(action_type)
    if action_group:
        prefix = ACTION_GROUPS.get(action_group)
        if prefix is None:
            raise HTTPException(
                status_code=400,
                detail=f"action_group phải là: {', '.join(ACTION_GROUPS)}",
            )
        clauses.append("a.action LIKE %s")
        params.append(prefix + "%")
    if security_only:
        clauses.append("a.action = ANY(%s)")
        params.append(list(SECURITY_ACTIONS))
    if start_date:
        clauses.append("a.created_at >= %s")
        params.append(start_date)
    if end_date:
        # DEF-28: tính TRỌN ngày cuối (đến trước 00:00 ngày hôm sau).
        clauses.append("a.created_at < %s")
        params.append(end_date + timedelta(days=1))

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    total = db.fetch_one(
        f"SELECT COUNT(*) AS n FROM tblAuditLog a {where}", params
    )["n"]
    rows = db.fetch_all(
        f"SELECT a.id, a.user_id, u.username, u.email, a.action, a.target_type, "
        f"a.target_id, a.metadata, a.ip_address, a.device_info, a.created_at, "
        f"(a.created_at AT TIME ZONE current_setting('TimeZone')) AS created_at_tz, "
        f"CASE a.target_type "
        f"  WHEN 'user' THEN tu.username "
        f"  WHEN 'record' THEN tr.code "
        f"  WHEN 'form' THEN tf.name "
        f"  ELSE NULL END AS target_label "
        f"FROM tblAuditLog a "
        f"LEFT JOIN tblUser u ON u.id = a.user_id "
        f"LEFT JOIN tblUser tu ON a.target_type = 'user' AND tu.id = a.target_id "
        f"LEFT JOIN tblScanRecord tr ON a.target_type = 'record' AND tr.id = a.target_id "
        f"LEFT JOIN tblFormType tf ON a.target_type = 'form' AND tf.id = a.target_id "
        f"{where} ORDER BY a.created_at DESC LIMIT %s OFFSET %s",
        [*params, limit, offset],
    )
    logs = []
    for r in rows:
        aware = r.pop("created_at_tz", None)
        if aware is not None:
            # Thời điểm UTC có offset để client đổi về giờ máy (giống DEF-25).
            r["created_at"] = aware.astimezone(timezone.utc).isoformat()
        logs.append(r)
    return {"logs": logs, "count": len(logs), "total": int(total)}