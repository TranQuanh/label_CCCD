-- schema.sql
-- ===========
-- Lược đồ cơ sở dữ liệu P1 + P2 — xác thực & RBAC + lịch sử hồ sơ & duyệt.
-- 6 bảng + view che thông tin nhạy cảm + seed dữ liệu biểu mẫu.
--
-- Quy ước:
--   - Mọi bảng nghiệp vụ dùng UUID làm PK (gen_v4), trừ bảng tra cứu
--     tblFormType vẫn giữ UUID PK nhưng định danh nghiệp vụ là cột slug.
--   - `db.py` chạy script này theo kiểu idempotent (CREATE TABLE IF NOT EXISTS)
--     nên có thể chạy lại nhiều lần không lỗi. Các bảng/kiểu đổi ở P2 được
--     migration bằng ALTER ... IF NOT EXISTS / DO $$ phía dưới.
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
    required_fields JSONB,           -- [{key,label,hint}, ...] — P2: JSONB thay TEXT[]
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- P2 migration: bản cũ lưu `required_fields` là TEXT[] (mảng key đơn) → chuyển
-- sang JSONB. `to_jsonb(text[])` cho `["key1","key2"]` (seed sẽ ghi đè bằng
-- [{key,label,hint}] qua ON CONFLICT DO UPDATE phía dưới).
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblformtype' AND column_name = 'required_fields'
          AND data_type = 'ARRAY'
    ) THEN
        ALTER TABLE tblFormType
            ALTER COLUMN required_fields TYPE JSONB USING to_jsonb(required_fields);
    END IF;
END $$;

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
    code               VARCHAR(50) UNIQUE NOT NULL,  -- mã hồ sơ do server cấp (P2)
    user_id            UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    form_type_id       UUID REFERENCES tblFormType(id),
    batch_job_id       UUID REFERENCES tblBatchJob(id) ON DELETE SET NULL,
    review_status      VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending/reviewed
    extracted_data     JSONB NOT NULL,
    supp               JSONB,             -- trường bổ sung theo biểu mẫu {key: value} (P2)
    confidence_scores  JSONB,
    parse_ok           BOOLEAN,
    raw_output         TEXT,
    is_edited          BOOLEAN NOT NULL DEFAULT FALSE,
    card_side          VARCHAR(10) CHECK (card_side IN ('front','back','both')),
    created_at         TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP NOT NULL DEFAULT NOW()
);

-- P2 migration: bản cũ không có cột `code` → thêm nếu chưa có. Bản mới đã có
-- cột này trong CREATE TABLE nên nhánh này chỉ chạy đúng một lần trên DB cũ.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'code'
    ) THEN
        ALTER TABLE tblScanRecord ADD COLUMN code VARCHAR(50) UNIQUE;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'supp'
    ) THEN
        ALTER TABLE tblScanRecord ADD COLUMN supp JSONB;
    END IF;
END $$;

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
-- P2 bổ sung cột `code`/`supp` — PostgreSQL không cho CREATE OR REPLACE đổi
-- thứ tự cột nên phải DROP trước rồi tạo lại.
-- ───────────────────────────────────────────────────────────────────────────
DROP VIEW IF EXISTS v_scan_record_masked;
CREATE VIEW v_scan_record_masked AS
SELECT
    r.id,
    r.code,
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
    r.supp,
    r.confidence_scores,
    r.parse_ok,
    r.is_edited,
    r.card_side,
    r.created_at
FROM tblScanRecord r
WHERE r.review_status = 'reviewed';

-- ───────────────────────────────────────────────────────────────────────────
-- Seed: 3 loại biểu mẫu (khớp kFormTypes phía frontend)
-- DO UPDATE để DB cũ (đã seed bản TEXT[]) được làm mới sang JSONB có label/hint.
-- ───────────────────────────────────────────────────────────────────────────
INSERT INTO tblFormType (slug, name, description, requires_front, requires_back, required_fields)
VALUES
    ('atm_open', 'Đăng ký mở thẻ ATM', 'Kê khai thông tin cá nhân khi mở tài khoản thanh toán.', TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone', 'label', 'Số điện thoại liên hệ', 'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'occupation', 'label', 'Nghề nghiệp hiện tại', 'hint', 'Ví dụ: Nhân viên văn phòng')
     )),
    ('health_declare', 'Khai báo y tế', 'Tờ khai sức khỏe phục vụ khám chữa bệnh.', TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone', 'label', 'Số điện thoại liên hệ', 'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'symptoms', 'label', 'Triệu chứng (nếu có)', 'hint', 'Nhập triệu chứng hoặc ghi "Không"')
     )),
    ('service_contract', 'Hợp đồng dịch vụ', 'Đăng ký ký hợp đồng cung cấp dịch vụ.', TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone', 'label', 'Số điện thoại liên hệ', 'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'company', 'label', 'Công ty / đơn vị', 'hint', 'Nhập tên công ty nếu ký thay tổ chức')
     ))
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    requires_front = EXCLUDED.requires_front,
    requires_back = EXCLUDED.requires_back,
    required_fields = EXCLUDED.required_fields;