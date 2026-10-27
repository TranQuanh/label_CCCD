-- schema.sql
-- ===========
-- Lược đồ cơ sở dữ liệu P1 + P2 — xác thực & RBAC + lịch sử hồ sơ.
-- 6 bảng: tblUser, tblRefreshToken, tblFormType, tblScanRecord, tblAuditLog, tblCccdProfile.
--
-- Thay đổi so với phiên bản cũ:
--   - Thêm tblCccdProfile (nhiều Profile CCCD / user, ngang hàng); chuyển dữ liệu
--     tblUser.cccd_profile cũ sang bảng mới (cột cũ vẫn giữ, DEPRECATED)
--   - Xoá tblBatchJob (chưa dùng, không có router)
--   - Xoá cột confidence_scores khỏi tblScanRecord (luôn NULL, không dùng)
--   - Xoá cột batch_job_id khỏi tblScanRecord (FK tới bảng đã xoá)
--   - Xoá cột raw_output khỏi tblScanRecord (không dùng, chỉ lưu extracted_data)
--   - Xoá cột review_status khỏi tblScanRecord (không dùng flow duyệt)
--
-- Quy ước:
--   - Mọi bảng nghiệp vụ dùng UUID làm PK (gen_random_uuid()).
--   - db.py chạy script này theo kiểu idempotent (CREATE TABLE IF NOT EXISTS)
--     nên có thể chạy lại nhiều lần không lỗi.
--   - Migration (ALTER/DROP) chạy trong DO $$ ... $$ để an toàn trên DB cũ.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";  -- gen_random_uuid()

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. tblUser — tài khoản người dùng
-- ─────────────────────────────────────────────────────────────────────────────
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
    cccd_profile       JSONB,                             -- (DEPRECATED — dùng tblCccdProfile)
    created_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- Migration: thêm cột cccd_profile vào tblUser nếu chưa có
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tbluser' AND column_name = 'cccd_profile'
    ) THEN
        ALTER TABLE tblUser ADD COLUMN cccd_profile JSONB;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. tblRefreshToken — refresh token (hash trong DB, xoay vòng được)
-- ─────────────────────────────────────────────────────────────────────────────
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

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. tblFormType — loại biểu mẫu (slug = khoá nghiệp vụ, id = UUID nội bộ)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblFormType (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug            VARCHAR(100) NOT NULL UNIQUE,    -- atm_open / health_declare / service_contract
    name            VARCHAR(255) NOT NULL,
    description     TEXT,
    requires_front  BOOLEAN NOT NULL DEFAULT TRUE,
    requires_back   BOOLEAN NOT NULL DEFAULT FALSE,
    required_fields JSONB,           -- [{key,label,hint}, ...]
    layout          JSONB,           -- layout specification for supplemental fields
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Migration: required_fields TEXT[] → JSONB (DB cũ)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblformtype'
          AND column_name = 'required_fields'
          AND data_type = 'ARRAY'
    ) THEN
        ALTER TABLE tblFormType
            ALTER COLUMN required_fields TYPE JSONB USING to_jsonb(required_fields);
    END IF;
END $$;

-- Migration: thêm cột layout nếu DB cũ chưa có
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblformtype' AND column_name = 'layout'
    ) THEN
        ALTER TABLE tblFormType ADD COLUMN layout JSONB;
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. tblScanRecord — kết quả trích xuất (lịch sử của người dùng)
--
-- Cột đã xoá so với phiên bản cũ:
--   confidence_scores JSONB  — luôn NULL, không có logic nào set giá trị
--   batch_job_id UUID        — FK tới tblBatchJob đã xoá
--   raw_output TEXT          — không dùng, chỉ lưu extracted_data
--   review_status VARCHAR    — không dùng, bỏ tính năng duyệt hồ sơ
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblScanRecord (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code           VARCHAR(50) UNIQUE NOT NULL,  -- mã hồ sơ do server cấp
    user_id        UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    form_type_id   UUID REFERENCES tblFormType(id),
    extracted_data JSONB NOT NULL,
    supp           JSONB,             -- trường bổ sung theo biểu mẫu {key: value}
    parse_ok       BOOLEAN,
    is_edited      BOOLEAN NOT NULL DEFAULT FALSE,
    card_side      VARCHAR(10) CHECK (card_side IN ('front','back','both')),
    is_hidden      BOOLEAN NOT NULL DEFAULT FALSE,  -- admin ẩn → chủ hồ sơ không thấy
    created_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Migration: thêm các cột còn thiếu trên DB cũ
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

    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE tblScanRecord ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT NOW();
    END IF;
END $$;

-- Migration: cờ ẩn hồ sơ (admin ẩn → chủ hồ sơ không còn thấy trong lịch sử)
ALTER TABLE tblScanRecord ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;

-- Migration: xoá cột confidence_scores nếu DB cũ còn tồn tại
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'confidence_scores'
    ) THEN
        ALTER TABLE tblScanRecord DROP COLUMN confidence_scores CASCADE;
    END IF;
END $$;

-- Migration: xoá cột raw_output nếu DB cũ còn tồn tại
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'raw_output'
    ) THEN
        ALTER TABLE tblScanRecord DROP COLUMN raw_output;
    END IF;
END $$;

-- Migration: xoá cột review_status nếu DB cũ còn tồn tại
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'review_status'
    ) THEN
        ALTER TABLE tblScanRecord DROP COLUMN review_status;
    END IF;
END $$;

-- Migration: xoá cột batch_job_id (bao gồm FK constraint) nếu DB cũ còn tồn tại
DO $$
DECLARE
    fk_name TEXT;
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name) = 'tblscanrecord' AND column_name = 'batch_job_id'
    ) THEN
        -- Tìm và xoá FK constraint trước khi DROP cột
        SELECT tc.constraint_name INTO fk_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema    = kcu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND lower(tc.table_name) = 'tblscanrecord'
          AND kcu.column_name      = 'batch_job_id'
        LIMIT 1;

        IF fk_name IS NOT NULL THEN
            EXECUTE 'ALTER TABLE tblScanRecord DROP CONSTRAINT ' || quote_ident(fk_name);
        END IF;

        ALTER TABLE tblScanRecord DROP COLUMN batch_job_id;
    END IF;
END $$;

-- Migration: xoá bảng tblBatchJob nếu DB cũ còn tồn tại
-- (FK từ tblScanRecord đã được xoá ở bước trên nên DROP IF EXISTS an toàn)
DROP TABLE IF EXISTS tblBatchJob;

CREATE INDEX IF NOT EXISTS idx_scan_user_created ON tblScanRecord(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_data_gin ON tblScanRecord USING GIN (extracted_data);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. tblAuditLog — nhật ký kiểm toán, append-only
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblAuditLog (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES tblUser(id) ON DELETE SET NULL,
    action      VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id   UUID,
    metadata    JSONB,
    ip_address  VARCHAR(45),
    device_info VARCHAR(255),
    created_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_user    ON tblAuditLog(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON tblAuditLog(created_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. tblCccdProfile — Profile CCCD đã lưu của người dùng (nhiều profile / user,
--    các profile ngang hàng, không có profile "mặc định")
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tblCccdProfile (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    data        JSONB NOT NULL,                 -- map snake_case (so_cccd, ho_va_ten, ...)
    created_at  TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cccd_profile_user ON tblCccdProfile(user_id, created_at);

-- Migration: bỏ khái niệm profile mặc định trên DB cũ (index + cột is_default)
DROP INDEX IF EXISTS uq_cccd_profile_default;
ALTER TABLE tblCccdProfile DROP COLUMN IF EXISTS is_default;

-- Migration: chuyển tblUser.cccd_profile (1 object, bản cũ) sang tblCccdProfile
-- (chỉ với user chưa có profile nào → chạy lại nhiều lần không nhân bản dữ liệu)
DO $$
BEGIN
    INSERT INTO tblCccdProfile (user_id, data)
    SELECT u.id, u.cccd_profile
    FROM tblUser u
    WHERE u.cccd_profile IS NOT NULL
      AND jsonb_typeof(u.cccd_profile) = 'object'
      AND u.cccd_profile <> '{}'::jsonb
      AND NOT EXISTS (SELECT 1 FROM tblCccdProfile p WHERE p.user_id = u.id);
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Seed: 3 loại biểu mẫu (khớp kFormTypes phía frontend)
-- ON CONFLICT DO UPDATE để DB cũ được làm mới sang JSONB có label/hint.
-- ─────────────────────────────────────────────────────────────────────────────
INSERT INTO tblFormType (slug, name, description, requires_front, requires_back, required_fields, layout)
VALUES
    ('atm_open',
     'Đăng ký mở thẻ ATM',
     'Kê khai thông tin cá nhân khi mở tài khoản thanh toán.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone',      'label', 'Số điện thoại liên hệ',  'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'occupation', 'label', 'Nghề nghiệp hiện tại',   'hint', 'Ví dụ: Nhân viên văn phòng')
     ),
     NULL),

    ('health_declare',
     'Khai báo y tế',
     'Tờ khai sức khỏe phục vụ khám chữa bệnh.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone',    'label', 'Số điện thoại liên hệ',  'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'symptoms', 'label', 'Triệu chứng (nếu có)',   'hint', 'Nhập triệu chứng hoặc ghi "Không"')
     ),
     NULL),

    ('service_contract',
     'Hợp đồng dịch vụ',
     'Đăng ký ký hợp đồng cung cấp dịch vụ.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key', 'phone',   'label', 'Số điện thoại liên hệ', 'hint', 'Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key', 'company', 'label', 'Công ty / đơn vị',      'hint', 'Nhập tên công ty nếu ký thay tổ chức')
     ),
     NULL)

ON CONFLICT (slug) DO UPDATE SET
    name            = EXCLUDED.name,
    description     = EXCLUDED.description,
    requires_front  = EXCLUDED.requires_front,
    requires_back   = EXCLUDED.requires_back,
    required_fields = EXCLUDED.required_fields,
    layout          = EXCLUDED.layout;
