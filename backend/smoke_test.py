"""
smoke_test.py
=============
Smoke test P1+P2 — chạy trực tiếp qua FastAPI TestClient (không cần uvicorn).

Cover:
  P1 — register → login sai 5 lần (lock) → login đúng → me → refresh → logout →
       kiểm access cũ bị blacklist → admin tạo user + đổi role → token cũ bị
       từ chối → audit-logs đủ sự kiện.
  P2 — /forms trả metadata JSONB {key,label,hint}; admin POST/PUT /forms;
       gửi hồ sơ (POST /scan-records) nhận mã server; lịch sử từ PostgreSQL;
       hàng đợi duyệt + duyệt; viewer chỉ đọc bản đã duyệt có CCCD che;
       đổi mật khẩu (bỏ OTP, verify mật khẩu hiện tại).

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

from app.main import app  # noqa: E402

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
    # Dọn dữ liệu test còn sót từ lần chạy trước (không đụng seed tblFormType;
    # chỉ xoá biểu mẫu P2 do test tạo ra để lần chạy sau không trùng slug).
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE tblAuditLog, tblRefreshToken, tblScanRecord, tblBatchJob, tblUser CASCADE")
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
    check("register tự đăng nhập role operator", body.get("data", {}).get("role") == "operator")

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
    check("role operator", body.get("data", {}).get("role") == "operator")

    print("== /auth/me ==")
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    body = r.json()
    check("me 200", r.status_code == 200, str(body))
    check("me trả username + email + role", body.get("username") == "nguyenvana"
          and body.get("email") == "nguyenvana@demo.vn" and body.get("role") == "operator")
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

    # operator token cũ (access) — đã logout; đăng nhập lại để test guard.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    op_access = r.json()["data"]["access_token"]

    r = client.get("/api/v1/users", headers={"Authorization": f"Bearer {op_access}"})
    check("GET /users (operator) → 403", r.status_code == 403, str(r.json()))

    r = client.put(
        f"/api/v1/users/{user_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "viewer"},
    )
    check("admin đổi role operator→viewer 200", r.status_code == 200, str(r.json()))

    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {op_access}"})
    check("token cũ sau đổi role bị vô hiệu (401)", r.status_code == 401, str(r.json()))

    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    check("user vẫn đăng nhập được sau đổi role", r.status_code == 200)
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {r.json()['data']['access_token']}"})
    check("me trả role mới = viewer", r.json().get("role") == "viewer", str(r.json()))

    print("== Guards admin ==")
    # admin không tự hạ quyền được
    r = client.put(
        f"/api/v1/users/{admin_id}",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"role": "operator"},
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
    # Đăng ký operator1 để test các luồng hồ sơ (giữ role operator).
    r = client.post("/api/v1/auth/register", json={
        "username": "operator1", "email": "operator1@cccd.local",
        "password": "opPass123", "full_name": "Operator 1",
    })
    operator1_access = r.json()["data"]["access_token"]
    check("đăng ký operator1 201", r.status_code == 201)

    r = client.post("/api/v1/forms", headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"slug": "x", "name": "X", "required_fields": []})
    check("tạo form (operator) → 403", r.status_code == 403, str(r.json()))

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
    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"form_id": "atm_open", "extracted_data": card,
                          "supp": {"phone": "0901234567", "occupation": "Kỹ sư"},
                          "card_side": "both", "parse_ok": True, "is_edited": False})
    body = r.json()
    check("gửi hồ sơ 201", r.status_code == 201, str(body))
    check("server cấp mã hồ sơ (HS...)", bool(body.get("code", "").startswith("HS")), str(body))
    rec_id = body.get("record_id")
    rec_code = body.get("code")

    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"form_id": "khong-ton-tai", "extracted_data": card})
    check("gửi với form không tồn tại → 404", r.status_code == 404, str(r.json()))

    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"form_id": "atm_open", "extracted_data": {}})
    check("gửi extracted_data rỗng → 400", r.status_code == 400, str(r.json()))

    print("== P2: Lịch sử hồ sơ ==")
    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {operator1_access}"})
    body = r.json()
    check("GET /scan-records (operator) 200", r.status_code == 200, str(body)[:80])
    check("lịch sử có record vừa gửi + pending", body.get("count", 0) >= 1
          and body["records"][0]["code"] == rec_code
          and body["records"][0]["review_status"] == "pending")
    check("lịch sử trả supp + extracted_data", body["records"][0].get("supp", {}).get("phone") == "0901234567"
          and body["records"][0]["extracted_data"].get("so_cccd") == "001201123456")
    check("lịch sử trả tên biểu mẫu", body["records"][0].get("form_name") == "Đăng ký mở thẻ ATM")

    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {operator1_access}"})
    check("GET chi tiết record 200", r.status_code == 200, str(r.json())[:80])

    # operator không xem được record của người khác (chỉ có record của operator1).
    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {admin_access}"})
    check("admin xem được record (có quyền)", r.status_code == 200, str(r.json())[:80])

    print("== P2: Hàng đợi duyệt + duyệt ==")
    r = client.get("/api/v1/scan-records/review-queue", headers={"Authorization": f"Bearer {operator1_access}"})
    body = r.json()
    check("review-queue có record pending", body.get("count", 0) >= 1, str(body)[:80])

    r = client.patch(f"/api/v1/scan-records/{rec_id}/review",
                     headers={"Authorization": f"Bearer {operator1_access}"},
                     json={"review_status": "reviewed"})
    check("duyệt record → 200", r.status_code == 200, str(r.json())[:80])

    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {operator1_access}"})
    check("record sau duyệt = reviewed", r.json().get("review_status") == "reviewed")

    print("== P2: Viewer — chỉ đọc bản đã duyệt, CCCD bị che ==")
    # nguyenvana đã được đổi role viewer ở phần P1 admin bên trên.
    r = client.post("/api/v1/auth/login", json={
        "identifier": "nguyenvana", "password": "demoPass123",
    })
    viewer_access = r.json()["data"]["access_token"]
    check("viewer login 200", r.status_code == 200)

    r = client.get("/api/v1/scan-records", headers={"Authorization": f"Bearer {viewer_access}"})
    body = r.json()
    check("viewer xem lịch sử → masked=true", body.get("masked") is True, str(body)[:120])
    viewer_records = body.get("records", [])
    check("viewer thấy ít nhất 1 record đã duyệt", len(viewer_records) >= 1)
    # viewer thấy record đã duyệt của người khác — số CCCD phải bị che.
    if viewer_records:
        masked_cccd = viewer_records[0]["extracted_data"].get("so_cccd", "")
        check("viewer thấy CCCD bị che (******)", "******" in masked_cccd, masked_cccd)

    r = client.get(f"/api/v1/scan-records/{rec_id}", headers={"Authorization": f"Bearer {viewer_access}"})
    check("viewer xem chi tiết record đã duyệt 200", r.status_code == 200, str(r.json())[:80])

    r = client.post("/api/v1/scan-records", headers={"Authorization": f"Bearer {viewer_access}"},
                    json={"form_id": "atm_open", "extracted_data": card})
    check("viewer gửi hồ sơ → 403", r.status_code == 403, str(r.json()))

    r = client.get("/api/v1/scan-records/review-queue", headers={"Authorization": f"Bearer {viewer_access}"})
    check("viewer xem review-queue → 403", r.status_code == 403, str(r.json()))

    print("== P2: Đổi mật khẩu (không OTP) ==")
    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"current_password": "sai-mat-khau", "new_password": "newPass123"})
    check("đổi mật khẩu sai current → 400", r.status_code == 400, str(r.json()))

    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"current_password": "opPass123", "new_password": "newPass123"})
    check("đổi mật khẩu đúng → 200", r.status_code == 200, str(r.json())[:80])

    r = client.post("/api/v1/auth/login", json={
        "identifier": "operator1", "password": "opPass123",
    })
    check("mật khẩu cũ hết hiệu lực", r.status_code == 401, str(r.json()))
    r = client.post("/api/v1/auth/login", json={
        "identifier": "operator1", "password": "newPass123",
    })
    check("mật khẩu mới đăng nhập được", r.status_code == 200)
    operator1_access = r.json()["data"]["access_token"]

    r = client.post("/api/v1/auth/change-password",
                    headers={"Authorization": f"Bearer {operator1_access}"},
                    json={"current_password": "newPass123", "new_password": "newPass123"})
    check("đổi mật khẩu trùng mật khẩu cũ → 400", r.status_code == 400, str(r.json()))

    print("== Audit logs (đủ sự kiện P2) ==")
    r = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {admin_access}"})
    body = r.json()
    check("audit-logs 200", r.status_code == 200, str(body)[:80])
    actions = {log["action"] for log in body.get("logs", [])}
    check("có đủ sự kiện P1+P2", {"auth.register", "auth.login", "auth.logout",
                                  "auth.login_failed", "user.update",
                                  "record.create", "record.review",
                                  "auth.change_password"} <= actions,
          str(sorted(actions)))

    print(f"\n== KẾT QUẢ: {PASS} PASS / {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()