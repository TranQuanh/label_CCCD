# So sánh VLM fine-tune — trích xuất CCCD

Sinh tự động bởi `scripts/compare_models.py`. Mọi dòng dùng **cùng tập test, cùng prompt/schema, cùng `metrics.evaluate`, cùng greedy decoding**.

## Bảng chính

| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |
|---|---|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 2.3 | 0.3059 | 0.9767 | +0.6708 | 0.0119 | 0.9920 | 1.0000 | 2618.3 | 10965.3 / 11637.9 | 1.1592 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 10.6 | 0.4736 | 0.9720 | +0.4984 | 0.0144 | 0.9872 | 1.0000 | 7970.4 | 14549.8 / 15390.8 | 0.8809 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 3.7 | 0.4006 | 0.9783 | +0.5777 | 0.0103 | 0.9942 | 1.0000 | 2768.4 | 13230.1 / 14090.9 | 1.4503 |

> Δ FA = FA(fine-tuned) − FA(zero-shot): đóng góp thuần của QLoRA cho kiến trúc đó.
> Các cột CER / F1 / parse / VRAM / latency lấy từ dòng fine-tuned (nếu có).

## Baseline OCR truyền thống

Không dùng `train.jsonl` ở bất kỳ khâu nào ⇒ **không có cột Δ FA**. Cùng tập test, cùng schema, cùng `metrics.evaluate`, cùng tiền xử lý ảnh 1024px như các VLM.

| Baseline | Detector | Recognizer | FA | CER ↓ | micro-F1 | Trường điền được | Dòng OCR/ảnh | Latency p50/p95 (ms) | Ảnh 1024px |
|---|---|---|---|---|---|---|---|---|---|
| PP-OCR det + VietOCR rec (vgg_transformer) | ppocr_db | vietocr | 0.5714 | 0.1092 | 0.8193 | 0.9767 | 15.5 | 10110.7 / 13158.8 | có |
| PaddleOCR PP-OCR (det+rec, lang=vi) | ppocr_db | ppocr_crnn | 0.4860 | 0.1677 | 0.4215 | 0.9674 | 15.2 | 35232.4 / 36521.2 | có |

## Xếp hạng chung (mọi lần chạy)

| Model / Baseline | Chế độ | FA | CER ↓ | micro-F1 | Latency p50/p95 (ms) |
|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | fine_tuned | 0.9783 | 0.0103 | 0.9942 | 13230.1 / 14090.9 |
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | fine_tuned | 0.9767 | 0.0119 | 0.9920 | 10965.3 / 11637.9 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | fine_tuned | 0.9720 | 0.0144 | 0.9872 | 14549.8 / 15390.8 |
| PP-OCR det + VietOCR rec (vgg_transformer) | rule_based | 0.5714 | 0.1092 | 0.8193 | 10110.7 / 13158.8 |
| PaddleOCR PP-OCR (det+rec, lang=vi) | rule_based | 0.4860 | 0.1677 | 0.4215 | 35232.4 / 36521.2 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | zero_shot | 0.4736 | 0.6975 | 0.2758 | 5447.1 / 6625.5 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | zero_shot | 0.4006 | 3.1476 | 0.5003 | 8075.5 / 16916.8 |
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | zero_shot | 0.3059 | 1.4363 | 0.5393 | 5023.3 / 7290.2 |

> `rule_based` = baseline OCR, **chưa từng thấy dữ liệu train**. Đặt cạnh `fine_tuned` để thấy khoảng cách, không phải để kết luận kiến trúc nào hơn.

## FA theo từng trường

Mỗi model lấy bản fine-tuned; baseline OCR lấy bản `rule_based`.

### Mặt trước

| Trường | internvl | llama_vision | paddle_vietocr (rule_based) | paddleocr (rule_based) | qwen |
|---|---|---|---|---|---|
| `mat_the` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Mặt sau

| Trường | internvl | llama_vision | paddle_vietocr (rule_based) | paddleocr (rule_based) | qwen |
|---|---|---|---|---|---|
| `dac_diem_nhan_dang` | 0.9068 | 0.9006 | 0.3292 | 0.0000 | 0.9130 |
| `ngay_cap` | 1.0000 | 0.9876 | 0.9565 | 0.9441 | 1.0000 |
| `noi_cap` | 1.0000 | 1.0000 | 0.0000 | 0.0000 | 1.0000 |
| `mat_the` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Trước khi kết luận

Tập test ~10% dữ liệu ⇒ chênh lệch vài % FA có thể là nhiễu. Cần ≥2 seed, bootstrap CI 95% cho FA, và McNemar test trên exact-match từng trường khi so từng cặp model (VLM_COMPARISON_PLAN.md mục 9).
