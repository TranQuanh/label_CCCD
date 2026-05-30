# CCCD Labeler

Auto-label ảnh CCCD bằng **Qwen2.5-VL-7B-Instruct** chạy local → xuất JSONL chuẩn fine-tuning.

---

## Yêu cầu phần cứng

| | Tối thiểu | Khuyến nghị |
|---|---|---|
| GPU VRAM | 8 GB (4-bit AWQ) | 16 GB (bfloat16) |
| RAM | 32 GB | 64 GB |
| Disk | 20 GB | 50 GB |
| CUDA | 11.8+ | 12.1+ |

> Máy local yếu (RTX 3050 4GB): chạy `test_local.py --skip_inference` để kiểm tra format, rồi đưa lên server label thật.

---

## Cài đặt

```bash
# PyTorch (CUDA 12.1)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# Các thư viện còn lại
pip install -r requirements.txt
```

Không cần cài transformers từ source — Qwen2.5-VL-7B chạy được với `transformers>=4.49.0` trên PyPI.

---

## Cấu trúc thư mục

```
project/
├── data/
│   ├── train/          ← ảnh CCCD (.jpg / .png)
│   ├── test/
│   └── valid/
├── result/             ← tự động tạo
│   ├── train_labels.jsonl
│   ├── test_labels.jsonl
│   ├── valid_labels.jsonl
│   ├── .checkpoint_train.json    ← checkpoint tự động (ẩn)
│   ├── .checkpoint_test.json
│   └── .checkpoint_valid.json
├── label_cccd.py
├── test_local.py
└── requirements.txt
```

---

## Test trên máy local trước

```bash
# Chỉ kiểm tra môi trường + format JSONL (không cần GPU, không load model)
python test_local.py --skip_inference

# Test đầy đủ kể cả inference (cần GPU ≥ 8GB)
python test_local.py

# Validate file JSONL đã có sẵn
python test_local.py --validate_file ./result/train_labels.jsonl

# Xem trạng thái checkpoint
python test_local.py --check_checkpoint ./result
```

---

## Chạy label

```bash
# Label từng split
python label_cccd.py --split train --data_dir ./data --result_dir ./result
python label_cccd.py --split test  --data_dir ./data --result_dir ./result
python label_cccd.py --split valid --data_dir ./data --result_dir ./result

# Label tất cả cùng lúc
python label_cccd.py --split all --data_dir ./data --result_dir ./result

# Trỏ thẳng vào 1 folder bất kỳ (không cần cấu trúc train/test/valid)
python label_cccd.py --input_dir ./my_folder --result_dir ./result

# Dùng model đã tải về local (server không có internet)
python label_cccd.py --split all \
  --model_name ./models/Qwen2.5-VL-7B-Instruct \
  --data_dir ./data --result_dir ./result

# Đổi sang Qwen3-VL-8B (server mạnh, cần cài transformers từ source)
python label_cccd.py --split all \
  --model_name Qwen/Qwen3-VL-8B-Instruct \
  --data_dir ./data --result_dir ./result
```

---

## Checkpoint — chạy dở dang không mất dữ liệu

Script tự động lưu tiến độ sau **mỗi ảnh**. Nếu bị ngắt (mất điện, Ctrl+C, server timeout), chạy lại **đúng lệnh cũ** là tiếp tục từ chỗ dừng — không cần flag thêm.

```bash
# Chạy lần đầu → label được 500/1000 ảnh thì bị ngắt
python label_cccd.py --split train --data_dir ./data --result_dir ./result

# Chạy lại đúng lệnh cũ → tự nhận ra checkpoint, tiếp tục từ ảnh 501
python label_cccd.py --split train --data_dir ./data --result_dir ./result

# Muốn label lại từ đầu (xóa checkpoint + output cũ)
python label_cccd.py --split train --data_dir ./data --result_dir ./result --reset
```

Checkpoint lưu tại `result/.checkpoint_<split>.json` và tự xóa khi split hoàn tất 100%.

---

## Tải model về local (server không có internet)

```bash
pip install huggingface_hub

# Qwen2.5-VL-7B (mặc định, nhẹ hơn)
huggingface-cli download Qwen/Qwen2.5-VL-7B-Instruct \
  --local-dir ./models/Qwen2.5-VL-7B-Instruct

# Qwen3-VL-8B (nếu server đủ mạnh)
huggingface-cli download Qwen/Qwen3-VL-8B-Instruct \
  --local-dir ./models/Qwen3-VL-8B-Instruct
```

---

## Format JSONL output

Mỗi dòng là 1 JSON record chuẩn `qwen-vl-finetune`:

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
      "value": "{\"so_cccd\": \"001234567890\", \"ho_va_ten\": \"NGUYỄN VĂN A\", \"ngay_sinh\": \"01/01/1990\", \"gioi_tinh\": \"Nam\", \"quoc_tich\": \"Việt Nam\", \"que_quan\": \"Hà Nội\", \"noi_thuong_tru\": \"123 Đường ABC, Quận 1, TP.HCM\", \"ngay_het_han\": \"01/01/2035\", \"dac_diem_nhan_dang\": null, \"ngay_cap\": null, \"noi_cap\": null, \"mat_the\": \"truoc\"}"
    }
  ],
  "_meta": {
    "parse_ok": true,
    "raw_output": "..."
  }
}
```

**Quy tắc format:**
- `image`: path đến file ảnh (tương đối hoặc tuyệt đối)
- `conversations[0].from` = `"human"`, `value` phải bắt đầu bằng `<image>`
- `conversations[1].from` = `"gpt"`, `value` là JSON string extract từ ảnh
- `_meta`: field debug, không ảnh hưởng training, có thể xóa trước khi train

**`parse_ok: false`** — model trả về output nhưng không parse được thành JSON. `gpt.value` vẫn được lưu dưới dạng raw text. Nên review lại các record này trước khi train.

---

## Fine-tune với dữ liệu đã label

```bash
# ms-swift (khuyến nghị)
pip install ms-swift>=4.0

swift sft \
  --model Qwen/Qwen2.5-VL-7B-Instruct \
  --dataset result/train_labels.jsonl \
  --val_dataset result/valid_labels.jsonl \
  --train_type lora \
  --output_dir ./output_lora

# QLoRA 4-bit (tiết kiệm VRAM, cần ~16-20GB thay vì ~40GB)
swift sft \
  --model Qwen/Qwen2.5-VL-7B-Instruct \
  --dataset result/train_labels.jsonl \
  --val_dataset result/valid_labels.jsonl \
  --train_type lora \
  --quant_bits 4 \
  --output_dir ./output_qlora
```

---

## Đổi model

| Model | VRAM inference | VRAM QLoRA train | Ghi chú |
|---|---|---|---|
| **Qwen2.5-VL-7B** (mặc định) | ~6-7 GB (4-bit) | ~16-20 GB | Cài thẳng, không cần source |
| Qwen3-VL-8B | ~6-7 GB (4-bit) | ~16-20 GB | Cần transformers từ source |

Để đổi model, truyền `--model_name` khi chạy. Không cần sửa code.