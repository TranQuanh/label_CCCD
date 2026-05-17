# CCCD Labeler v3 - Qwen3-VL-8B

Auto-label ảnh CCCD → JSONL đúng format fine-tuning Qwen3-VL chính thức.

---

## Format JSONL chuẩn (qwen-vl-finetune official)

```json
{
  "image": "data/train/cccd_001.jpg",
  "conversations": [
    {
      "from": "human",
      "value": "<image>\nĐọc ảnh CCCD và trích xuất thông tin ra JSON..."
    },
    {
      "from": "gpt",
      "value": "{\"so_cccd\": \"001234567890\", \"ho_va_ten\": \"NGUYỄN VĂN A\", ...}"
    }
  ]
}
```

**Quy tắc bắt buộc:**
- Field `image`: path đến file ảnh
- Field `conversations`: list 2 phần tử
  - `[0].from` = `"human"` và `value` phải có tag `<image>` ở đầu
  - `[1].from` = `"gpt"` và `value` là JSON string của dữ liệu extract
- Không dùng `role/content` (đó là format inference, không phải training)

---

## Cài đặt

```bash
# 1. transformers từ source (bắt buộc cho Qwen3-VL)
pip install git+https://github.com/huggingface/transformers

# 2. Các thư viện còn lại
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt
```

---

## Test trên máy local trước

```bash
# Chỉ test môi trường + format (không cần GPU, không load model)
python test_local.py --skip_inference

# Test đầy đủ kể cả inference (cần GPU ≥ 16GB)
python test_local.py

# Validate file JSONL có sẵn
python test_local.py --validate_file ./result/train_labels.jsonl
```

---

## Chạy label

```bash
# Label từng split
python label_cccd.py --split train --data_dir ./data --result_dir ./result
python label_cccd.py --split test  --data_dir ./data --result_dir ./result
python label_cccd.py --split valid --data_dir ./data --result_dir ./result

# Label tất cả 1 lần
python label_cccd.py --split all --data_dir ./data --result_dir ./result

# Dùng model local (server không có internet)
python label_cccd.py --split all \
  --model_name ./models/Qwen3-VL-8B-Instruct \
  --data_dir ./data --result_dir ./result
```

---

## Cấu trúc thư mục

```
project/
├── data/
│   ├── train/    ← ảnh CCCD
│   ├── test/
│   └── valid/
├── result/       ← tự động tạo
│   ├── train_labels.jsonl
│   ├── test_labels.jsonl
│   └── valid_labels.jsonl
├── label_cccd.py
├── test_local.py
└── requirements.txt
```

---

## Tải model về local

```bash
pip install huggingface_hub
huggingface-cli download Qwen/Qwen3-VL-8B-Instruct \
  --local-dir ./models/Qwen3-VL-8B-Instruct
```

---

## Dùng JSONL để fine-tune (ms-swift)

```bash
pip install ms-swift>=4.0

swift sft \
  --model Qwen/Qwen3-VL-8B-Instruct \
  --dataset result/train_labels.jsonl \
  --val_dataset result/valid_labels.jsonl \
  --train_type lora \
  --output_dir ./output_lora
```

---

## Ghi chú về field `_meta`

Mỗi record có thêm field `_meta` (debug, không ảnh hưởng training):
```json
"_meta": {
  "parse_ok": true,      ← model trả về JSON hợp lệ
  "raw_output": "..."    ← raw text của model để debug
}
```
`parse_ok: false` → gpt value là raw text, cần review lại trước khi train.
# label_CCCD
