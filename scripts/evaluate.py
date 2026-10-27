"""Score a VLM on the test set (FA / CER / F1), fine-tuned or zero-shot."""

from __future__ import annotations

import argparse
import json
import logging
import statistics
import time
from pathlib import Path
from typing import Dict, List, Optional

import torch
from PIL import Image
from tqdm import tqdm

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.models.lora_setup import build_bnb_config
from src.models.vlm_registry import (
    SHARED_IMAGE_MAX_SIDE,
    VLMSpec,
    check_available,
    images_arg,
    load_processor,
    preprocess_image,
    resolve,
)
from src.models.vlm_registry import build_gen_kwargs as _build_gen_kwargs
from src.utils.cccd_schema import SYSTEM_PROMPT
from src.utils.metrics import evaluate, safe_parse

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_test(test_jsonl: str) -> List[dict]:
    records: List[dict] = []
    with open(test_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def read_run_meta(adapter_dir: Optional[str]) -> dict:
    """Read the `vlm_meta.json` train.py writes next to the adapter."""
    if not adapter_dir:
        return {}
    path = Path(adapter_dir) / "vlm_meta.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Đánh giá model CCCD trên tập test")
    p.add_argument("--test_jsonl", required=True)
    p.add_argument("--base_model", default=None,
                   help="Bỏ trống = lấy từ vlm_meta.json của adapter, fallback Qwen2.5-VL-3B")
    p.add_argument("--adapter_dir", default=None,
                   help="Bắt buộc trừ khi --zero_shot")
    p.add_argument("--model_key", default=None,
                   help="Key trong vlm_registry; bỏ trống = suy từ base_model")
    p.add_argument("--zero_shot", action="store_true",
                   help="Chạy base model thuần, không gắn LoRA adapter")
    p.add_argument("--image_root", default=".")
    p.add_argument("--report_path", default="result/eval_report.json")
    p.add_argument("--max_new_tokens", type=int, default=512)
    p.add_argument(
        "--predictions_path",
        default=None,
        help="Nơi ghi dự đoán từng ảnh (JSONL). Bỏ trống = <report_path>_preds.jsonl",
    )
    p.add_argument(
        "--no_save_predictions",
        action="store_true",
        help="Không ghi file dự đoán. Mặc định LUÔN ghi vì bootstrap CI và McNemar "
             "test cần kết quả từng ảnh, mà report chỉ có số tổng hợp.",
    )
    args = p.parse_args()
    if not args.zero_shot and not args.adapter_dir:
        p.error("cần --adapter_dir, hoặc dùng --zero_shot để chạy base model thuần")
    return args


def load_eval_model(base_model: str, adapter_dir: Optional[str], spec: VLMSpec, zero_shot: bool):
    """Load the 4-bit base, plus the LoRA adapter unless running zero-shot."""
    from transformers import AutoModelForImageTextToText
    from peft import PeftModel

    compute_dtype = torch.bfloat16
    base = AutoModelForImageTextToText.from_pretrained(
        base_model,
        quantization_config=build_bnb_config(compute_dtype),
        device_map="auto",
        torch_dtype=compute_dtype,
        trust_remote_code=True,
    )

    if zero_shot:
        logger.info("Chế độ ZERO-SHOT: không gắn adapter")
        processor = load_processor(base_model, spec)
        base.eval()
        return base, processor

    logger.info("Gắn LoRA adapter từ %s", adapter_dir)
    model = PeftModel.from_pretrained(base, adapter_dir)
    model.eval()
    # Re-apply spec.processor_kwargs so the image-token budget matches training.
    processor = load_processor(adapter_dir, spec)
    return model, processor


# Import from `src.models.vlm_registry`, not from here: `scripts/` is not a package.
build_gen_kwargs = _build_gen_kwargs


def main() -> None:
    args = parse_args()

    meta = read_run_meta(args.adapter_dir)
    base_model = args.base_model or meta.get("model_id") or "Qwen/Qwen2.5-VL-3B-Instruct"
    if args.base_model and meta.get("model_id") and args.base_model != meta["model_id"]:
        logger.warning(
            "⚠ --base_model='%s' KHÁC base lúc train ('%s'). Gắn adapter lên base khác "
            "sẽ cho kết quả vô nghĩa. Đang dùng '%s' theo yêu cầu.",
            args.base_model, meta["model_id"], args.base_model,
        )
    spec = resolve(args.model_key or base_model)
    ok, reason = check_available(spec)
    if not ok:
        raise RuntimeError(f"Không chạy được {base_model}: {reason}")

    mode = "zero_shot" if args.zero_shot else "fine_tuned"
    logger.info("🔄 Đang tải Model và Processor (4-bit, %s, %s)...", spec.key, mode)
    model, processor = load_eval_model(base_model, args.adapter_dir, spec, args.zero_shot)

    records = load_test(args.test_jsonl)
    image_root = Path(args.image_root)
    preds: List[dict] = []
    golds: List[dict] = []
    # Raw strings are kept so a parser fix can be rescored on CPU (scripts/rescore.py).
    raws: List[str] = []
    latencies_ms: List[float] = []
    # Generated-token count per image: latency alone cannot say whether a run is slow
    # because it writes more tokens or because each step costs more.
    n_new_tokens: List[int] = []
    n_parse_ok = 0
    n_errors = 0

    gen_kwargs = build_gen_kwargs(args.max_new_tokens)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    logger.info("🚀 Bắt đầu chấm điểm trên tập Test...")
    for rec in tqdm(records, desc="Đánh giá", unit="ảnh"):
        gold = safe_parse(rec["conversations"][1]["value"])
        golds.append(gold)

        img_path = image_root / rec["image"]
        if not img_path.exists():
            img_path = Path(rec["image"])

        try:
            image = Image.open(img_path).convert("RGB")
            # Same resize as training, or the image-token count drifts.
            preprocess_image(image, spec)
            human_text = rec["conversations"][0]["value"].replace("<image>", "").strip()

            messages = [
                {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": human_text},
                    ],
                }
            ]

            text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = processor(
                text=[text], images=images_arg([image], spec), return_tensors="pt"
            ).to(model.device)

            if torch.cuda.is_available():
                torch.cuda.synchronize()
            t0 = time.perf_counter()
            with torch.no_grad():
                generated_ids = model.generate(**inputs, **gen_kwargs)
            if torch.cuda.is_available():
                torch.cuda.synchronize()
            latencies_ms.append((time.perf_counter() - t0) * 1000)

            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            # Counted before decoding: `skip_special_tokens` drops EOS from the text.
            n_tok = int(generated_ids_trimmed[0].shape[0])
            output_text = processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]

            parsed = safe_parse(output_text)
            if parsed:
                n_parse_ok += 1
            preds.append(parsed)
            # Appended together at the very end of the try: an exception anywhere above
            # must leave every list the same length, handled once in `except`.
            raws.append(output_text)
            n_new_tokens.append(n_tok)

        except Exception as exc:
            logger.error("❌ Lỗi khi xử lý ảnh %s: %s", rec["image"], exc)
            preds.append({})
            # Must append in lockstep with preds or the lists drift apart.
            raws.append(f"<EXCEPTION> {exc}")
            n_new_tokens.append(0)
            n_errors += 1

    # Per-image predictions are required by the bootstrap CI and McNemar test.
    if not args.no_save_predictions:
        pred_path = (
            Path(args.predictions_path)
            if args.predictions_path
            else Path(args.report_path).with_suffix("").with_name(
                Path(args.report_path).stem + "_preds.jsonl"
            )
        )
        pred_path.parent.mkdir(parents=True, exist_ok=True)
        with open(pred_path, "w", encoding="utf-8") as f:
            for rec, pred, gold, raw, n_tok in zip(records, preds, golds, raws, n_new_tokens):
                f.write(json.dumps(
                    {"image": rec["image"], "pred": pred, "gold": gold, "raw": raw,
                     "n_new_tokens": n_tok},
                    ensure_ascii=False,
                ) + "\n")
        logger.info("💾 Đã ghi %d dự đoán (kèm output thô) → %s", len(preds), pred_path)

    result = evaluate(preds, golds)
    report = result.as_dict()

    report["run"] = {
        "model_key": spec.key,
        "model_id": base_model,
        "family": spec.family,
        "params_b": spec.params_b,
        "mode": mode,
        "adapter_dir": args.adapter_dir,
        "image_max_side": SHARED_IMAGE_MAX_SIDE,
        "max_new_tokens": args.max_new_tokens,
        "decoding": "greedy (do_sample=False, num_beams=1)",
        "trainable_params_pct": meta.get("trainable_params_pct"),
        "train_max_length": meta.get("max_length"),
        "train_epochs": meta.get("train", {}).get("epochs"),
    }
    report["json_parse_rate"] = round(n_parse_ok / len(records), 4) if records else 0.0
    report["n_errors"] = n_errors
    if latencies_ms:
        ordered = sorted(latencies_ms)
        report["latency_ms"] = {
            "p50": round(statistics.median(ordered), 1),
            "p95": round(ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))], 1),
            "mean": round(statistics.fmean(ordered), 1),
        }
    generated = [n for n in n_new_tokens if n > 0]
    if generated:
        ordered_tok = sorted(generated)
        p50_tok = statistics.median(ordered_tok)
        report["gen_tokens"] = {
            "p50": round(p50_tok, 1),
            "p95": ordered_tok[min(len(ordered_tok) - 1, int(0.95 * len(ordered_tok)))],
            "mean": round(statistics.fmean(ordered_tok), 1),
            "max": max(ordered_tok),
            "n_hit_cap": sum(1 for n in generated if n >= args.max_new_tokens),
        }
        # p50 latency per p50 token: separates "writes more" from "each step costs more".
        if latencies_ms and p50_tok:
            report["gen_tokens"]["ms_per_token_p50"] = round(
                statistics.median(latencies_ms) / p50_tok, 2
            )
    if torch.cuda.is_available():
        report["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(
        "FA=%.4f | CER=%.4f | F1=%.4f | parse_ok=%.1f%% | p50=%sms | "
        "token sinh p50=%s (%s ms/token)",
        report["field_accuracy"], report["cer"], report["f1"],
        100 * report["json_parse_rate"],
        report.get("latency_ms", {}).get("p50", "-"),
        report.get("gen_tokens", {}).get("p50", "-"),
        report.get("gen_tokens", {}).get("ms_per_token_p50", "-"),
    )
    logger.info("✅ Đã lưu báo cáo → %s", report_path)


if __name__ == "__main__":
    main()
