# Bang ket qua so sanh VLM - CCCD mat Back

Moi dong dung cung tap test, cung prompt/schema, cung `metrics.evaluate`, cung greedy decoding. CI 95% bootstrap resample theo anh, 2000 lan, seed=42.

| Model | FA zero-shot | FA fine-tuned (CI 95%) | Delta FA | CER | micro-F1 | JSON parse | VRAM (GB) | p50/p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 30.59% | 97.67% [96.58%, 98.76%] | +67.08% | 0.0119 | 99.20% | 100.0% | 2.6 | 10965.3 / 11637.9 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 47.36% | 97.20% [95.96%, 98.29%] | +49.84% | 0.0144 | 98.72% | 100.0% | 7.8 | 14549.8 / 15390.8 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 40.06% | 97.83% [96.74%, 98.91%] | +57.77% | 0.0103 | 99.42% | 100.0% | 2.7 | 13230.1 / 14090.9 |

> Delta FA = FA(fine-tuned) - FA(zero-shot): dong gop thuan cua QLoRA.
> Khoang tin cay chong lan => khong ket luan model nao tot hon.

## Baseline OCR truyen thong (Stage 3d)

KHONG co cot Delta FA: baseline khong nhin thay `train.jsonl` o bat ky khau nao nen khong co cap zero-shot/fine-tuned de tru. Hai pipeline dung CHUNG detector, nen chenh lech giua chung co lap phan dong gop cua recognizer chuyen tieng Viet.

| Pipeline | FA (CI 95%) | CER | micro-F1 | Truong dien duoc | Dong OCR/anh | Engine |
|---|---|---|---|---|---|---|
| paddle_vietocr | 57.14% [54.81%, 59.32%] | 0.1092 | 81.93% | 97.7% | 15.5 | - |
| paddleocr | 48.60% [47.67%, 49.38%] | 0.1677 | 42.15% | 96.7% | 15.2 | - |

> "Truong dien duoc" = `field_fill_rate`: ty le truong parser dien ra MOT CAI GI DO, bat ke dung sai. Doc kem FA de tach "OCR khong doc ra" khoi "doc ra nhung sai".
> Dong nao co nhan _(canonicalize)_ hoac _(full-res)_ la ABLATION, khong phai so headline.
