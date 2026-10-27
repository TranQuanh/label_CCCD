# So sánh VLM fine-tune — trích xuất CCCD

Sinh tự động bởi `scripts/compare_models.py`. Mọi dòng dùng **cùng tập test, cùng prompt/schema, cùng `metrics.evaluate`, cùng greedy decoding**.

## Bảng chính

| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |
|---|---|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 2.3 | 0.6111 | 0.9452 | +0.3341 | 0.0040 | 0.9833 | 1.0000 | 2612.3 | 17174.5 / 18736.6 | 1.1592 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 10.6 | 0.4753 | 0.9437 | +0.4684 | 0.0045 | 0.9823 | 1.0000 | 7970.4 | 19852.7 / 21365.3 | 0.8809 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 3.7 | 0.6188 | 0.9375 | +0.3187 | 0.0055 | 0.9788 | 1.0000 | 2731.0 | 19967.3 / 21712.8 | 1.4503 |

> Δ FA = FA(fine-tuned) − FA(zero-shot): đóng góp thuần của QLoRA cho kiến trúc đó.
> Các cột CER / F1 / parse / VRAM / latency lấy từ dòng fine-tuned (nếu có).

## Baseline OCR truyền thống

Không dùng `train.jsonl` ở bất kỳ khâu nào ⇒ **không có cột Δ FA**. Cùng tập test, cùng schema, cùng `metrics.evaluate`, cùng tiền xử lý ảnh 1024px như các VLM.

| Baseline | Detector | Recognizer | FA | CER ↓ | micro-F1 | Trường điền được | Dòng OCR/ảnh | Latency p50/p95 (ms) | Ảnh 1024px |
|---|---|---|---|---|---|---|---|---|---|
| PP-OCR det + VietOCR rec (vgg_transformer) | ppocr_db | vietocr | 0.5147 | 0.5644 | 0.6470 | 0.7199 | 16.2 | 7899.1 / 9721.2 | có |
| PaddleOCR PP-OCR (det+rec, lang=vi) | ppocr_db | ppocr_crnn | 0.4028 | 0.5723 | 0.3767 | 0.7269 | 17.4 | 23376.8 / 33348.8 | có |

## Xếp hạng chung (mọi lần chạy)

| Model / Baseline | Chế độ | FA | CER ↓ | micro-F1 | Latency p50/p95 (ms) |
|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | fine_tuned | 0.9452 | 0.0040 | 0.9833 | 17174.5 / 18736.6 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | fine_tuned | 0.9437 | 0.0045 | 0.9823 | 19852.7 / 21365.3 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | fine_tuned | 0.9375 | 0.0055 | 0.9788 | 19967.3 / 21712.8 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | zero_shot | 0.6188 | 0.1660 | 0.7780 | 10275.8 / 11285.7 |
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | zero_shot | 0.6111 | 0.7765 | 0.6673 | 10337.7 / 11772.4 |
| PP-OCR det + VietOCR rec (vgg_transformer) | rule_based | 0.5147 | 0.5644 | 0.6470 | 7899.1 / 9721.2 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | zero_shot | 0.4753 | 0.3042 | 0.5775 | 10265.8 / 11437.7 |
| PaddleOCR PP-OCR (det+rec, lang=vi) | rule_based | 0.4028 | 0.5723 | 0.3767 | 23376.8 / 33348.8 |

> `rule_based` = baseline OCR, **chưa từng thấy dữ liệu train**. Đặt cạnh `fine_tuned` để thấy khoảng cách, không phải để kết luận kiến trúc nào hơn.

## FA theo từng trường

Mỗi model lấy bản fine-tuned; baseline OCR lấy bản `rule_based`.

### Mặt trước

| Trường | internvl | llama_vision | paddle_vietocr (rule_based) | paddleocr (rule_based) | qwen |
|---|---|---|---|---|---|
| `so_cccd` | 0.9931 | 0.9861 | 0.8958 | 0.9444 | 0.9861 |
| `ho_va_ten` | 0.8889 | 0.9167 | 0.2083 | 0.0139 | 0.8889 |
| `ngay_sinh` | 1.0000 | 0.9861 | 0.5486 | 0.5764 | 0.9653 |
| `gioi_tinh` | 1.0000 | 1.0000 | 0.6597 | 0.4861 | 1.0000 |
| `quoc_tich` | 0.9931 | 0.9931 | 0.4792 | 0.0000 | 0.9931 |
| `que_quan` | 0.8958 | 0.8889 | 0.2917 | 0.1389 | 0.8819 |
| `noi_thuong_tru` | 0.7639 | 0.7708 | 0.1597 | 0.1319 | 0.7778 |
| `co_gia_tri_den` | 0.9722 | 0.9514 | 0.3889 | 0.3333 | 0.9444 |
| `mat_the` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### Mặt sau

| Trường | internvl | llama_vision | paddle_vietocr (rule_based) | paddleocr (rule_based) | qwen |
|---|---|---|---|---|---|
| `mat_the` | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

## Trước khi kết luận

Tập test ~10% dữ liệu ⇒ chênh lệch vài % FA có thể là nhiễu. Cần ≥2 seed, bootstrap CI 95% cho FA, và McNemar test trên exact-match từng trường khi so từng cặp model (VLM_COMPARISON_PLAN.md mục 9).
