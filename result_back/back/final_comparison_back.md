# Bang ket qua so sanh VLM - CCCD mat Back

Moi dong dung cung tap test, cung prompt/schema, cung `metrics.evaluate`, cung greedy decoding. CI 95% bootstrap resample theo anh, 2000 lan, seed=42.

| Model | FA zero-shot | FA fine-tuned (CI 95%) | Delta FA | CER | micro-F1 | JSON parse | VRAM (GB) | p50/p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 2.95% | 97.67% [96.58%, 98.76%] | +94.72% | 0.0119 | 99.20% | 100.0% | 2.6 | 10965.3 / 11637.9 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 48.91% | 97.36% [96.12%, 98.45%] | +48.45% | 0.0139 | 98.92% | 100.0% | 7.8 | 14384.2 / 15038.2 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 38.20% | 97.83% [96.74%, 98.91%] | +59.63% | 0.0103 | 99.42% | 100.0% | 2.7 | 13230.1 / 14090.9 |

> Delta FA = FA(fine-tuned) - FA(zero-shot): dong gop thuan cua QLoRA.
> Khoang tin cay chong lan => khong ket luan model nao tot hon.
