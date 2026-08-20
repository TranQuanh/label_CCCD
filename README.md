# CCCD VLM Extraction

Trích xuất thông tin thẻ **Căn cước công dân (CCCD)** tiếng Việt bằng
Vision-Language Model fine-tune **QLoRA 4-bit**, kèm ứng dụng di động e-KYC.
Chạy được trên một GPU nhỏ (Colab T4 15GB / L4 24GB).

## Ba phần

| Thư mục | Vai trò | Ngôn ngữ |
|---|---|---|
| [`frontend/`](frontend/) | App Flutter: đăng nhập (JWT) + quét 2 mặt thẻ → đối chiếu → xuất biểu mẫu PDF + quản trị người dùng (admin) | Dart |
| [`backend/`](backend/) | Service FastAPI: **API `/api/v1/*` (auth + RBAC + audit) + serving `/extract-cccd/*`** (model 4-bit + adapter) | Python |
| [`model/`](model/) | Pipeline ML: gán nhãn → huấn luyện → đánh giá → so sánh kiến trúc | Python |

Thư mục phụ: [`docs/`](docs/) (kiến trúc, kế hoạch so sánh, changelog, phân tích
kết quả), `data/` · `checkpoints/` · `result_*/` (dữ liệu và artifact, không commit).

Ở gốc còn ba thư mục **shim** — `src/`, `app/`, `scripts/` — không chứa mã nguồn,
chỉ trỏ về vị trí thật để mọi lệnh và notebook Colab cũ vẫn chạy nguyên vẹn.
Sửa code ở `model/` và `backend/`, đừng sửa shim.

```
frontend/  lib/{core,data,features}/     ← app Flutter
backend/   main.py                       ← FastAPI (shim: app/)
model/     src/  scripts/  notebooks/    ← pipeline ML (shim: src/, scripts/)
docs/      ARCHITECTURE · CHANGELOG · VLM_COMPARISON_PLAN · Discussion
```

## Vòng đời ML — 4 giai đoạn

| # | Giai đoạn | Notebook | Module chính |
|---|-----------|----------|--------------|
| 1 | Gán nhãn (human-in-the-loop) | `model/notebooks/01_data_labeling.ipynb` | `model/src/data_pipeline/{auto_label,label_tool}.py` |
| 2 | Fine-tune QLoRA | `model/notebooks/02_finetuning.ipynb` | `model/src/data_pipeline/prepare_dataset.py`, `model/src/models/lora_setup.py`, `model/scripts/train.py` |
| 3 | Đánh giá (FA/CER/F1) | `model/notebooks/03_evaluation.ipynb` | `model/src/utils/metrics.py`, `model/scripts/evaluate.py` |
| 4 | Triển khai API | `model/notebooks/04_deployment.ipynb` | `backend/main.py` |
| 5 | So sánh kiến trúc | `model/notebooks/05_model_comparison.ipynb` | `model/scripts/compare_models.py` |

## Cài đặt

```bash
pip install -r requirements.txt
# PyTorch + CUDA (nếu chạy local):
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> `bitsandbytes` (4-bit) chỉ chạy trên **Linux / Colab / WSL**, không hỗ trợ
> Windows native.

## Quy trình nhanh

Đường dẫn dưới đây dùng shim ở gốc nên chạy đúng như trước khi tái cấu trúc.

```bash
# 1. Auto-label draft → duyệt tay bằng Gradio
python -m src.data_pipeline.auto_label --input_dir data/raw --result_dir data/draft
python -m src.data_pipeline.label_tool --jsonl data/draft/raw_draft.jsonl \
    --front_dir data/Front --back_dir data/Back --share

# 2. Chia 80/10/10 (augment train-only) → fine-tune QLoRA
python -m src.data_pipeline.prepare_dataset --input data/draft/raw_draft.jsonl --out_dir data/dataset
python scripts/train.py --train_jsonl data/dataset/train.jsonl --val_jsonl data/dataset/val.jsonl \
    --model_name OpenGVLab/InternVL3_5-2B-HF --output_dir checkpoints/internvl-cccd-lora-front

# 3. Đánh giá trên test
python scripts/evaluate.py --test_jsonl data/dataset/test.jsonl \
    --adapter_dir checkpoints/internvl-cccd-lora-front

# 4. Serve API (một model mỗi tiến trình, cả hai adapter mặt trước/sau dùng chung base)
MODEL_KEY=internvl CHECKPOINT_DIR=checkpoints uvicorn backend.main:app --host 0.0.0.0 --port 8000
# POST 1 ảnh  → http://localhost:8000/extract-cccd/?side=truoc
# POST N ảnh  → http://localhost:8000/extract-cccd/batch
# API người dùng → http://localhost:8000/api/v1/*   (auth/register, auth/login, users, audit-logs, forms)
# Chạy không cần GPU để test luồng user: SKIP_MODEL_LOAD=1 uvicorn backend.main:app --port 8000

# 5. App di động (xem frontend/README.md để dựng scaffold trước)
cd frontend && flutter run --dart-define=USE_MOCK=false \
                           --dart-define=API_BASE_URL=http://<IP-máy-chạy-API>:8000
```

## Điểm thiết kế nổi bật

- **Một nguồn chân lý cho prompt & schema**: `model/src/utils/cccd_schema.py` —
  prompt và danh sách trường phải giống hệt nhau ở lúc gán nhãn, huấn luyện,
  đánh giá và phục vụ.
- **Một nguồn chân lý cho cấu hình đa model**: `model/src/models/vlm_registry.py` —
  tách rõ cái phải **giống nhau** giữa các kiến trúc (LoRA target, ảnh 1024px)
  khỏi cái **bị kiến trúc ép** (max_length, processor kwargs).
- **Xác thực + RBAC thật**: backend `/api/v1/*` (JWT + refresh token, bcrypt,
  lockout, thu hồi token khi đổi quyền, audit log append-only) — xem
  [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) cho 11 quyết định chốt các mâu
  thuẫn giữa các tài liệu yêu cầu.
- **Vừa một GPU nhỏ**: NF4 + double-quant, đóng băng vision tower, LoRA chỉ trên
  language model; InternVL3.5-2B chạy hết 2.6 GB VRAM.
- **Mọi artifact lưu Google Drive** → Colab ngắt không mất tiến độ.

## Hai điều cần biết trước khi đọc số liệu

- **Split hiện tại chia theo *ảnh*, không theo *thẻ*.** `prepare_dataset.group_key`
  trả về tên file, trong khi 1436 ảnh mặt trước chỉ thuộc 689 thẻ khác nhau ⇒
  77,1% ảnh test có ảnh khác của cùng số CCCD nằm trong tập train. Field Accuracy
  mặt trước vì thế là **ước lượng lạc quan**. Chi tiết và cách khắc phục:
  [docs/Discussion.md](docs/Discussion.md).
- **Nhãn có nhiễu đo được**: 46,3% nhóm ảnh cùng một tấm thẻ được gán nhãn khác
  nhau; phần lỗi còn lại của model tập trung đúng vào những ô đó.

> Khi tài liệu trong `docs/` mâu thuẫn với code, **tin code** — xem mục
> "Docs vs. code drift" trong [CLAUDE.md](CLAUDE.md).
