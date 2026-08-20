"""
smoke_test.py
=============
Smoke test P1 — chạy trực tiếp qua FastAPI TestClient (không cần uvicorn).

Cover: register → login sai 5 lần (lock) → login đúng → me → refresh → logout →
kiểm access cũ bị blacklist → admin tạo user + đổi role → token cũ bị từ chối →
audit-logs đủ sự kiện.

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
    # Dọn dữ liệu test còn sót từ lần chạy trước (không đụng tblFormType).
    import psycopg

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.execute("TRUNCATE tblAuditLog, tblRefreshToken, tblScanRecord, tblBatchJob, tblUser CASCADE")
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

    print("== Forms ==")
    r = client.get("/api/v1/forms")
    body = r.json()
    check("forms 200", r.status_code == 200, str(body))
    check("có 3 form", len(body.get("forms", [])) == 3)
    slugs = {f["slug"] for f in body.get("forms", [])}
    check("đủ 3 slug quen thuộc", slugs == {"atm_open", "health_declare", "service_contract"})
    atm = next(f for f in body["forms"] if f["slug"] == "atm_open")
    check("form trả requires_front/back + required_fields",
          atm["requires_front"] is True and atm["requires_back"] is True
          and "phone" in atm["required_fields"] and "occupation" in atm["required_fields"])

    print("== Admin: tạo user + đổi role → invalidate token ==")
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

    print("== Audit logs ==")
    r = client.get("/api/v1/audit-logs", headers={"Authorization": f"Bearer {admin_access}"})
    body = r.json()
    check("audit-logs 200", r.status_code == 200, str(body)[:80])
    actions = {log["action"] for log in body.get("logs", [])}
    check("có đủ sự kiện chính", {"auth.register", "auth.login", "auth.logout",
                                   "auth.login_failed", "user.update"} <= actions,
          str(actions))

    print(f"\n== KẾT QUẢ: {PASS} PASS / {FAIL} FAIL ==")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()