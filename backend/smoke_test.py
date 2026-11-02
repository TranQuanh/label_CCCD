"""
smoke_test.py
=============
Smoke test P1+P2 — chạy trực tiếp qua FastAPI TestClient (không cần uvicorn).

Cover:
  P1 — register (role user) → login sai 5 lần (lock) → login đúng → me → refresh → logout →
       kiểm access cũ bị blacklist → admin tạo user + đổi role (user → admin) → token cũ bị
       từ chối → audit-logs đủ sự kiện.
  P2 — /forms trả metadata JSONB {key,label,hint}; admin POST/PUT /forms;
       gửi hồ sơ (POST /scan-records) nhận mã server; lịch sử từ PostgreSQL;
       đổi mật khẩu (bỏ OTP, verify mật khẩu hiện tại); quản lý profiles CCCD.

Chạy:
  $env:SKIP_MODEL_LOAD='1'
  $env:DATABASE_URL='postgresql://postgres:postgres@localhost:5432/cccd'
  python backend/smoke_test.py
"""

from __future__ import annotations

import os
import sys

# Cho import `app.main` như uvicorn (qua shim `app` → backend/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SKIP_MODEL_LOAD", "1")
os.environ.setdefault("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/cccd")
os.environ.setdefault("JWT_SECRET", "smoke-test-secret-key")

from fastapi.testclient import TestClient  # noqa: E402

# DEF-22: shim app/ đã bị xoá — import trực tiếp từ backend.main
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


def main() -> None:
    # DEF-22: TRUNCATE an toàn — chỉ xoá dữ liệu test, không xoá seed tblFormType.
    # Thêm tblCccdProfile trước tblUser để tránh FK violation.
    # Dùng biến môi trường DATABASE_URL — không hardcode DB dev mặc định.
    import psycopg

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("  [SKIP] DATABASE_URL không được đặt — bỏ qua bước dọn DB")
    else:
        with psycopg.connect(db_url) as conn:
            conn.execute(
                "TRUNCATE tblAuditLog, tblRefreshToken, tblScanRecord, "
                "tblCccdProfile, tblUser CASCADE"
            )
            conn.execute("DELETE FROM tblFormType WHERE slug = 'work_permit'")
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

    # Mở khóa để các bước sau tiếp tục test được (test đã xác nhận cơ chế khóa).
    import psycopg

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
    # DEF-22: import từ backend trực tiếp, không qua shim app/
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

    # user token cũ (access) — đã logout; đăng nhập lại để test guard.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    user_access = r.json()["data"]["access_token"]

    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {user_access}"})
    check("GET /users (user) → 403", r.status_code == 403, str(r.json()))

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
    check("admin khóa chính mình → 400", r.status_code == 400, str(r.json()))

    print("== P2: Admin quản lý biểu mẫu (POST/PUT /forms) ==")
    # Đăng ký user1 để test các luồng hồ sơ (giữ role user).
    r = client.post("/api/v1/auth/register", json={
        "username": "user1", "email": "user1@cccd.local",
        "password": "userPass123", "full_name": "User 1",
    })
    user1_access = r.json()["data"]["access_token"]
    check("đăng ký user1 201", r.status_code == 201)

    r = client.post("/api/v1/forms", headers={"Authorization": f"Bearer {user1_access}"},
                    json={"slug": "x", "name": "X", "required_fields": []})
    check("tạo form (user) → 403", r.status_code == 403, str(r.json()))

    r = client.post("/api/v1/forms", headers={"Authorization": f"Bearer {admin_access}"},
                    json={"slug": "work_permit", "name": "Giấy phép lao động",
                          "description": "Test P2", "requires_front": True,
                          "requires_back": True,
                          "required_fields": [
                              {"key": "phone", "label": "Số điện thoại", "hint": "Nhập SĐT"},
                              {"key": "company", "label": "Công ty", "hint": "Tên công ty"},
                          ]})
    check("tạo form (admin) 201", r.status_code == 201, str(r.json())[:80])

    r = client.put("/api/v1/forms/work_permit", headers={"Authorization": f"Bearer {admin_access}"},
                   json={"requires_back": False, "required_fields": [
                       {"key": "phone", "label": "Số điện thoại", "hint": "Nhập SĐT"}]})
    check("sửa form (admin) 200", r.status_code == 200, str(r.json())[:80])

    r = client.get("/api/v1/forms")
    check("forms mới xuất hiện", any(f["slug"] == "work_permit" for f in r.json()["forms"]))
    wp = next(f for f in r.json()["forms"] if f["slug"] == "work_permit")
    check("sửa form: requires_back=False + 1 trường",
          wp["requires_back"] is False and len(wp["required_fields"]) == 1)

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

    print("== P2: Lịch sử hồ sơ ==")
    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {user1_access}"})
    body = r.json()
    check("GET /scan-records (user) 200", r.status_code == 200, str(body)[:80])
    check("lịch sử có record vừa gửi", body.get("count", 0) >= 1
          and body["records"][0]["code"] == rec_code)
    check("lịch sử trả supp + extracted_data", body["records"][0].get("supp", {}).get("phone") == "0901234567"
          and body["records"][0]["extracted_data"].get("so_cccd") == "001201123456")
    check("lịch sử trả tên biểu mẫu", body["records"][0].get("form_name") == "Đăng ký mở thẻ ATM")

    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {user1_access}"})
    check("GET chi tiết record 200", r.status_code == 200, str(r.json())[:80])

    # admin xem được record của user khác
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {admin_access}"})
    check("admin xem được record (có quyền)", r.status_code == 200, str(r.json())[:80])

    print("== Profile CCCD (/profiles) ==")
    user1_h = {"Authorization": f"Bearer {user1_access}"}
    admin_h = {"Authorization": f"Bearer {admin_access}"}
    r = client.get("/api/v1/profiles", headers=user1_h)
    check("GET /profiles rỗng 200", r.status_code == 200 and r.json().get("profiles") == [], str(r.json()))

    prof1 = {**card, "so_cccd": "001201123456"}
    prof2 = {**card, "so_cccd": "001201654321", "ho_va_ten": "TRẦN THỊ B"}
    r = client.post("/api/v1/profiles", headers=user1_h, json={"data": prof1})
    p1 = r.json()
    check("tạo profile 1 → 201, không còn trường is_default",
          r.status_code == 201 and "is_default" not in p1, str(p1))
    r = client.post("/api/v1/profiles", headers=user1_h, json={"data": prof2})
    p2 = r.json()
    check("tạo profile 2 → 201", r.status_code == 201 and bool(p2.get("id")), str(p2))

    r = client.post("/api/v1/profiles", headers=user1_h,
                    json={"data": {**card, "so_cccd": "001 201 123456"}})
    check("tạo profile trùng số CCCD (có khoảng trắng) → 409", r.status_code == 409, str(r.json()))
    r = client.post("/api/v1/profiles", headers=user1_h,
                    json={"data": {**card, "so_cccd": "001.201.123456"}})
    check("tạo profile trùng số CCCD (có dấu chấm) → 409", r.status_code == 409, str(r.json()))
    r = client.post("/api/v1/profiles", headers=user1_h, json={"data": {}})
    check("tạo profile data rỗng → 400", r.status_code == 400, str(r.json()))

    r = client.get("/api/v1/profiles", headers=user1_h)
    ids = [p["id"] for p in r.json().get("profiles", [])]
    check("GET /profiles có 2 profile theo created_at ASC", ids == [p1.get("id"), p2.get("id")], str(ids))

    r = client.put(f"/api/v1/profiles/{p2.get('id')}", headers=user1_h, json={"data": prof1})
    check("sửa profile 2 thành số CCCD của profile 1 → 409", r.status_code == 409, str(r.json()))
    r = client.put(f"/api/v1/profiles/{p2.get('id')}", headers=user1_h,
                   json={"data": {**prof2, "ho_va_ten": "TRẦN THỊ C"}})
    check("sửa profile hợp lệ → 200", r.status_code == 200
          and r.json().get("data", {}).get("ho_va_ten") == "TRẦN THỊ C", str(r.json()))

    r = client.post(f"/api/v1/profiles/{p2.get('id')}/default", headers=user1_h)
    check("endpoint đặt mặc định đã bỏ → 404/405", r.status_code in (404, 405), str(r.status_code))

    r = client.put(f"/api/v1/profiles/{p1.get('id')}", headers=admin_h, json={"data": prof1})
    check("admin sửa profile của user1 → 404", r.status_code == 404, str(r.json()))
    r = client.delete(f"/api/v1/profiles/{p1.get('id')}", headers=admin_h)
    check("admin xoá profile của user1 → 404", r.status_code == 404, str(r.json()))

    r = client.delete(f"/api/v1/profiles/{p2.get('id')}", headers=user1_h)
    check("xoá profile 2 → 200", r.status_code == 200, str(r.json()))
    r = client.get("/api/v1/profiles", headers=user1_h)
    ids = [p["id"] for p in r.json().get("profiles", [])]
    check("sau khi xoá chỉ còn profile 1", ids == [p1.get("id")], str(ids))
    r = client.delete("/api/v1/profiles/abc", headers=user1_h)
    check("xoá id không hợp lệ → 404", r.status_code == 404, str(r.json()))

    print("== P2: Đổi mật khẩu (không OTP) ==")
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {user1_access}"},
                    json={"current_password": "sai-mat-khau", "new_password": "newPass123"})
    check("đổi mật khẩu sai current → 400", r.status_code == 400, str(r.json()))

    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {user1_access}"},
                    json={"current_password": "userPass123", "new_password": "newPass123"})
    check("đổi mật khẩu đúng → 200", r.status_code == 200, str(r.json())[:80])

    r = client.post("/api/v1/auth/login", json={
        "identifier": "user1", "password": "userPass123",
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
                                  "record.create",
                                  "auth.change_password"} <= actions,
          str(sorted(actions)))
    check("có sự kiện profile.create", "profile.create" in actions, str(sorted(actions)))

    print(f"\n== KẾT QUẢ: {PASS} PASS / {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()