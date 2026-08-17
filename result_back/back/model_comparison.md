# So sánh VLM fine-tune — trích xuất CCCD

Sinh tự động bởi `scripts/compare_models.py`. Mọi dòng dùng **cùng tập test, cùng prompt/schema, cùng `metrics.evaluate`, cùng greedy decoding**.

## Bảng chính

| Model | Params (B) | FA zero-shot | FA fine-tuned | Δ FA | CER ↓ | micro-F1 | JSON parse | Peak VRAM (MB) | Latency p50/p95 (ms) | Trainable % |
|---|---|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 2.3 | 0.0295 | 0.9767 | +0.9472 | 0.0119 | 0.9920 | 1.0000 | 2618.3 | 10965.3 / 11637.9 | 1.1592 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 10.6 | 0.4891 | 0.9736 | +0.4845 | 0.0139 | 0.9892 | 1.0000 | 7970.4 | 14384.2 / 15038.2 | 0.8809 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 3.7 | 0.3820 | 0.9783 | +0.5963 | 0.0103 | 0.9942 | 1.0000 | 2768.4 | 13230.1 / 14090.9 | 1.4503 |

> Δ FA = FA(fine-tuned) − FA(zero-shot): đóng góp thuần của QLoRA cho kiến trúc đó.
> Các cột CER / F1 / parse / VRAM / latency lấy từ dòng fine-tuned (nếu có).

## FA theo từng trường (fine-tuned)

### Mặt trước

| Trường | internvl | llama_vision | qwen |
|---|---|---|---|
| `mat_the` | 1.0000 | 1.0000 | 1.0000 |

### Mặt sau

| Trường | internvl | llama_vision | qwen |
|---|---|---|---|
| `dac_diem_nhan_dang` | 0.9068 | 0.9068 | 0.9130 |
| `ngay_cap` | 1.0000 | 0.9876 | 1.0000 |
| `noi_cap` | 1.0000 | 1.0000 | 1.0000 |
| `mat_the` | 1.0000 | 1.0000 | 1.0000 |

## Trước khi kết luận

Tập test ~10% dữ liệu ⇒ chênh lệch vài % FA có thể là nhiễu. Cần ≥2 seed, bootstrap CI 95% cho FA, và McNemar test trên exact-match từng trường khi so từng cặp model (VLM_COMPARISON_PLAN.md mục 9).
