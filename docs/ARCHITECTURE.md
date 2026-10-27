# CCCD VLM Extraction — Kiến trúc dự án

Trích xuất thông tin thẻ CCCD tiếng Việt bằng Visual Language Model + **QLoRA**,
đóng gói thành dịch vụ e-KYC 3 tầng:

```
frontend/  Flutter app (xác thực + quét thẻ + hồ sơ)
backend/   FastAPI (API /api/v1 + serving /extract-cccd/)
model/     ML pipeline (auto-label → fine-tune → evaluate)
docs/      ARCHITECTURE · PRODUCT_SPEC · VLM_COMPARISON_PLAN · Discussion
```

Các thư mục `src/`, `app/`, `scripts/` ở gốc repo là **shim** trỏ về `model/src`,
`backend/`, `model/scripts` để mọi lệnh/notebook cũ chạy nguyên vẹn. Thiết kế
module hóa, chạy được trên **Google Colab T4 15GB**.

| Vai trò | Model (tải local từ HuggingFace) | Loader class |
|---------|----------------------------------|--------------|
| Sinh ground truth (auto-label) | `Qwen/Qwen2.5-VL-7B-Instruct` | `Qwen2_5_VLForConditionalGeneration` |
| Fine-tune & Deploy | `Qwen/Qwen3-VL-8B-Instruct` | `Qwen3VLForConditionalGeneration` |

> ⚠️ Qwen3-VL cần `transformers` cài từ source:
> `pip install git+https://github.com/huggingface/transformers`. Hai phần dùng
> hai model khác nhau → **base lúc deploy phải khớp base lúc fine-tune (Qwen3-VL-8B)**.

## Cấu trúc thư mục

```
label_CCCD/
├── backend/                       # ⭐ FastAPI: API người dùng + serving VLM
│   ├── main.py                    #   app FastAPI; router /api/v1 + /extract-cccd/*
│   ├── config.py                  #   cấu hình qua biến môi trường
│   ├── schema.sql                 #   6 bảng + view v_scan_record_masked + seed forms
│   ├── db.py  redis_client.py     #   PostgreSQL (psycopg) + Redis (token blacklist)
│   ├── security.py                #   bcrypt + JWT + lockout
│   ├── deps.py                    #   get_current_user / require_admin / ROLE_LEVELS
│   ├── auth.py  users.py          #   /auth/* (gồm change-password), /users/* (admin, RBAC)
│   ├── audit.py  forms.py         #   /audit-logs (append-only), /forms (+ POST/PUT admin)
│   ├── records.py                 #   /scan-records (submit, lịch sử, duyệt)
│   └── smoke_test.py              #   smoke test 72 case (chạy không cần GPU)
├── frontend/                      # ⭐ Flutter app — xem docs/PRODUCT_SPEC.md
├── model/                         # ⭐ ML pipeline (auto-label → fine-tune → evaluate)
│   ├── src/                       #   utils/ data_pipeline/ models/
│   └── scripts/                   #   train.py evaluate.py compare_models.py benchmark.py
├── src/  app/  scripts/           # SHIM → model/src, backend/, model/scripts (giữ lệnh cũ)
├── notebooks/  docs/  requirements.txt
└── data/  checkpoints/  result_*   # artifact (gitignored)
```

## Vòng đời ML (chạy lần lượt 4 notebook)

| Giai đoạn | Notebook | Output trên Drive |
|-----------|----------|-------------------|
| 1. Gán nhãn (HITL) | `01_data_labeling` | `data/draft/raw_draft.jsonl` |
| 2. Fine-tune QLoRA | `02_finetuning` | `data/dataset/*.jsonl`, `checkpoints/.../adapter` |
| 3. Đánh giá | `03_evaluation` | `result/eval_report.json` |
| 4. Triển khai | `04_deployment` | API public qua ngrok |

## Quyết định thiết kế chính

- **Prompt động theo mặt thẻ** (`cccd_schema.build_user_prompt`): tên file chứa
  `front`→mặt trước, `back`→mặt sau → model không bịa trường của mặt còn lại.
- **Chống data leakage**: split theo *nhóm thẻ* (gộp front/back cùng người),
  augment **chỉ tập train**.
- **Vừa T4 15GB**: 4-bit NF4 + double-quant, gradient checkpointing, freeze
  vision tower, `paged_adamw_8bit`, `compute_dtype=float16` (Turing không có bf16).
- **Loss đúng chỗ**: collator mask toàn bộ prompt + token ảnh (`-100`), chỉ tính
  loss trên câu trả lời JSON của assistant.
- **Mọi artifact lưu Google Drive** → Colab ngắt không mất tiến độ.

## Backend: API người dùng (`/api/v1/*`) và serving (`/extract-cccd/*`)

Hai lớp API **tách biệt** trong cùng một FastAPI app (`backend/main.py`):

| Lớp | Đường dẫn | Xác thực | Mục đích |
|-----|-----------|----------|----------|
| Ứng dụng | `/api/v1/*` | JWT Bearer (đa số) | đăng nhập/đăng ký/đổi mật khẩu, quản lý user (admin), audit log, danh mục biểu mẫu (CRUD admin), **lưu hồ sơ + lịch sử + hàng đợi duyệt** |
| Serving | `/extract-cccd/*` | — (nội bộ) | luồng VLM: trích xuất 1 ảnh / batch; benchmark & notebooks dùng thẳng |

`/health` báo `status`, `db`, `redis`, `lite_mode` (model tắt khi `SKIP_MODEL_LOAD=1`
để chạy/test không cần GPU).

### Lược đồ dữ liệu (`backend/schema.sql`) — 6 bảng + 1 view

- `tblUser` — `username` UNIQUE, `email` UNIQUE, `password_hash` (bcrypt),
  `full_name`, `role` (`admin`/`operator`/`viewer`), `is_active`,
  `failed_login_count`/`locked_until` (lockout), **`token_version`**.
- `tblRefreshToken` — refresh token (băm SHA-256), `revoked_at`, TTL 30 ngày.
- `tblFormType` — **UUID PK + `slug` UNIQUE** (slug = khóa nghiệp vụ, API dùng
  slug; `forms.py resolve_form_uuid()` là nơi duy nhất map slug→UUID).
  **P2: `required_fields` là JSONB `[{key,label,hint}]`** — server là nguồn duy
  nhất mô tả biểu mẫu; frontend không hardcode trường bổ sung ở chế độ thật.
- `tblBatchJob` / `tblScanRecord` — hàng đợi & kết quả trích xuất.
  **P2: `tblScanRecord` có `code` (mã hồ sơ server cấp, `HS<yyyyMMdd>-<6số>`)
  và `supp` (JSONB — trường bổ sung theo biểu mẫu).** `review_status`
  (`pending`/`reviewed`) = chốt mâu thuẫn **HITL vs Batch**: kết quả batch cũng
  phải được duyệt trước khi vào lịch sử/xuất.
- `tblAuditLog` — **append-only**, ghi từ mọi sự kiện quan trọng
  (register/login/logout/đổi role/khóa/đổi mật khẩu/tạo-duyệt hồ sơ); không có
  endpoint sửa/xóa.
- `v_scan_record_masked` — view cho viewer: **chỉ record đã duyệt**, CCCD được
  che (`left(so_cccd,6) || '******'`). (Quyết định chốt **Viewer vs RLS**: RLS ở
  bảng gốc cho owner+admin; viewer đọc qua view này.)

### Xác thực & RBAC (`backend/security.py`, `deps.py`, `auth.py`)

- Mật khẩu ≥8 ký tự, có chữ và số; băm bcrypt.
- JWT HS256, claims `sub` (UUID), `role`, `tok_ver`, `jti`, `exp`, `type`.
  Access 60 phút, refresh 30 ngày (băm trong DB, thu hồi được).
- **Đăng nhập bằng email HOẶC tên đăng nhập** — một field `identifier`, backend
  phân biệt qua `@` (chốt mâu thuẫn login field; giữ nguyên theo yêu cầu).
- Lockout: 5 lần sai → khóa 15 phút; audit + ghi `failed_login_count`.
- **Thu hồi quyền**: đổi role / khóa tài khoản → `token_version++` + revoke mọi
  refresh token → JWT cũ vô hiệu ngay, người đó phải đăng nhập lại.
- **P2: Đổi mật khẩu** (`POST /auth/change-password`) — **không OTP** (P2 quyết
  định: không có hạ tầng SMS/email thật), chỉ xác minh `current_password`; đổi
  hash + `token_version++` + revoke refresh token → phiên khác bị đăng xuất.
- Guards: không tự hạ quyền bản thân; không khóa/hạ quyền admin cuối cùng.
- Logout: revoke refresh + blacklist `jti` access vào Redis (key `jwt:blacklist`).

### Hồ sơ trích xuất (P2 — `backend/records.py`)

- **`POST /scan-records`** (operator+): nhận `form_id` + `extracted_data` +
  `supp` + `card_side`; server sinh `code` (`_generate_code()`, retry khi trùng),
  `review_status = 'pending'`, audit `record.create`. 404 nếu form không tồn tại,
  400 nếu `extracted_data` rỗng.
- **`GET /scan-records`**: viewer → `v_scan_record_masked` (chỉ đã duyệt, số CCCD
  che, response có cờ `masked:true`); operator → hồ sơ của mình; admin → của mình
  hoặc `?user_id=`. Phân trang `limit/offset`.
- **`GET /scan-records/review-queue`** (operator+): hồ sơ `pending`, lọc
  `form_id`/`card_side`.
- **`PATCH /scan-records/{id}/review`** (operator+): `pending` ↔ `reviewed`, audit
  `record.review`. RBAC áp dụng ở tầng app (RLS chưa bật trên bảng gốc).

### Mâu thuẫn tài liệu — chốt quyết định (P1)

22 mâu thuẫn phát hiện khi đối chiếu 6 tài liệu yêu cầu → 11 nhóm, đã chốt:

1. **HITL vs Batch** → `review_status`; batch vẫn phải duyệt trước khi hiển thị.
2. **Không lưu ảnh vs ZIP batch** → không lưu ảnh lâu dài; batch dàn tạm trong
   `TMP_DIR` với TTL + dọn dẹp.
3. **Lịch sử** → PostgreSQL là nguồn chân lý; thiết bị chỉ cache/mock.
4. **Serving** → in-process FastAPI (KHÔNG vLLM/TGI); ghi rõ ở đây và README.
5. **Cây thư mục** → `backend/model/frontend/docs` chuẩn + shim ở gốc.
6. **Trường đăng nhập** → giữ `username` + `email`, login bằng identifier (đã
   chốt giữ nguyên theo yêu cầu, không thay đổi).
7. **`tok_ver`** → cột `token_version` trong `tblUser` (đã thêm).
8. **Đặt tên trường** → tiếng Việt snake_case (`so_cccd`…) ở VLM/DB JSONB/API;
   camelCase chỉ nội bộ app qua `frontKeyMap`; bỏ `id_number`.
9. **ID biểu mẫu** → UUID PK + slug UNIQUE; API dùng slug.
10. **Endpoint** → app API dưới `/api/v1/*`; `/extract-cccd/*` là serving nội bộ.
11. **Viewer vs RLS** → RLS bảng gốc (owner+admin) + view che cho viewer.

### Chốt P2 (quyết định phạm vi P2)

- **Đổi mật khẩu**: KHÔNG dùng OTP — không có hạ tầng SMS/email thật; chỉ xác
  minh mật khẩu hiện tại (`POST /auth/change-password`).
- **Danh mục biểu mẫu**: `required_fields` chuyển TEXT[] → **JSONB
  `[{key,label,hint}]`** để `/forms` là nguồn duy nhất mô tả biểu mẫu (gồm cả
  label/hint tiếng Việt); frontend mock vẫn giữ `kFormTypes`.
- **Tab Duyệt trên UI** làm trong P2 (không chỉ API) — operator/admin thấy tab
  "Duyệt" trong khung chính; viewer không thấy.
- **Vai trò viewer có UI** trong P2: xem lịch sử qua bản che, không thấy tab Duyệt.
- **Đặt tên API/DB**: tiếng Việt snake_case (`so_cccd`) ở DB JSONB + API; app
  convert camelCase↔snake_case qua `serverKeyMap`/`toServerJson`/`fromServerJson`.

## Lệnh chạy nhanh (ngoài Colab)

```bash
# B1 — auto label
python -m src.data_pipeline.auto_label --input_dir data/raw --result_dir data/draft

# B1 — duyệt tay
python -m src.data_pipeline.label_tool --jsonl data/draft/raw_draft.jsonl --image_root .

# B2 — chia + fine-tune
python -m src.data_pipeline.prepare_dataset --input data/draft/raw_draft.jsonl --out_dir data/dataset
python scripts/train.py --train_jsonl data/dataset/train.jsonl --val_jsonl data/dataset/val.jsonl

# B3 — đánh giá
python scripts/evaluate.py --test_jsonl data/dataset/test.jsonl --adapter_dir checkpoints/qwen3vl-cccd-lora

# B4 — serve
ADAPTER_DIR=checkpoints/qwen3vl-cccd-lora uvicorn app.main:app --port 8000
```

> **Lưu ý import**: `scripts/train.py` và `scripts/evaluate.py` tự thêm repo root
> vào `sys.path`, nên chạy được cả `python scripts/train.py` lẫn `python -m`.
> Các module trong `src/` phải chạy bằng `python -m src.<...>` (từ repo root).

## Chuẩn bị trên Google Drive (cho 4 notebook)

Các notebook copy source từ Drive sang runtime bằng:
`cp -r /content/drive/MyDrive/cccd_project/code /content/cccd`.

Vì vậy cần dựng sẵn cây thư mục này trên Drive **một lần**:

```
MyDrive/cccd_project/
├── code/                       # ⬅ upload toàn bộ source repo này vào đây
│   ├── src/  scripts/  app/  requirements.txt ...
├── data/
│   ├── raw/                    # ảnh CCCD gốc (đặt tên có 'front'/'back')
│   ├── draft/                  # auto_label sinh ra (B1)
│   ├── dataset/                # train/val/test.jsonl (B2)
│   └── aug/                    # ảnh augment train (B2)
├── models/                     # model tải từ HuggingFace về local (B1/B2/B3/B4)
│   ├── Qwen2.5-VL-7B-Instruct/ # dùng cho auto-label (B1)
│   └── Qwen3-VL-8B-Instruct/   # base fine-tune & deploy (B2/B3/B4)
├── checkpoints/
│   └── qwen3vl-cccd-lora/      # LoRA adapter (B2) — nguồn cho B3, B4
└── result/
    └── eval_report.json        # báo cáo metric (B3)
```

> Thay vì `cp` từ Drive, có thể `git clone` repo của bạn vào `/content/cccd`.
> Điểm cốt lõi: **mọi dữ liệu/checkpoint trỏ vào `MyDrive/cccd_project`** để
> sống sót qua các lần Colab ngắt kết nối.

## Quy ước đặt tên ảnh (quan trọng)

`cccd_schema.infer_side_from_filename` suy mặt thẻ từ tên file:

| Chứa token | Mặt thẻ | Prompt sinh ra |
|------------|---------|----------------|
| `front`, `truoc`, `_mt`, `mattruoc` | **trước** | chỉ hỏi trường mặt trước |
| `back`, `sau`, `_ms`, `matsau` | **sau** | chỉ hỏi trường mặt sau |
| (không khớp) | unknown | hỏi toàn bộ trường |

Ví dụ hợp lệ: `cccd_001_front.jpg`, `cccd_001_back.jpg` → cùng nhóm `cccd_001`
(không bị tách train/test khi split).

## Format JSONL

Record sau khi `prepare_dataset` (đã bỏ `_meta`, chuẩn cho Trainer):

```json
{
  "image": "data/raw/cccd_001_front.jpg",
  "conversations": [
    {"from": "human", "value": "<image>\nĐây là MẶT TRƯỚC của CCCD..."},
    {"from": "gpt",   "value": "{\"so_cccd\": \"0123...\", \"mat_the\": \"truoc\"}"}
  ]
}
```

Bản draft (trước khi duyệt) có thêm khối `_meta`:
`{"side": "truoc", "parse_ok": true, "raw_output": "...", "reviewed": false}`.
`label_tool` đặt `reviewed = true` sau khi người duyệt nhấn **Save**; `prepare_dataset`
mặc định **bỏ** mọi record `reviewed = false` (dùng `--allow_unreviewed` để giữ).

## Chỉ số đánh giá (`metrics.py`)

| Chỉ số | Ý nghĩa | Tốt khi |
|--------|---------|---------|
| **Field Accuracy** | % trường khớp chính xác (sau chuẩn hóa) | càng cao |
| **CER** | Character Error Rate trung bình theo trường | càng thấp |
| **F1 (micro)** | precision/recall mức token toàn bộ trường | càng cao |

Chuẩn hóa trước khi so: NFC Unicode, gộp khoảng trắng, hạ chữ thường, `null`↔`""`.

## Khắc phục sự cố (Colab T4)

| Triệu chứng | Cách xử lý |
|-------------|------------|
| `CUDA out of memory` lúc train | giảm `--max_length` (1536→1024), giữ `--batch_size 1`, tăng `--grad_accum` |
| OOM lúc serve | đảm bảo adapter load trên **base 4-bit** (mặc định); giảm `MAX_NEW_TOKENS` |
| `bf16 not supported` | T4 là Turing → dùng `--compute_dtype float16` (mặc định) |
| `bitsandbytes` lỗi trên Windows | chạy trên Colab/Linux hoặc WSL; bnb 4-bit không hỗ trợ Windows native |
| Gradio không hiện ảnh | kiểm tra `--image_root` resolve đúng tới ảnh trong record |
| Import `src`/`app` lỗi | chạy từ repo root; script đã tự vá `sys.path` |

