-- schema.sql
-- ===========
-- Lược đồ cơ sở dữ liệu P1 — xác thực & quản lý tài khoản (RBAC).
-- 6 bảng + view che thông tin nhạy cảm + seed dữ liệu biểu mẫu.
--
-- Quy ước:
--   - Mọi bảng nghiệp vụ dùng UUID làm PK (gen_v4), trừ bảng tra cứu
--     tblFormType vẫn giữ UUID PK nhưng định danh nghiệp vụ là cột slug.
--   - `db.py` chạy script này theo kiểu idempotent (CREATE TABLE IF NOT EXISTS)
--     nên có thể chạy lại nhiều lần không lỗi.
--   - RLS: tblScanRecord bật owner + admin (xem bảng để biết chính sách).

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ───────────────────────────────────────────────────────────────────────────
-- 1. tblUser — tài khoản người dùng
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblUser (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username           VARCHAR(255) NOT NULL UNIQUE,
    email              VARCHAR(255) NOT NULL UNIQUE,
    password_hash      VARCHAR(255) NOT NULL,
    full_name          VARCHAR(255),
    role               VARCHAR(20)  NOT NULL DEFAULT 'operator',
    is_active          BOOLEAN      NOT NULL DEFAULT TRUE,
    failed_login_count INT          NOT NULL DEFAULT 0,
    locked_until       TIMESTAMP,
    token_version      INT          NOT NULL DEFAULT 0,   -- tăng khi đổi role → vô hiệu token cũ
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────────────────
-- 2. tblRefreshToken — refresh token (hash trong DB, xoay vòng được)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblRefreshToken (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    token_hash    VARCHAR(255) NOT NULL UNIQUE,      -- SHA-256 của token ngẫu nhiên
    device_info   VARCHAR(255),
    ip_address    VARCHAR(45),
    expires_at    TIMESTAMP NOT NULL,
    revoked_at    TIMESTAMP,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_refresh_user ON tblRefreshToken(user_id);

-- ───────────────────────────────────────────────────────────────────────────
-- 3. tblFormType — loại biểu mẫu (slug = khoá nghiệp vụ, id = UUID nội bộ)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblFormType (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(100) NOT NULL UNIQUE,    -- atm_open / health_declare / service_contract
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    requires_front  BOOLEAN NOT NULL DEFAULT TRUE,
    requires_back   BOOLEAN NOT NULL DEFAULT FALSE,
    required_fields TEXT[],
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- ───────────────────────────────────────────────────────────────────────────
-- 4. tblBatchJob — công việc nhập hàng loạt (async, P4; tạo sẵn cấu trúc)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblBatchJob (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    form_type_id  UUID NOT NULL REFERENCES tblFormType(id),
    status        VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/running/done/failed
    total_images  INT,
    success_count INT,
    fail_count    INT,
    error_report  JSONB,
    created_at    TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at  TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_batch_user ON tblBatchJob(user_id);

-- ───────────────────────────────────────────────────────────────────────────
-- 5. tblScanRecord — kết quả trích xuất (lịch sử của người dùng)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblScanRecord (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    form_type_id       UUID REFERENCES tblFormType(id),
    batch_job_id       UUID REFERENCES tblBatchJob(id) ON DELETE SET NULL,
    review_status      VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/reviewed
    extracted_data     JSONB NOT NULL,
    confidence_scores  JSONB,
    parse_ok           BOOLEAN,
    raw_output         TEXT,
    is_edited          BOOLEAN NOT NULL DEFAULT FALSE,
    card_side          VARCHAR(10) CHECK (card_side IN ('front','back','both')),
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_scan_user_created ON tblScanRecord(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_data_gin ON tblScanRecord USING GIN (extracted_data);

-- ───────────────────────────────────────────────────────────────────────────
-- 6. tblAuditLog — nhật ký kiểm toán, append-only (không cho phép sửa/xoá)
-- ───────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblAuditLog (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID REFERENCES tblUser(id) ON DELETE SET NULL,
    action       VARCHAR(100) NOT NULL,
    target_type  VARCHAR(50),
    target_id    UUID,
    metadata     JSONB,
    ip_address   VARCHAR(45),
    device_info  VARCHAR(255),
    created_at   TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user ON tblAuditLog(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON tblAuditLog(created_at DESC);

-- ───────────────────────────────────────────────────────────────────────────
-- View che thông tin nhạy cảm — dùng cho người dùng/viewer xem kết quả đã
-- duyệt. Số CCCD bị che giữa: 001201******.
-- P1 chưa có dữ liệu bản ghi; view tạo sẵn cho P2/P3.
-- ───────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE VIEW v_scan_record_masked AS
SELECT
    r.id,
    r.user_id,
    r.form_type_id,
    r.review_status,
    CASE
        WHEN r.extracted_data ? 'so_cccd'
        THEN r.extracted_data || jsonb_build_object(
                 'so_cccd', left(r.extracted_data ->> 'so_cccd', 6) || '******'
             )
        ELSE r.extracted_data
    END AS extracted_data,
    r.confidence_scores,
    r.parse_ok,
    r.is_edited,
    r.card_side,
    r.created_at
FROM tblScanRecord r
WHERE r.review_status = 'reviewed';

-- ───────────────────────────────────────────────────────────────────────────
-- Seed: 3 loại biểu mẫu (khớp kFormTypes phía frontend)
-- ───────────────────────────────────────────────────────────────────────────
INSERT INTO tblFormType (slug, name, description, requires_front, requires_back, required_fields)
VALUES
    ('atm_open', 'Đăng ký mở thẻ ATM', 'Kê khai thông tin cá nhân khi mở tài khoản thanh toán.', TRUE, TRUE,
     ARRAY['phone', 'occupation']),
    ('health_declare', 'Khai báo y tế', 'Tờ khai sức khỏe phục vụ khám chữa bệnh.', TRUE, TRUE,
     ARRAY['phone', 'symptoms']),
    ('service_contract', 'Hợp đồng dịch vụ', 'Đăng ký ký hợp đồng cung cấp dịch vụ.', TRUE, TRUE,
     ARRAY['phone', 'company'])
ON CONFLICT (slug) DO NOTHING;