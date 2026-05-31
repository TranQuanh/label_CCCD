# CCCD VLM Extraction

Trích xuất thông tin thẻ **Căn cước công dân (CCCD)** tiếng Việt bằng Visual
Language Model + fine-tuning **QLoRA**. Chạy được trên **Google Colab T4 15GB**.

| Vai trò | Model | Tải về |
|---------|-------|--------|
| Sinh ground truth (auto-label) | **Qwen2.5-VL-7B-Instruct** | local từ HuggingFace |
| Fine-tune & Deploy | **Qwen3-VL-8B-Instruct** | local từ HuggingFace |

> ⚠️ Qwen3-VL cần `transformers` cài từ **source**: `pip install git+https://github.com/huggingface/transformers`

> 📐 Chi tiết kiến trúc, quy ước đặt tên ảnh, format dữ liệu, metric và khắc phục
> sự cố: xem **[ARCHITECTURE.md](ARCHITECTURE.md)**.

## Vòng đời ML — 4 giai đoạn

| # | Giai đoạn | Notebook | Module chính |
|---|-----------|----------|--------------|
| 1 | Gán nhãn (human-in-the-loop) | `notebooks/01_data_labeling.ipynb` | `src/data_pipeline/auto_label.py`, `src/data_pipeline/label_tool.py` |
| 2 | Fine-tune QLoRA | `notebooks/02_finetuning.ipynb` | `src/data_pipeline/prepare_dataset.py`, `src/models/lora_setup.py`, `scripts/train.py` |
| 3 | Đánh giá (FA/CER/F1) | `notebooks/03_evaluation.ipynb` | `src/utils/metrics.py`, `scripts/evaluate.py` |
| 4 | Triển khai API | `notebooks/04_deployment.ipynb` | `app/main.py` (FastAPI) |

## Cài đặt

```bash
pip install -r requirements.txt
# Riêng PyTorch + CUDA (nếu chạy local):
# pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

> `bitsandbytes` (4-bit) chỉ chạy trên **Linux/Colab/WSL**, không hỗ trợ Windows native.

## Quy trình nhanh

```bash
# 1. Auto-label draft → duyệt tay bằng Gradio
python -m src.data_pipeline.auto_label  --input_dir data/raw --result_dir data/draft
python -m src.data_pipeline.label_tool  --jsonl data/draft/raw_draft.jsonl --image_root . --share

# 2. Chia 80/10/10 (augment train-only) → fine-tune QLoRA (base Qwen3-VL-8B)
python -m src.data_pipeline.prepare_dataset --input data/draft/raw_draft.jsonl --out_dir data/dataset
python scripts/train.py --train_jsonl data/dataset/train.jsonl --val_jsonl data/dataset/val.jsonl \
    --output_dir checkpoints/qwen3vl-cccd-lora

# 3. Đánh giá trên test
python scripts/evaluate.py --test_jsonl data/dataset/test.jsonl \
    --adapter_dir checkpoints/qwen3vl-cccd-lora

# 4. Serve API
ADAPTER_DIR=checkpoints/qwen3vl-cccd-lora uvicorn app.main:app --port 8000
# POST ảnh tới  http://localhost:8000/extract-cccd/
```

## Điểm thiết kế nổi bật

- **Prompt động theo mặt thẻ**: tên file chứa `front`/`back` → chỉ hỏi đúng trường của mặt đó.
- **Chống data leakage**: split theo nhóm thẻ; augment **chỉ tập train**.
- **Vừa T4 15GB**: 4-bit NF4 + double-quant, gradient checkpointing, freeze vision tower, `paged_adamw_8bit`, `float16`.
- **Mọi artifact lưu Google Drive** → Colab ngắt không mất tiến độ.

Trên Colab cần dựng sẵn cây thư mục `MyDrive/cccd_project/` (xem [ARCHITECTURE.md](ARCHITECTURE.md#chuẩn-bị-trên-google-drive-cho-4-notebook)).
