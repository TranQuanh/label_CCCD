"""
auth.py
=======
Router xác thực `/auth/*` — đăng ký, đăng nhập, refresh, đăng xuất, thông tin
user hiện tại.

Quy tắc bảo mật (khớp tài liệu):
  - Đăng nhập bằng `identifier` = EMAIL hoặc USERNAME (backend tự phát hiện).
  - Mật khẩu ≥8 ký tự, gồm cả chữ và số.
  - 5 lần sai liên tiếp → khóa 15 phút (`failed_login_count`/`locked_until`).
  - Access token: JWT TTL 1h (chứa tok_ver). Refresh token: ngẫu nhiên, DB chỉ
    lưu hash, TTL 30 ngày.
  - Logout: revoke refresh + đưa jti access vào Redis blacklist.
  - Mọi sự kiện quan trọng đều ghi audit log.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from . import config, db, redis_client
from .audit import audit
from .deps import get_current_user
from .security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Email tối thiểu hợp lệ (đủ chặt để chặn rác, không quá chặt cho miền quốc tế).
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# Hash mật khẩu "dummy" cố định — dùng khi user không tồn tại để thời gian phản
# hồi giống hệt khi user tồn tại, tránh kẻ tấn công dò tên đăng nhập qua timing.
_DUMMY_HASH = hash_password("dummy-password-1234")


def _now_naive() -> datetime:
    """`NOW()` trong PostgreSQL trả timestamp KHÔNG múi giờ — mọi so sánh thời
    gian trong code dùng UTC naive để không lệch kiểu aware/naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Models ─────────────────────────────────────────────────────────────────
class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: str = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(default="", max_length=255)


class LoginBody(BaseModel):
    identifier: str = Field(max_length=255)
    password: str = Field(max_length=128)
    device_info: Optional[str] = None


class RefreshBody(BaseModel):
    refresh_token: str


class ChangePasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def _validate_password(password: str) -> Optional[str]:
    """Kiểm tra mật khẩu: ≥8 ký tự và có cả chữ lẫn số. Trả thông báo lỗi hoặc None."""
    if len(password) < 8:
        return "Mật khẩu phải có ít nhất 8 ký tự"
    if not re.search(r"[a-zA-Z]", password) or not re.search(r"[0-9]", password):
        return "Mật khẩu phải gồm cả chữ và số"
    return None


def _client_meta(request: Request) -> tuple[str, str]:
    """(ip_address, device_info) cho audit + refresh token."""
    ip = request.client.host if request.client else None
    device = request.headers.get("user-agent")
    return ip, device


def _issue_tokens(
    conn, user: dict, device_info: Optional[str], ip: Optional[str]
) -> dict:
    """
    Tạo cặp token (access + refresh) và lưu refresh hash vào DB trong cùng
    transaction với `conn` (đảm bảo register/login là một thao tác nguyên tử).
    """
    access_token, jti = create_access_token(user["id"], user["role"], user["token_version"])
    refresh_token = generate_refresh_token()
    expires_at = _now_naive() + timedelta(days=config.REFRESH_TTL_DAYS)
    conn.execute(
        "INSERT INTO tblRefreshToken (user_id, token_hash, device_info, ip_address, expires_at) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user["id"], hash_refresh_token(refresh_token), device_info, ip, expires_at),
    )
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": config.ACCESS_TTL_MIN * 60,
    }


def _find_user_by_identifier(identifier: str) -> Optional[dict]:
    """Email hoặc username → user. Nếu chứa '@' coi là email."""
    if "@" in identifier:
        return db.fetch_one("SELECT * FROM tblUser WHERE email = %s", (identifier,))
    return db.fetch_one("SELECT * FROM tblUser WHERE username = %s", (identifier,))


# ── Endpoints ──────────────────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterBody, request: Request) -> dict:
    """
    Đăng ký tài khoản mới và tự động đăng nhập (cấp cặp token).

    Body: {username, email, password, full_name}
    """
    if not EMAIL_RE.match(body.email):
        raise HTTPException(status_code=400, detail="Email không hợp lệ")
    pw_err = _validate_password(body.password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    username = body.username.strip()
    email = body.email.strip().lower()
    full_name = body.full_name.strip()

    exists = db.fetch_one(
        "SELECT id FROM tblUser WHERE username = %s OR email = %s",
        (username, email),
    )
    if exists:
        raise HTTPException(status_code=409, detail="Tên đăng nhập hoặc email đã tồn tại")

    ip, device = _client_meta(request)
    with db.get_conn() as conn:
        user_id = conn.execute(
            "INSERT INTO tblUser (username, email, password_hash, full_name, role) "
            "VALUES (%s, %s, %s, %s, 'operator') RETURNING id",
            (username, email, hash_password(body.password), full_name),
        ).fetchone()["id"]
        user = conn.execute(
            "SELECT * FROM tblUser WHERE id = %s", (user_id,)
        ).fetchone()
        tokens = _issue_tokens(conn, user, device, ip)
        conn.commit()

    audit(user_id, "auth.register", "user", user_id, {"username": username}, ip, device)
    return {
        "message": "Đăng ký thành công",
        "data": {
            "user_id": user_id,
            "username": username,
            "email": email,
            "full_name": full_name,
            "role": user["role"],
            **tokens,
        },
    }


@router.post("/login")
def login(body: LoginBody, request: Request) -> dict:
    """
    Đăng nhập bằng email HOẶC username.

    Body: {identifier, password, device_info}
    """
    ip, device = _client_meta(request)
    identifier = body.identifier.strip()

    user = _find_user_by_identifier(identifier)
    if user is None:
        # Không lộ thông tin: luôn chạy verify để thời gian phản hồi không lộ
        # việc user tồn tại hay không.
        verify_password(body.password, _DUMMY_HASH)
        audit(None, "auth.login_failed", "user", None,
              {"identifier": identifier, "reason": "not_found"}, ip, device)
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    # Khóa tài khoản
    if user["locked_until"] and user["locked_until"] > _now_naive():
        remaining = user["locked_until"] - _now_naive()
        minutes = max(1, int(remaining.total_seconds() // 60))
        raise HTTPException(
            status_code=423,
            detail=f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau {minutes} phút",
        )
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")

    if not verify_password(body.password, user["password_hash"]):
        fails = (user["failed_login_count"] or 0) + 1
        locked_until = None
        if fails >= config.MAX_LOGIN_FAILS:
            locked_until = _now_naive() + timedelta(minutes=config.LOCK_MINUTES)
        db.execute(
            "UPDATE tblUser SET failed_login_count = %s, locked_until = %s WHERE id = %s",
            (fails, locked_until, user["id"]),
        )
        audit(user["id"], "auth.login_failed", "user", user["id"],
              {"attempt": fails}, ip, device)
        if locked_until:
            raise HTTPException(
                status_code=423,
                detail=f"Đăng nhập sai quá {config.MAX_LOGIN_FAILS} lần. "
                       f"Tài khoản khóa {config.LOCK_MINUTES} phút",
            )
        raise HTTPException(status_code=401, detail="Sai tên đăng nhập hoặc mật khẩu")

    # Đúng mật khẩu → reset bộ đếm, cấp token
    db.execute(
        "UPDATE tblUser SET failed_login_count = 0, locked_until = NULL WHERE id = %s",
        (user["id"],),
    )
    with db.get_conn() as conn:
        fresh = conn.execute(
            "SELECT * FROM tblUser WHERE id = %s", (user["id"],)
        ).fetchone()
        tokens = _issue_tokens(conn, fresh, body.device_info or device, ip)
        conn.commit()

    audit(user["id"], "auth.login", "user", user["id"],
          {"identifier": identifier, "device": body.device_info or device}, ip, device)
    return {
        "message": "Đăng nhập thành công",
        "data": {
            "user_id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"],
            **tokens,
        },
    }


@router.post("/refresh")
def refresh(body: RefreshBody, request: Request) -> dict:
    """
    Cấp access token mới từ refresh token hợp lệ (chưa revoked, chưa hết hạn).
    """
    token_hash = hash_refresh_token(body.refresh_token)
    row = db.fetch_one(
        "SELECT rt.id, rt.expires_at, rt.revoked_at, rt.user_id, "
        "u.role, u.is_active, u.token_version "
        "FROM tblRefreshToken rt JOIN tblUser u ON u.id = rt.user_id "
        "WHERE rt.token_hash = %s",
        (token_hash,),
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Refresh token không hợp lệ")
    if row["revoked_at"]:
        raise HTTPException(status_code=401, detail="Refresh token đã bị thu hồi")
    if row["expires_at"] < _now_naive():
        raise HTTPException(status_code=401, detail="Refresh token đã hết hạn")
    if not row["is_active"]:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")

    ip, device = _client_meta(request)
    access_token, _ = create_access_token(row["user_id"], row["role"], row["token_version"])
    # Refresh token cũ vẫn dùng được nhiều lần tới khi hết hạn/revoke — đúng
    # mô hình trong tài liệu (rotation phức tạp hơn, gác lại).
    return {
        "message": "Đã cấp access token mới",
        "data": {
            "access_token": access_token,
            "token_type": "bearer",
            "expires_in": config.ACCESS_TTL_MIN * 60,
        },
    }


@router.post("/logout")
def logout(request: Request, user: dict = Depends(get_current_user)) -> dict:
    """
    Đăng xuất: revoke mọi refresh token của user + blacklist jti của access token
    hiện tại (TTL = thời gian access còn sống).
    """
    ip, device = _client_meta(request)

    # Revoke toàn bộ refresh token chưa hết hạn của user.
    db.execute(
        "UPDATE tblRefreshToken SET revoked_at = NOW() "
        "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()",
        (user["id"],),
    )

    # Blacklist access token hiện tại. Lấy jti từ Authorization header bằng cách
    # giải mã lại (get_current_user đã kiểm tra rồi, chỉ cần payload).
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        from .security import decode_access_token

        payload = decode_access_token(authorization.split(" ", 1)[1])
        if payload:
            exp_ts = payload["exp"]
            now_ts = _now_naive().timestamp()
            ttl = max(1, int(exp_ts - now_ts))
            redis_client.blacklist_jti(payload["jti"], ttl)

    audit(user["id"], "auth.logout", "user", user["id"], None, ip, device)
    return {"message": "Đã đăng xuất"}


@router.get("/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    """Thông tin user hiện tại (token hợp lệ là đủ)."""
    return {
        "user_id": user["id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "email": user["email"],
        "role": user["role"],
    }


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Đổi mật khẩu: xác minh mật khẩu hiện tại, đặt mật khẩu mới, thu hồi mọi
    phiên khác (bump token_version + revoke refresh token) — token hiện tại vẫn
    dùng được tới khi hết hạn.

    P2 quyết định: KHÔNG dùng OTP (không có hạ tầng SMS/email thật) — chỉ cần
    người dùng chứng minh mật khẩu hiện tại.
    """
    pw_err = _validate_password(body.new_password)
    if pw_err:
        raise HTTPException(status_code=400, detail=pw_err)

    # Verify mật khẩu hiện tại. Đúng thì không lộ gì; sai thì 400 rõ ràng.
    if not verify_password(body.current_password, user["password_hash"]):
        audit(user["id"], "auth.change_password_failed", "user", user["id"],
              None, *_client_meta(request))
        raise HTTPException(status_code=400, detail="Mật khẩu hiện tại không đúng")

    if body.current_password == body.new_password:
        raise HTTPException(status_code=400, detail="Mật khẩu mới trùng mật khẩu hiện tại")

    # Đổi hash + tăng token_version → mọi JWT/refresh cũ của CÁC PHIÊN KHÁC bị
    # vô hiệu. Phiên hiện tại tiếp tục sống (token_version không nằm trong
    # kiểm tra của chính request này sau khi đổi — không ảnh hưởng tới trả lời).
    db.execute(
        "UPDATE tblUser SET password_hash = %s, token_version = token_version + 1, "
        "updated_at = NOW() WHERE id = %s",
        (hash_password(body.new_password), user["id"]),
    )
    # Revoke các refresh token KHÁC phiên hiện tại. Cách đơn giản và an toàn:
    # thu hồi hết refresh token đang sống (bắt buộc đăng nhập lại sau này).
    db.execute(
        "UPDATE tblRefreshToken SET revoked_at = NOW() "
        "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()",
        (user["id"],),
    )

    ip, device = _client_meta(request)
    audit(user["id"], "auth.change_password", "user", user["id"],
          None, ip, device)
    return {"message": "Đã đổi mật khẩu. Vui lòng đăng nhập lại bằng mật khẩu mới."}