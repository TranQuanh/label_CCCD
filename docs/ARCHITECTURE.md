# CCCD VLM Extraction — Kiến trúc dự án

Trích xuất thông tin thẻ CCCD tiếng Việt bằng Visual Language Model + **QLoRA**.
Thiết kế module hóa, chạy được trên **Google Colab T4 15GB**.

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
├── src/
│   ├── utils/
│   │   ├── cccd_schema.py      # ⭐ Single source of truth: prompt động front/back, field schema
│   │   └── metrics.py          # FA / CER / F1
│   ├── data_pipeline/         # (đổi tên từ 'data' để không trùng thư mục dữ liệu data/)
│   │   ├── auto_label.py       # B1: auto-label draft bằng Qwen-VL (prompt theo mặt thẻ)
│   │   ├── label_tool.py       # B2: Gradio UI duyệt & sửa tay (overwrite vào JSONL)
│   │   └── prepare_dataset.py  # B3: split 80/10/10 group-aware + augment train-only
│   └── models/
│       └── lora_setup.py       # Load 4-bit NF4 + grad checkpointing + PEFT/LoRA
├── scripts/
│   ├── train.py                # Fine-tune QLoRA bằng HF Trainer + collator mask prompt
│   └── evaluate.py             # Chạy test set → FA/CER/F1 → eval_report.json
├── app/
│   └── main.py                 # FastAPI /extract-cccd/ (base 4-bit + LoRA adapter)
├── notebooks/
│   ├── 01_data_labeling.ipynb  # ┐
│   ├── 02_finetuning.ipynb     # ├ 4 giai đoạn, đều mount Drive + lưu artifact ra Drive
│   ├── 03_evaluation.ipynb     # │
│   └── 04_deployment.ipynb     # ┘
└── requirements.txt
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

