# Bang ket qua so sanh VLM - CCCD mat Front

Moi dong dung cung tap test, cung prompt/schema, cung `metrics.evaluate`, cung greedy decoding. CI 95% bootstrap resample theo anh, 2000 lan, seed=42.

| Model | FA zero-shot | FA fine-tuned (CI 95%) | Delta FA | CER | micro-F1 | JSON parse | VRAM (GB) | p50/p95 (ms) |
|---|---|---|---|---|---|---|---|---|
| /content/drive/MyDrive/cccd_project/Data/models/InternVL3_5-2B-HF | 61.11% | 94.52% [93.06%, 95.83%] | +33.41% | 0.0040 | 98.33% | 100.0% | 2.6 | 17174.5 / 18736.6 |
| /content/drive/MyDrive/cccd_project/Data/models/Llama-3.2-11B-Vision-Instruct | 47.53% | 94.37% [92.90%, 95.91%] | +46.84% | 0.0045 | 98.23% | 100.0% | 7.8 | 19852.7 / 21365.3 |
| /content/drive/MyDrive/cccd_project/Data/models/Qwen2.5-VL-3B-Instruct | 61.88% | 93.75% [92.13%, 95.22%] | +31.87% | 0.0055 | 97.88% | 100.0% | 2.7 | 19967.3 / 21712.8 |

> Delta FA = FA(fine-tuned) - FA(zero-shot): dong gop thuan cua QLoRA.
> Khoang tin cay chong lan => khong ket luan model nao tot hon.

## Baseline OCR truyen thong (Stage 3d)

KHONG co cot Delta FA: baseline khong nhin thay `train.jsonl` o bat ky khau nao nen khong co cap zero-shot/fine-tuned de tru. Hai pipeline dung CHUNG detector, nen chenh lech giua chung co lap phan dong gop cua recognizer chuyen tieng Viet.

| Pipeline | FA (CI 95%) | CER | micro-F1 | Truong dien duoc | Dong OCR/anh | Engine |
|---|---|---|---|---|---|---|
| paddle_vietocr | 51.47% [47.99%, 54.78%] | 0.5644 | 64.70% | 72.0% | 16.2 | - |
| paddleocr | 40.28% [37.89%, 42.59%] | 0.5723 | 37.67% | 72.7% | 17.4 | - |

> "Truong dien duoc" = `field_fill_rate`: ty le truong parser dien ra MOT CAI GI DO, bat ke dung sai. Doc kem FA de tach "OCR khong doc ra" khoi "doc ra nhung sai".
> Dong nao co nhan _(canonicalize)_ hoac _(full-res)_ la ABLATION, khong phai so headline.
