"""
smoke_test.py
=============
Smoke test P1+P2 — chạy trực tiếp qua FastAPI TestClient (không cần uvicorn).

Cover:
  P1 — register → login sai 5 lần (lock) → login đúng → me → refresh → logout →
       kiểm access cũ bị blacklist → admin tạo user + đổi role → token cũ bị
       từ chối → audit-logs đủ sự kiện.
  Quality — /api/v1/quality-check: 401 không token, 200 có khóa 'available'
       (có/không cài OpenCV đều qua), side sai → 400.
  P2 — /forms trả metadata JSONB {key,label,hint}; admin chỉ ẩn/hiện biểu mẫu
       (không tạo/sửa); admin không xem nội dung hồ sơ người khác;
       gửi hồ sơ (POST /scan-records) nhận mã server; lịch sử từ PostgreSQL;
       Profile CCCD (/profiles); đổi mật khẩu (bỏ OTP, verify mật khẩu hiện tại).
  Role chỉ còn 'admin' và 'user'.

CẢNH BÁO: test TRUNCATE các bảng tblUser/tblScanRecord/... → CHỈ chạy trên DB
riêng cho test. Tên database trong DATABASE_URL BẮT BUỘC kết thúc bằng '_test'
(vd. cccd_test), nếu không test dừng ngay (exit 2) trước khi đụng dữ liệu.

Tạo DB test một lần (psql hoặc pgAdmin):
  CREATE DATABASE cccd_test;
(Schema tự tạo khi chạy test — không cần chạy schema.sql bằng tay.)

Chạy:
  $env:SKIP_MODEL_LOAD='1'
  $env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cccd_test'
  python backend/smoke_test.py
"""

from __future__ import annotations

import os
import sys

# Thêm thư mục gốc dự án vào sys.path để import package `backend` (như uvicorn
# chạy `backend.main:app`).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SKIP_MODEL_LOAD", "1")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cccd_test")

# DEF-22: chặn chạy nhầm vào DB dev/thật (test TRUNCATE toàn bộ tài khoản, hồ
# sơ). Tên DB = phần sau dấu '/' cuối của DATABASE_URL, bỏ query string.
_db_name = os.environ["DATABASE_URL"].split("?", 1)[0].rsplit("/", 1)[-1]
if not _db_name.endswith("_test"):
    print(
        f"DỪNG: DATABASE_URL đang trỏ tới database '{_db_name}' — smoke test sẽ "
        "XOÁ SẠCH dữ liệu (TRUNCATE) nên chỉ chạy trên database có tên kết thúc "
        "bằng '_test'.\n"
        "Tạo DB test: CREATE DATABASE cccd_test;\n"
        "Rồi đặt: $env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cccd_test'"
    )
    sys.exit(2)

os.environ["JWT_SECRET"] = "smoke-test-secret-key"
# Smoke test không gọi Colab thật → ép rỗng để kiểm tra nhánh 503.
os.environ["INFERENCE_SERVER_URL"] = ""
# Không tạo admin đầu tiên từ env của shell (test tự tạo admin1 bằng SQL).
for _k in ("ADMIN_USERNAME", "ADMIN_EMAIL", "ADMIN_PASSWORD"):
    os.environ[_k] = ""

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    mark = "[OK] " if cond else "[FAIL]"
    if cond:
        PASS += 1
    else:
        FAIL += 1
    print(f"  {mark} {name} {detail}")


def _tiny_png(width: int = 64, height: int = 40) -> bytes:
    """PNG xám 8-bit cố định (sọc dọc) dựng bằng thư viện chuẩn — không cần Pillow."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    row = bytes((x * 4) % 256 for x in range(width))
    raw = b"".join(b"\x00" + row for _ in range(height))  # filter 0 mỗi dòng
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def main() -> None:
    # Dọn dữ liệu test còn sót từ lần chạy trước (không đụng seed tblFormType;
    # chỉ xoá biểu mẫu P2 do test tạo ra để lần chạy sau không trùng slug).
    import psycopg

    from backend.db import SCHEMA_PATH

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        # DB test mới tạo chưa có bảng → chạy schema.sql (idempotent, giống
        # db.init_db) TRƯỚC khi TRUNCATE.
        conn.execute(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
        conn.execute("TRUNCATE tblAuditLog, tblRefreshToken, tblScanRecord, tblUser CASCADE")
        conn.execute("DELETE FROM tblFormType WHERE slug = 'work_permit'")
        # Lần chạy trước có thể dừng giữa chừng khi atm_open đang bị ẩn.
        conn.execute("UPDATE tblFormType SET is_active = TRUE "
                     "WHERE slug IN ('atm_open', 'health_declare', 'service_contract')")
        conn.commit()

    # `with` để TestClient kích hoạt lifespan (init_db + Redis).
    with TestClient(app) as client:
        _run(client)


def _run(client: TestClient) -> None:
    print("== Health ==")
    r = client.get("/health")
    body = r.json()
    check("health 200", r.status_code == 200)
    check("lite mode bật", body.get("lite_mode") is True, str(body))
    check("model chưa nạp", body.get("model_loaded") is False)
    check("db ok", body.get("db") is True)
    check("redis ok", body.get("redis") is True)
    check("status ok (db + redis đều OK)", body.get("status") == "ok", str(body))

    print("== Register ==")
    r = client.post("/api/v1/auth/register", json={
        "username": "nguyenvana",
        "email": "nguyenvana@demo.vn",
        "password": "demoPass123",
        "full_name": "Nguyễn Văn A",
    })
    body = r.json()
    check("register 201", r.status_code == 201, str(body))
    check("có access token", bool(body.get("data", {}).get("access_token")))
    check("có refresh token", bool(body.get("data", {}).get("refresh_token")))
    check("username trong data", body.get("data", {}).get("username") == "nguyenvana")
    user_id = body.get("data", {}).get("user_id")
    access = body["data"]["access_token"]
    refresh = body["data"]["refresh_token"]
    check("register tự đăng nhập role user", body.get("data", {}).get("role") == "user")

    r = client.post("/api/v1/auth/register", json={
        "username": "nguyenvana",
        "email": "khac@demo.vn",
        "password": "demoPass123",
        "full_name": "Trùng username",
    })
    check("register trùng username → 409", r.status_code == 409, str(r.json()))

    r = client.post("/api/v1/auth/register", json={
        "username": "badpass",
        "email": "badpass@demo.vn",
        "password": "chu-khong-so",
        "full_name": "Mật khẩu thiếu số",
    })
    check("register mật khẩu thiếu số → 400", r.status_code == 400, str(r.json()))

    # DEF-14: username theo regex client + trùng không phân biệt hoa thường.
    r = client.post("/api/v1/auth/register", json={
        "username": "a@b", "email": "ab@demo.vn",
        "password": "demoPass123", "full_name": "Username sai",
    })
    check("register username 'a@b' → 400", r.status_code == 400, str(r.json()))
    r = client.post("/api/v1/auth/register", json={
        "username": "1abc", "email": "1abc@demo.vn",
        "password": "demoPass123", "full_name": "Username bắt đầu bằng số",
    })
    check("register username bắt đầu bằng số → 400", r.status_code == 400, str(r.json()))
    r = client.post("/api/v1/auth/register", json={
        "username": "NguyenVanA", "email": "khac2@demo.vn",
        "password": "demoPass123", "full_name": "Trùng username khác hoa thường",
    })
    check("register trùng username khác hoa/thường → 409", r.status_code == 409, str(r.json()))
    r = client.post("/api/v1/auth/register", json={
        "username": "nguyenvanb", "email": "NguyenVanA@Demo.VN",
        "password": "demoPass123", "full_name": "Trùng email khác hoa thường",
    })
    check("register trùng email khác hoa/thường → 409", r.status_code == 409, str(r.json()))

    print("== Login sai 5 lần → lock ==")
    locked = False
    for i in range(5):
        r = client.post("/api/v1/auth/login", json={
            "identifier": "nguyenvana", "password": "sai-mat-khau-1",
        })
        if r.status_code == 423:
            locked = True
    check("lần sai thứ 5 → 423 khóa", locked, "không khóa được tài khoản")
    check("login lúc khóa vẫn 423", r.status_code == 423)

    # DEF-16: giả lập khóa đã hết hạn (locked_until ở quá khứ, bộ đếm vẫn 5)
    # → sai 1 lần chỉ là 401 (lần sai thứ 1), không bị khóa lại ngay.
    from datetime import date, datetime, timedelta, timezone

    import psycopg

    past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("UPDATE tblUser SET locked_until = %s WHERE username = 'nguyenvana'", (past,))
        conn.commit()
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "sai-mat-khau-1",
    })
    check("hết khóa, sai 1 lần → 401 (không khóa lại ngay)", r.status_code == 401, str(r.json()))
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute(
            "SELECT failed_login_count, locked_until FROM tblUser WHERE username = 'nguyenvana'"
        ).fetchone()
    check("hết khóa, sai 1 lần → bộ đếm = 1, locked_until NULL",
          row is not None and row[0] == 1 and row[1] is None, str(row))

    # Mở khóa để các bước sau tiếp tục test được (test đã xác nhận cơ chế khóa).
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("UPDATE tblUser SET locked_until = NULL, failed_login_count = 0 WHERE username = 'nguyenvana'")
        conn.commit()

    print("== Login đúng (email hoặc username) ==")
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana@demo.vn", "password": "demoPass123",
        "device_info": "smoke-test-android",
    })
    body = r.json()
    check("login bằng email → 200", r.status_code == 200, str(body))
    access = body["data"]["access_token"]
    refresh = body["data"]["refresh_token"]
    check("role user", body.get("data", {}).get("role") == "user")

    # DEF-13: email gõ chữ hoa vẫn đăng nhập được.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "NguyenVanA@Demo.VN", "password": "demoPass123",
    })
    check("login bằng email chữ hoa → 200", r.status_code == 200, str(r.json()))

    print("== /auth/me ==")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    body = r.json()
    check("me 200", r.status_code == 200, str(body))
    check("me trả username + email + role", body.get("username") == "nguyenvana"
          and body.get("email") == "nguyenvana@demo.vn" and body.get("role") == "user")
    check("me trả full_name", body.get("full_name") == "Nguyễn Văn A")

    print("== Refresh ==")
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    body = r.json()
    check("refresh 200", r.status_code == 200, str(body))
    check("refresh trả access mới", bool(body.get("data", {}).get("access_token")))
    new_access = body["data"]["access_token"]

    print("== Logout + blacklist ==")
    r = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {new_access}"})
    check("logout 200", r.status_code == 200, str(r.json()))
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"})
    check("access sau logout bị từ chối (401)", r.status_code == 401, str(r.json()))
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    check("refresh sau logout bị revoke (401)", r.status_code == 401, str(r.json()))

    print("== Forms (P1 + P2 metadata JSONB) ==")
    r = client.get("/api/v1/forms")
    body = r.json()
    check("forms 200", r.status_code == 200, str(body))
    check("có 3 form", len(body.get("forms", [])) == 3)
    slugs = {f["slug"] for f in body.get("forms", [])}
    check("đủ 3 slug quen thuộc", slugs == {"atm_open", "health_declare", "service_contract"})
    atm = next(f for f in body["forms"] if f["slug"] == "atm_open")
    atm_keys = {f["key"] for f in atm["required_fields"]}
    check("form trả requires_front/back + required_fields",
          atm["requires_front"] is True and atm["requires_back"] is True
          and {"phone", "occupation"} <= atm_keys, str(atm_keys))
    # P2: required_fields giờ là list dict {key,label,hint}
    phone_field = next(f for f in atm["required_fields"] if f["key"] == "phone")
    check("required_fields JSONB có label/hint",
          bool(phone_field.get("label")) and bool(phone_field.get("hint")), str(phone_field))

    print("== P1: Admin — tạo user + đổi role → invalidate token ==")
    # Đăng ký admin thủ công qua SQL (chưa có endpoint seed admin).
    from backend.security import hash_password
    admin_id = None
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO tblUser (username, email, password_hash, full_name, role) "
            "VALUES (%s, %s, %s, %s, 'admin') RETURNING id",
            ("admin1", "admin1@cccd.local", hash_password("adminPass123"), "Admin 1"),
        )
        admin_id = cur.fetchone()[0]
        conn.commit()

    r = client.post("/api/v1/auth/login", json={
        "identifier": "admin1@cccd.local", "password": "adminPass123",
    })
    body = r.json()
    admin_access = body["data"]["access_token"]
    check("admin login 200", r.status_code == 200, str(body))

    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {admin_access}"})
    check("GET /users (admin) 200", r.status_code == 200, str(r.json())[:80])
    check("GET /users có ≥2 user", len(r.json().get("users", [])) >= 2)

    # token user cũ (access) — đã logout; đăng nhập lại để test guard.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    user_access = r.json()["data"]["access_token"]

    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {user_access}"})
    check("GET /users (user) → 403", r.status_code == 403, str(r.json()))

    r = client.put(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "viewer"},
    )
    check("đổi sang role đã bỏ (viewer) → 400", r.status_code == 400, str(r.json()))

    r = client.put(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "admin"},
    )
    check("admin đổi role user→admin 200", r.status_code == 200, str(r.json()))

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {user_access}"})
    check("token cũ sau đổi role bị vô hiệu (401)", r.status_code == 401, str(r.json()))

    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    check("user vẫn đăng nhập được sau đổi role", r.status_code == 200)
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['data']['access_token']}"})
    check("me trả role mới = admin", r.json().get("role") == "admin", str(r.json()))

    # Trả nguyenvana về role user để các bước sau chỉ còn 1 admin (admin1).
    r = client.put(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "user"},
    )
    check("admin đổi role admin→user 200", r.status_code == 200, str(r.json()))

    print("== Guards admin ==")
    # admin không tự hạ quyền được
    r = client.put(
        f"/api/v1/users/{admin_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "user"},
    )
    check("admin tự hạ quyền → 400", r.status_code == 400, str(r.json()))
    # admin không khóa admin cuối cùng
    r = client.put(
        f"/api/v1/users/{admin_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"is_active": False},
    )
    check("admin khóa chính mình → 400", r.status_code == 400
          and "chính bạn" in str(r.json().get("detail", "")), str(r.json()))
    # DEF-23: id sai định dạng UUID → 404 (không phải 500).
    r = client.put("/api/v1/users/abc", headers={"Authorization": f"Bearer {admin_access}"},
                   json={"full_name": "X"})
    check("PUT /users/abc (id sai) → 404", r.status_code == 404, str(r.json()))
    r = client.get("/api/v1/audit-logs", params={"user_id": "abc"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("GET /audit-logs?user_id=abc → 400", r.status_code == 400, str(r.json()))

    print("== Proxy /extract-cccd bắt buộc đăng nhập ==")
    fake_jpg = ("a.jpg", b"\xff\xd8\xff\xe0" + b"\x00" * 32, "image/jpeg")
    r = client.post("/extract-cccd/", params={"side": "truoc"}, files={"file": fake_jpg})
    check("extract-cccd không token → 401", r.status_code == 401, str(r.json()))
    r = client.post("/extract-cccd/", params={"side": "truoc"}, files={"file": fake_jpg},
                    headers={"Authorization": f"Bearer {admin_access}"})
    check("extract-cccd chưa cấu hình INFERENCE_SERVER_URL → 503",
          r.status_code == 503, str(r.json()))

    print("== /api/v1/quality-check (cảnh báo chất lượng ảnh) ==")
    png = ("q.png", _tiny_png(), "image/png")
    r = client.post("/api/v1/quality-check", params={"side": "truoc"}, files={"file": png})
    check("quality-check không token → 401", r.status_code == 401, str(r.json()))
    r = client.post("/api/v1/quality-check", params={"side": "truoc"}, files={"file": png},
                    headers={"Authorization": f"Bearer {admin_access}"})
    body = r.json()
    # Không phụ thuộc OpenCV có cài hay không (thiếu → available=false).
    check("quality-check có token → 200 + khóa 'available'",
          r.status_code == 200 and "available" in body, str(body)[:160])
    r = client.post("/api/v1/quality-check", params={"side": "xyz"}, files={"file": png},
                    headers={"Authorization": f"Bearer {admin_access}"})
    check("quality-check side=xyz → 400", r.status_code == 400, str(r.json()))

    print("== P2: Admin quản lý biểu mẫu (POST/PUT /forms) ==")
    # Đăng ký user1 để test các luồng hồ sơ (role user).
    r = client.post("/api/v1/auth/register", json={
        "username": "user1", "email": "user1@cccd.local",
        "password": "opPass123", "full_name": "User 1",
    })
    user1_access = r.json()["data"]["access_token"]
    check("đăng ký user1 201", r.status_code == 201)

    # Admin KHÔNG được tạo / sửa biểu mẫu (chỉ ẩn / hiện).
    r = client.post("/api/v1/forms", headers={"Authorization": f"Bearer {admin_access}"},
                    json={"slug": "x", "name": "X", "required_fields": []})
    check("tạo form (admin) → 405 (đã bỏ)", r.status_code == 405, str(r.status_code))
    r = client.put("/api/v1/forms/atm_open", headers={"Authorization": f"Bearer {admin_access}"},
                   json={"name": "Đổi tên"})
    check("sửa form (admin) → 405 (đã bỏ)", r.status_code == 405, str(r.status_code))

    r = client.get("/api/v1/forms/all", headers={"Authorization": f"Bearer {user1_access}"})
    check("GET /forms/all (user) → 403", r.status_code == 403, str(r.json()))
    r = client.get("/api/v1/forms/all", headers={"Authorization": f"Bearer {admin_access}"})
    check("GET /forms/all (admin) 200 + record_count",
          r.status_code == 200 and len(r.json().get("forms", [])) >= 3
          and all("record_count" in f for f in r.json()["forms"]), str(r.json())[:120])
    r = client.patch("/api/v1/forms/atm_open/visibility",
                     headers={"Authorization": f"Bearer {user1_access}"}, json={"is_active": False})
    check("user ẩn biểu mẫu → 403", r.status_code == 403, str(r.json()))
    r = client.patch("/api/v1/forms/khong-co/visibility",
                     headers={"Authorization": f"Bearer {admin_access}"}, json={"is_active": False})
    check("ẩn biểu mẫu không tồn tại → 404", r.status_code == 404, str(r.json()))

    print("== P2: Gửi hồ sơ (POST /scan-records) ==")
    card = {
        "so_cccd": "001201123456", "ho_va_ten": "NGUYỄN VĂN A",
        "ngay_sinh": "01/01/1990", "gioi_tinh": "Nam", "quoc_tich": "Việt Nam",
        "que_quan": "Hà Nội", "noi_thuong_tru": "Hà Nội", "co_gia_tri_den": "01/01/2030",
    }
    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "atm_open", "extracted_data": card,
                          "supp": {"phone": "0901234567", "occupation": "Kỹ sư"},
                          "card_side": "both", "parse_ok": True, "is_edited": False})
    body = r.json()
    check("gửi hồ sơ 201", r.status_code == 201, str(body))
    check("server cấp mã hồ sơ (HS...)", bool(body.get("code", "").startswith("HS")), str(body))
    rec_id = body.get("record_id")
    rec_code = body.get("code")

    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "khong-ton-tai", "extracted_data": card})
    check("gửi với form không tồn tại → 404", r.status_code == 404, str(r.json()))

    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "atm_open", "extracted_data": {}})
    check("gửi extracted_data rỗng → 400", r.status_code == 400, str(r.json()))

    # DEF-20: giới hạn payload (≤50 khóa, mỗi giá trị ≤1000 ký tự).
    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "atm_open",
                          "extracted_data": {f"k{i}": "x" for i in range(51)}})
    check("gửi extracted_data 51 khóa → 422", r.status_code == 422, str(r.json())[:120])
    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "atm_open", "extracted_data": card,
                          "supp": {"phone": "9" * 1001}})
    check("gửi supp giá trị 1001 ký tự → 422", r.status_code == 422, str(r.json())[:120])

    print("== P2: Lịch sử hồ sơ ==")
    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"})
    body = r.json()
    check("GET /scan-records (user) 200", r.status_code == 200, str(body)[:80])
    check("lịch sử có record vừa gửi", body.get("count", 0) >= 1
          and body["records"][0]["code"] == rec_code)
    check("lịch sử trả supp + extracted_data", body["records"][0].get("supp", {}).get("phone") == "0901234567"
          and body["records"][0]["extracted_data"].get("so_cccd") == "001201123456")
    check("lịch sử trả tên biểu mẫu", body["records"][0].get("form_name") == "Đăng ký mở thẻ ATM")
    # DEF-25: created_at là ISO UTC có offset để client đổi sang giờ máy.
    check("created_at có offset UTC (+00:00)",
          str(body["records"][0].get("created_at", "")).endswith("+00:00"),
          str(body["records"][0].get("created_at")))

    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("GET chi tiết record 200", r.status_code == 200, str(r.json())[:80])

    # Admin KHÔNG được xem nội dung hồ sơ của người khác.
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {admin_access}"})
    check("admin xem chi tiết hồ sơ người khác → 404", r.status_code == 404, str(r.json())[:80])

    # DEF-23: id / user_id sai định dạng UUID → 404 / 400 (không phải 500).
    r = client.get("/api/v1/scan-records/abc", headers={"Authorization": f"Bearer {user1_access}"})
    check("GET /scan-records/abc (id sai) → 404", r.status_code == 404, str(r.json()))
    r = client.get("/api/v1/scan-records", params={"user_id": "abc"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("GET /scan-records?user_id=abc (admin) → 400", r.status_code == 400, str(r.json()))

    # (Đã bỏ requirement duyệt hồ sơ: không còn review-queue và review_status)

    print("== P2: User khác không xem được hồ sơ ==")
    # nguyenvana (role user) không phải chủ hồ sơ của user1.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    other_access = r.json()["data"]["access_token"]
    check("nguyenvana login 200", r.status_code == 200)
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {other_access}"})
    check("user khác xem chi tiết record → 404", r.status_code == 404, str(r.json())[:80])

    print("== Admin ẩn / hiện hồ sơ ==")
    r = client.get("/api/v1/scan-records", params={"all_users": "true"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("admin xem hồ sơ mọi người (?all_users=true) 200",
          r.status_code == 200 and any(x["id"] == rec_id for x in r.json().get("records", [])),
          str(r.json())[:80])
    check("danh sách admin KHÔNG có nội dung CCCD / supp",
          all("extracted_data" not in x and "supp" not in x for x in r.json().get("records", []))
          and "total" in r.json(), str(r.json())[:120])
    r = client.get("/api/v1/scan-records",
                   params={"all_users": "true", "form_id": "atm_open", "q": rec_code},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("admin lọc theo biểu mẫu + mã hồ sơ",
          r.status_code == 200 and [x["id"] for x in r.json().get("records", [])] == [rec_id],
          str(r.json())[:120])
    r = client.get("/api/v1/scan-records", params={"all_users": "true", "status": "xyz"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("admin status=xyz → 400", r.status_code == 400, str(r.json()))
    r = client.patch(f"/api/v1/scan-records/{rec_id}/visibility",
                     headers={"Authorization": f"Bearer {user1_access}"}, json={"is_hidden": True})
    check("user ẩn hồ sơ → 403", r.status_code == 403, str(r.json()))
    r = client.patch(f"/api/v1/scan-records/{rec_id}/visibility",
                     headers={"Authorization": f"Bearer {admin_access}"}, json={"is_hidden": True})
    check("admin ẩn hồ sơ 200", r.status_code == 200 and r.json().get("is_hidden") is True, str(r.json())[:80])
    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"})
    check("chủ hồ sơ không thấy hồ sơ đã ẩn",
          all(x["id"] != rec_id for x in r.json().get("records", [])), str(r.json())[:80])
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("chủ hồ sơ xem chi tiết hồ sơ đã ẩn → 404", r.status_code == 404, str(r.json())[:80])
    r = client.patch(f"/api/v1/scan-records/{rec_id}/visibility",
                     headers={"Authorization": f"Bearer {admin_access}"}, json={"is_hidden": False})
    check("admin hiện lại hồ sơ 200", r.status_code == 200 and r.json().get("is_hidden") is False, str(r.json())[:80])
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("chủ hồ sơ thấy lại hồ sơ", r.status_code == 200, str(r.json())[:80])

    print("== Admin ẩn / hiện biểu mẫu ==")
    r = client.patch("/api/v1/forms/atm_open/visibility",
                     headers={"Authorization": f"Bearer {admin_access}"}, json={"is_active": False})
    check("admin ẩn biểu mẫu atm_open 200",
          r.status_code == 200 and r.json().get("is_active") is False, str(r.json())[:80])
    r = client.get("/api/v1/forms")
    check("biểu mẫu ẩn không còn trong danh mục",
          all(f["slug"] != "atm_open" for f in r.json().get("forms", [])))
    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"})
    check("hồ sơ cũ của biểu mẫu ẩn bị ẩn với chủ hồ sơ",
          all(x["id"] != rec_id for x in r.json().get("records", [])), str(r.json())[:80])
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("chủ hồ sơ mở hồ sơ của biểu mẫu ẩn → 404", r.status_code == 404, str(r.json())[:80])
    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"form_id": "atm_open", "extracted_data": card})
    check("gửi hồ sơ mới cho biểu mẫu ẩn → 404", r.status_code == 404, str(r.json()))
    r = client.get("/api/v1/scan-records", params={"all_users": "true", "status": "form_hidden"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("admin vẫn thấy hồ sơ của biểu mẫu ẩn (form_active=false)",
          any(x["id"] == rec_id and x.get("form_active") is False
              for x in r.json().get("records", [])), str(r.json())[:120])
    r = client.patch("/api/v1/forms/atm_open/visibility",
                     headers={"Authorization": f"Bearer {admin_access}"}, json={"is_active": True})
    check("admin hiện lại biểu mẫu 200", r.status_code == 200, str(r.json())[:80])
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("hồ sơ hiện lại khi biểu mẫu hiện lại", r.status_code == 200, str(r.json())[:80])

    print("== Admin: chi tiết tài khoản, gỡ khóa, đăng xuất mọi thiết bị ==")
    user1_id = client.get("/api/v1/auth/me",
                          headers={"Authorization": f"Bearer {user1_access}"}).json().get("user_id")
    r = client.get(f"/api/v1/users/{user1_id}", headers={"Authorization": f"Bearer {admin_access}"})
    detail = r.json()
    check("GET /users/{id} 200 + số hồ sơ, phiên",
          r.status_code == 200 and detail.get("record_count", 0) >= 1
          and "active_sessions" in detail and "password_hash" not in detail, str(detail)[:120])
    r = client.post(f"/api/v1/users/{user1_id}/unlock", headers={"Authorization": f"Bearer {admin_access}"})
    check("POST /users/{id}/unlock 200", r.status_code == 200, str(r.json()))
    r = client.get("/api/v1/audit-logs", params={"action_group": "form", "end_date": str(date.today())},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("audit lọc nhóm form + end_date hôm nay (tính trọn ngày)",
          r.status_code == 200 and any(x["action"] == "form.hide" for x in r.json().get("logs", []))
          and "total" in r.json(), str(r.json())[:120])
    r = client.get("/api/v1/audit-logs", params={"action_group": "xyz"},
                   headers={"Authorization": f"Bearer {admin_access}"})
    check("audit action_group=xyz → 400", r.status_code == 400, str(r.json()))

    print("== Profile CCCD (/profiles) ==")
    op_h = {"Authorization": f"Bearer {user1_access}"}
    admin_h = {"Authorization": f"Bearer {admin_access}"}
    r = client.get("/api/v1/profiles", headers=op_h)
    check("GET /profiles rỗng 200", r.status_code == 200 and r.json().get("profiles") == [], str(r.json()))

    prof1 = {**card, "so_cccd": "001201123456"}
    prof2 = {**card, "so_cccd": "001201654321", "ho_va_ten": "TRẦN THỊ B"}
    r = client.post("/api/v1/profiles", headers=op_h, json={"data": prof1})
    p1 = r.json()
    check("tạo profile 1 → 201, không còn trường is_default",
          r.status_code == 201 and "is_default" not in p1, str(p1))
    r = client.post("/api/v1/profiles", headers=op_h, json={"data": prof2})
    p2 = r.json()
    check("tạo profile 2 → 201", r.status_code == 201 and bool(p2.get("id")), str(p2))

    r = client.post("/api/v1/profiles", headers=op_h,
                    json={"data": {**card, "so_cccd": "001 201 123456"}})
    check("tạo profile trùng số CCCD (có khoảng trắng) → 409", r.status_code == 409, str(r.json()))
    r = client.post("/api/v1/profiles", headers=op_h,
                    json={"data": {**card, "so_cccd": "001.201.123456"}})
    check("tạo profile trùng số CCCD (có dấu chấm) → 409", r.status_code == 409, str(r.json()))
    r = client.post("/api/v1/profiles", headers=op_h, json={"data": {}})
    check("tạo profile data rỗng → 400", r.status_code == 400, str(r.json()))

    r = client.get("/api/v1/profiles", headers=op_h)
    ids = [p["id"] for p in r.json().get("profiles", [])]
    check("GET /profiles có 2 profile theo created_at ASC", ids == [p1.get("id"), p2.get("id")], str(ids))

    r = client.put(f"/api/v1/profiles/{p2.get('id')}", headers=op_h, json={"data": prof1})
    check("sửa profile 2 thành số CCCD của profile 1 → 409", r.status_code == 409, str(r.json()))
    r = client.put(f"/api/v1/profiles/{p2.get('id')}", headers=op_h,
                   json={"data": {**prof2, "ho_va_ten": "TRẦN THỊ C"}})
    check("sửa profile hợp lệ → 200", r.status_code == 200
          and r.json().get("data", {}).get("ho_va_ten") == "TRẦN THỊ C", str(r.json()))

    r = client.post(f"/api/v1/profiles/{p2.get('id')}/default", headers=op_h)
    check("endpoint đặt mặc định đã bỏ → 404/405", r.status_code in (404, 405), str(r.status_code))

    r = client.put(f"/api/v1/profiles/{p1.get('id')}", headers=admin_h, json={"data": prof1})
    check("admin sửa profile của user1 → 404", r.status_code == 404, str(r.json()))
    r = client.delete(f"/api/v1/profiles/{p1.get('id')}", headers=admin_h)
    check("admin xoá profile của user1 → 404", r.status_code == 404, str(r.json()))

    r = client.delete(f"/api/v1/profiles/{p2.get('id')}", headers=op_h)
    check("xoá profile 2 → 200", r.status_code == 200, str(r.json()))
    r = client.get("/api/v1/profiles", headers=op_h)
    ids = [p["id"] for p in r.json().get("profiles", [])]
    check("sau khi xoá chỉ còn profile 1", ids == [p1.get("id")], str(ids))
    r = client.delete("/api/v1/profiles/abc", headers=op_h)
    check("xoá id không hợp lệ → 404", r.status_code == 404, str(r.json()))

    print("== P2: Đổi mật khẩu (không OTP) ==")
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {user1_access}"},
                    json={"current_password": "sai-mat-khau", "new_password": "newPass123"})
    check("đổi mật khẩu sai current → 400", r.status_code == 400, str(r.json()))

    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {user1_access}"},
                    json={"current_password": "opPass123", "new_password": "newPass123"})
    check("đổi mật khẩu đúng → 200", r.status_code == 200, str(r.json())[:80])

    r = client.post("/api/v1/auth/login", json={
        "identifier": "user1", "password": "opPass123",
    })
    check("mật khẩu cũ hết hiệu lực", r.status_code == 401, str(r.json()))
    r = client.post("/api/v1/auth/login", json={
        "identifier": "user1", "password": "newPass123",
    })
    check("mật khẩu mới đăng nhập được", r.status_code == 200)
    user1_access = r.json()["data"]["access_token"]

    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {user1_access}"},
                    json={"current_password": "newPass123", "new_password": "newPass123"})
    check("đổi mật khẩu trùng mật khẩu cũ → 400", r.status_code == 400, str(r.json()))

    print("== Audit logs (đủ sự kiện P2) ==")
    r = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {admin_access}"})
    body = r.json()
    check("audit-logs 200", r.status_code == 200, str(body)[:80])
    actions = {log["action"] for log in body.get("logs", [])}
    check("có đủ sự kiện P1+P2", {"auth.register", "auth.login", "auth.logout",
                                  "auth.login_failed", "user.update",
                                  "record.create", "record.hide", "record.show",
                                  "auth.change_password"} <= actions,
          str(sorted(actions)))
    check("có sự kiện profile.create", "profile.create" in actions, str(sorted(actions)))

    print(f"\n== KẾT QUẢ: {PASS} PASS / {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()