-- migrate_now.sql: sync DB với schema.sql hiện tại

-- 1. tblScanRecord: thêm cột còn thiếu
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblscanrecord' AND column_name='updated_at') THEN
        ALTER TABLE tblScanRecord ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT NOW();
    END IF;
END $$;

ALTER TABLE tblScanRecord ADD COLUMN IF NOT EXISTS is_hidden BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE tblScanRecord ADD COLUMN IF NOT EXISTS supp JSONB;

-- 2. tblScanRecord: xoá cột cũ nếu còn sót
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblscanrecord' AND column_name='confidence_scores') THEN
        ALTER TABLE tblScanRecord DROP COLUMN confidence_scores;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblscanrecord' AND column_name='raw_output') THEN
        ALTER TABLE tblScanRecord DROP COLUMN raw_output;
    END IF;
END $$;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblscanrecord' AND column_name='review_status') THEN
        ALTER TABLE tblScanRecord DROP COLUMN review_status;
    END IF;
END $$;

DO $$
DECLARE
    fk_name TEXT;
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblscanrecord' AND column_name='batch_job_id') THEN
        SELECT tc.constraint_name INTO fk_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND lower(tc.table_name) = 'tblscanrecord'
          AND kcu.column_name = 'batch_job_id'
        LIMIT 1;
        IF fk_name IS NOT NULL THEN
            EXECUTE 'ALTER TABLE tblScanRecord DROP CONSTRAINT ' || quote_ident(fk_name);
        END IF;
        ALTER TABLE tblScanRecord DROP COLUMN batch_job_id;
    END IF;
END $$;

-- 3. Xoá bảng không dùng
DROP TABLE IF EXISTS tblBatchJob CASCADE;

-- 4. tblUser: thêm cccd_profile nếu chưa có
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tbluser' AND column_name='cccd_profile') THEN
        ALTER TABLE tblUser ADD COLUMN cccd_profile JSONB;
    END IF;
END $$;

-- 5. tblCccdProfile: tạo nếu chưa có
CREATE TABLE IF NOT EXISTS tblCccdProfile (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID NOT NULL REFERENCES tblUser(id) ON DELETE CASCADE,
    data       JSONB NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cccd_profile_user ON tblCccdProfile(user_id, created_at);
DROP INDEX IF EXISTS uq_cccd_profile_default;
ALTER TABLE tblCccdProfile DROP COLUMN IF EXISTS is_default;

-- 6. Migration data: tblUser.cccd_profile → tblCccdProfile
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

-- 7. tblFormType: migration
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE lower(table_name)='tblformtype' AND column_name='required_fields' AND data_type='ARRAY'
    ) THEN
        ALTER TABLE tblFormType ALTER COLUMN required_fields TYPE JSONB USING to_jsonb(required_fields);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE lower(table_name)='tblformtype' AND column_name='layout') THEN
        ALTER TABLE tblFormType ADD COLUMN layout JSONB;
    END IF;
END $$;

-- 8. Seed biểu mẫu (cập nhật required_fields mới nhất)
INSERT INTO tblFormType (slug, name, description, requires_front, requires_back, required_fields, layout)
VALUES
    ('atm_open',
     'Đăng ký mở thẻ ATM',
     'Kê khai thông tin cá nhân khi mở tài khoản thanh toán.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key','phone',      'label','Số điện thoại liên hệ',  'hint','Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key','occupation', 'label','Nghề nghiệp hiện tại',   'hint','Ví dụ: Nhân viên văn phòng')
     ), NULL),

    ('health_declare',
     'Khai báo y tế',
     'Tờ khai sức khỏe phục vụ khám chữa bệnh.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key','phone',              'label','Số điện thoại liên hệ',                   'hint','Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key','symptoms',           'label','Triệu chứng (nếu có)',                    'hint','Nhập triệu chứng hoặc ghi "Không"'),
         JSONB_BUILD_OBJECT('key','provinces_visited',  'label','Địa phương đã đi (14 ngày)',              'hint','Liệt kê tỉnh/thành phố, mỗi địa phương một dòng'),
         JSONB_BUILD_OBJECT('key','from_outbreak_area', 'label','Đi đến/ở/về từ vùng dịch',               'hint','co hoặc khong'),
         JSONB_BUILD_OBJECT('key','contact_suspected',  'label','Tiếp xúc người nghi ngờ mắc bệnh',       'hint','co hoặc khong'),
         JSONB_BUILD_OBJECT('key','contact_symptoms',   'label','Tiếp xúc người có triệu chứng sốt/ho',   'hint','co hoặc khong'),
         JSONB_BUILD_OBJECT('key','has_fever_cough',    'label','Hiện có sốt/ho/khó thở/đau họng',        'hint','co hoặc khong'),
         JSONB_BUILD_OBJECT('key','existing_conditions','label','Bệnh nền hiện có',                        'hint','Ghi tên bệnh hoặc "Không có"')
     ), NULL),

    ('service_contract',
     'Hợp đồng dịch vụ',
     'Đăng ký ký hợp đồng cung cấp dịch vụ.',
     TRUE, TRUE,
     JSONB_BUILD_ARRAY(
         JSONB_BUILD_OBJECT('key','phone',   'label','Số điện thoại liên hệ', 'hint','Nhập số điện thoại đang sử dụng'),
         JSONB_BUILD_OBJECT('key','company', 'label','Công ty / đơn vị',      'hint','Nhập tên công ty nếu ký thay tổ chức')
     ), NULL)

ON CONFLICT (slug) DO UPDATE SET
    name            = EXCLUDED.name,
    description     = EXCLUDED.description,
    requires_front  = EXCLUDED.requires_front,
    requires_back   = EXCLUDED.requires_back,
    required_fields = EXCLUDED.required_fields,
    layout          = EXCLUDED.layout;

-- 9. Indexes
CREATE INDEX IF NOT EXISTS idx_scan_user_created ON tblScanRecord(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_scan_data_gin     ON tblScanRecord USING GIN (extracted_data);
CREATE INDEX IF NOT EXISTS idx_audit_user        ON tblAuditLog(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_created     ON tblAuditLog(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_refresh_user      ON tblRefreshToken(user_id);

SELECT 'Migration hoàn tất ✓' AS result;
