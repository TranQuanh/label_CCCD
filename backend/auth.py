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
from .audit import DEVICE_INFO_MAX_LEN, IP_MAX_LEN, audit, clip
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

# DEF-14: tên đăng nhập khớp client (`Validators.username` trong
# lib/core/validation/validators.dart): 3–32 ký tự, chữ/số/_, bắt đầu bằng chữ.
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
USERNAME_MSG = "Tên đăng nhập 3–32 ký tự (chữ/số/_), bắt đầu bằng chữ"


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


def _validate_username(username: str) -> Optional[str]:
    """Kiểm tra tên đăng nhập (đã strip) khi đăng ký/tạo tài khoản. Trả thông
    báo lỗi hoặc None. Đăng nhập KHÔNG kiểm (tài khoản cũ vẫn vào được)."""
    if not (3 <= len(username) <= 32) or not USERNAME_RE.match(username):
        return USERNAME_MSG
    return None


def _client_meta(request: Request) -> tuple[str, str]:
    """(ip_address, device_info) cho audit + refresh token."""
    # DEF-05: cắt ngắn cho vừa cột VARCHAR(45)/VARCHAR(255) (tránh lỗi 500).
    ip = clip(request.client.host if request.client else None, IP_MAX_LEN)
    device = clip(request.headers.get("user-agent"), DEVICE_INFO_MAX_LEN)
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
    """Email hoặc username → user. Nếu chứa '@' coi là email.

    DEF-13: email so không phân biệt hoa thường (người dùng gõ chữ hoa vẫn vào
    được). Username giữ so khớp chính xác để không khớp nhầm hai tài khoản cũ
    chỉ khác hoa/thường."""
    if "@" in identifier:
        return db.fetch_one(
            "SELECT * FROM tblUser WHERE lower(email) = lower(%s)", (identifier,)
        )
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
    un_err = _validate_username(username)
    if un_err:
        raise HTTPException(status_code=400, detail=un_err)

    # DEF-13/14: kiểm trùng không phân biệt hoa thường (bằng truy vấn, không
    # thêm index/constraint).
    exists = db.fetch_one(
        "SELECT id FROM tblUser WHERE lower(username) = lower(%s) "
        "OR lower(email) = lower(%s)",
        (username, email),
    )
    if exists:
        raise HTTPException(status_code=409, detail="Tên đăng nhập hoặc email đã tồn tại")

    ip, device = _client_meta(request)
    with db.get_conn() as conn:
        user_id = conn.execute(
            "INSERT INTO tblUser (username, email, password_hash, full_name, role) "
            "VALUES (%s, %s, %s, %s, 'user') RETURNING id",
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
    now = _now_naive()
    if user["locked_until"] and user["locked_until"] > now:
        remaining = user["locked_until"] - now
        minutes = max(1, int(remaining.total_seconds() // 60))
        raise HTTPException(
            status_code=423,
            detail=f"Tài khoản tạm khóa do đăng nhập sai nhiều lần. Thử lại sau {minutes} phút",
        )
    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Tài khoản đã bị khóa")

    # DEF-16: khóa đã hết hạn → bắt đầu đếm lại từ 0 (sai 1 lần sau khi hết
    # khóa chỉ là lần sai thứ 1, không bị khóa lại ngay). Lần ghi bên dưới
    # (sai hoặc đúng mật khẩu) đều đặt lại locked_until.
    prev_fails = user["failed_login_count"] or 0
    if user["locked_until"] is not None:
        prev_fails = 0

    if not verify_password(body.password, user["password_hash"]):
        fails = prev_fails + 1
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
    # device_info client gửi có thể dài → cắt ngắn thay vì từ chối đăng nhập.
    login_device = clip(body.device_info, DEVICE_INFO_MAX_LEN) or device
    with db.get_conn() as conn:
        fresh = conn.execute(
            "SELECT * FROM tblUser WHERE id = %s", (user["id"],)
        ).fetchone()
        tokens = _issue_tokens(conn, fresh, login_device, ip)
        conn.commit()

    audit(user["id"], "auth.login", "user", user["id"],
          {"identifier": identifier, "device": login_device}, ip, device)
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


# DEF-07: đã bỏ GET/PUT/DELETE /auth/profile (DEPRECATED, ghi vào cột cũ
# tblUser.cccd_profile) — Profile CCCD dùng /api/v1/profiles (tblCccdProfile).


@router.post("/change-password")
def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Đổi mật khẩu: xác minh mật khẩu hiện tại, đặt mật khẩu mới, thu hồi MỌI
    phiên kể cả phiên hiện tại (bump token_version + revoke refresh token) —
    access token đang dùng bị từ chối ngay ở request kế tiếp (tok_ver lệch),
    client phải đăng nhập lại bằng mật khẩu mới.

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

    # Đổi hash + tăng token_version → mọi access token cũ (KỂ CẢ token của
    # phiên hiện tại) bị get_current_user từ chối từ request kế tiếp. Request
    # này vẫn trả lời bình thường vì user đã được xác thực trước khi đổi.
    db.execute(
        "UPDATE tblUser SET password_hash = %s, token_version = token_version + 1, "
        "updated_at = NOW() WHERE id = %s",
        (hash_password(body.new_password), user["id"]),
    )
    # Thu hồi hết refresh token đang sống của user, kể cả của phiên hiện tại
    # (bắt buộc đăng nhập lại trên mọi thiết bị).
    db.execute(
        "UPDATE tblRefreshToken SET revoked_at = NOW() "
        "WHERE user_id = %s AND revoked_at IS NULL AND expires_at > NOW()",
        (user["id"],),
    )

    ip, device = _client_meta(request)
    audit(user["id"], "auth.change_password", "user", user["id"],
          None, ip, device)
    return {"message": "Đã đổi mật khẩu. Vui lòng đăng nhập lại bằng mật khẩu mới."}