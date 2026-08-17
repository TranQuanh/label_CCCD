# Bang ket qua so sanh VLM - CCCD mat Front

Moi dong dung cung tap test, cung prompt/schema, cung `metrics.evaluate`, cung greedy decoding. CI 95% bootstrap resample theo anh, 2000 lan, seed=42.

| Model | FA zero-shot | FA fine-tuned (CI 95%) | Delta FA | CER | micro-F1 | JSON parse | VRAM (GB) | p50/p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 4.48% | 94.52% [93.06%, 95.83%] | +90.04% | 0.0040 | 98.33% | 100.0% | 2.6 | 17174.5 / 18736.6 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 47.92% | 94.37% [92.90%, 95.91%] | +46.45% | 0.0045 | 98.23% | 100.0% | 7.8 | 19852.7 / 21365.3 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 5.94% | 93.75% [92.13%, 95.22%] | +87.81% | 0.0055 | 97.88% | 100.0% | 2.7 | 19967.3 / 21712.8 |

> Delta FA = FA(fine-tuned) - FA(zero-shot): dong gop thuan cua QLoRA.
> Khoang tin cay chong lan => khong ket luan model nao tot hon.
