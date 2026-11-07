"""
bootstrap.py
============
Tạo tài khoản admin đầu tiên lúc khởi động (gọi trong lifespan của main.py,
sau db.init_db()).

Chỉ chạy khi đặt đủ cả 3 biến môi trường ADMIN_USERNAME, ADMIN_EMAIL,
ADMIN_PASSWORD (đọc qua config.py). Quy tắc:
  - Đã có user trùng username hoặc email → KHÔNG tạo, KHÔNG đổi mật khẩu,
    KHÔNG tự nâng quyền (tránh chiếm quyền tài khoản của người khác) — chỉ
    ghi log cảnh báo nếu user đó chưa phải admin.
  - Chưa có → tạo user role 'admin' + ghi audit 'user.bootstrap_admin'.
  - Mật khẩu yếu / dữ liệu sai → log cảnh báo và bỏ qua.
Mọi lỗi đều được bắt lại: bootstrap lỗi KHÔNG làm sập server. Không bao giờ
ghi mật khẩu ra log.
"""

from __future__ import annotations

import logging

from . import config, db
from .audit import audit
from .auth import EMAIL_RE, _validate_password, _validate_username
from .security import hash_password

logger = logging.getLogger(__name__)


def bootstrap_admin() -> None:
    """Tạo admin đầu tiên từ env nếu được cấu hình (an toàn khi gọi lại)."""
    username = config.ADMIN_USERNAME
    email = config.ADMIN_EMAIL.lower()
    password = config.ADMIN_PASSWORD
    if not (username and email and password):
        return  # không cấu hình → bỏ qua, không log ồn

    try:
        # DEF-14: cùng quy tắc tên đăng nhập với /auth/register.
        un_err = _validate_username(username)
        if un_err:
            logger.warning("Bỏ qua tạo admin: ADMIN_USERNAME không hợp lệ (%s)", un_err)
            return
        if len(email) > 255 or not EMAIL_RE.match(email):
            logger.warning("Bỏ qua tạo admin: ADMIN_EMAIL không hợp lệ")
            return
        pw_err = _validate_password(password)
        if pw_err:
            logger.warning("Bỏ qua tạo admin: ADMIN_PASSWORD không đạt (%s)", pw_err)
            return

        existing = db.fetch_one(
            "SELECT id, username, role FROM tblUser "
            "WHERE lower(username) = lower(%s) OR lower(email) = lower(%s)",
            (username, email),
        )
        if existing is not None:
            if existing["role"] != "admin":
                logger.warning(
                    "Bỏ qua tạo admin: đã có tài khoản '%s' (role=%s) trùng "
                    "ADMIN_USERNAME/ADMIN_EMAIL — KHÔNG tự nâng quyền. Nâng quyền "
                    "thủ công nếu đây đúng là tài khoản của bạn.",
                    existing["username"], existing["role"],
                )
            else:
                logger.info("Admin '%s' đã tồn tại → không thay đổi", existing["username"])
            return

        with db.get_conn() as conn:
            user_id = conn.execute(
                "INSERT INTO tblUser (username, email, password_hash, full_name, role) "
                "VALUES (%s, %s, %s, %s, 'admin') RETURNING id",
                (username, email, hash_password(password), ""),
            ).fetchone()["id"]
            conn.commit()

        audit(user_id, "user.bootstrap_admin", "user", user_id, {"username": username})
        logger.info("✓ Đã tạo tài khoản admin đầu tiên '%s'", username)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Không tạo được admin đầu tiên: %s", exc)
