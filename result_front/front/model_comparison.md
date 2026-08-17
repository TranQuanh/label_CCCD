# So sánh VLM fine-tune — trích xuất CCCD

Sinh tự động bởi `scripts/compare_models.py`. Mọi dòng dùng **cùng tập test, cùng prompt/schema, cùng `metrics.evaluate`, cùng greedy decoding**.

## Bảng chính

| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |
|---|---|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 2.3 | 0.0448 | 0.9452 | +0.9004 | 0.0040 | 0.9833 | 1.0000 | 2612.3 | 17174.5 / 18736.6 | 1.1592 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 10.6 | 0.4792 | 0.9437 | +0.4645 | 0.0045 | 0.9823 | 1.0000 | 7970.4 | 19852.7 / 21365.3 | 0.8809 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 3.7 | 0.0594 | 0.9375 | +0.8781 | 0.0055 | 0.9788 | 1.0000 | 2731.0 | 19967.3 / 21712.8 | 1.4503 |

> Δ FA = FA(fine-tuned) − FA(zero-shot): đóng góp thuần của QLoRA cho kiến trúc đó.
> Các cột CER / F1 / parse / VRAM / latency lấy từ dòng fine-tuned (nếu có).

## FA theo từng trường (fine-tuned)

### Mặt trước

| Trường | internvl | llama_vision | qwen |
|---|---|---|---|
| `so_cccd` | 0.9931 | 0.9861 | 0.9861 |
| `ho_va_ten` | 0.8889 | 0.9167 | 0.8889 |
| `ngay_sinh` | 1.0000 | 0.9861 | 0.9653 |
| `gioi_tinh` | 1.0000 | 1.0000 | 1.0000 |
| `quoc_tich` | 0.9931 | 0.9931 | 0.9931 |
| `que_quan` | 0.8958 | 0.8889 | 0.8819 |
| `noi_thuong_tru` | 0.7639 | 0.7708 | 0.7778 |
| `co_gia_tri_den` | 0.9722 | 0.9514 | 0.9444 |
| `mat_the` | 1.0000 | 1.0000 | 1.0000 |

### Mặt sau

| Trường | internvl | llama_vision | qwen |
|---|---|---|---|
| `mat_the` | 1.0000 | 1.0000 | 1.0000 |

## Trước khi kết luận

Tập test ~10% dữ liệu ⇒ chênh lệch vài % FA có thể là nhiễu. Cần ≥2 seed, bootstrap CI 95% cho FA, và McNemar test trên exact-match từng trường khi so từng cặp model (VLM_COMPARISON_PLAN.md mục 9).
