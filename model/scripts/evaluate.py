"""
evaluate.py
===========
Chạy model trên tập Test rồi tính FA / CER / F1, cho cả 2 chế độ:

  - fine-tuned : base 4-bit + LoRA adapter (mặc định).
  - zero-shot  : base 4-bit thuần, KHÔNG gắn adapter (`--zero_shot`).

Hai chế độ dùng y hệt prompt, tiền xử lý ảnh và tham số sinh → hiệu
(fine-tuned − zero-shot) chính là đóng góp thuần của QLoRA cho từng kiến trúc
(VLM_COMPARISON_PLAN.md mục 3.3).

Mọi thứ riêng theo họ model lấy từ [src/models/vlm_registry.py](../src/models/vlm_registry.py).
Đã cấu hình tự động load 4-bit Inference an toàn.
"""

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
    """Đọc test.jsonl → list record."""
    records: List[dict] = []
    with open(test_jsonl, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def read_run_meta(adapter_dir: Optional[str]) -> dict:
    """Đọc `vlm_meta.json` do train.py ghi cạnh adapter (rỗng nếu không có)."""
    if not adapter_dir:
        return {}
    path = Path(adapter_dir) / "vlm_meta.json"
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_args() -> argparse.Namespace:
    """Parse CLI args."""
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
    """
    Load base 4-bit (+ LoRA adapter nếu không phải zero-shot).

    Dựng lại ĐÚNG `BitsAndBytesConfig` như lúc train (dùng chung
    `lora_setup.build_bnb_config`) để zero-shot và fine-tuned cùng điều kiện
    lượng tử hoá.

    Returns:
        (model, processor) ở chế độ eval.
    """
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
    # Processor đã lưu kèm adapter; vẫn áp lại spec.processor_kwargs để chắc chắn
    # ngân sách token ảnh khớp lúc train.
    processor = load_processor(adapter_dir, spec)
    return model, processor


# `build_gen_kwargs` sống trong vlm_registry (cùng chỗ với `preprocess_image` và
# các biến kiểm soát khác) để eval/serve/notebook cùng gọi một nguồn.
# Alias cục bộ cho dễ đọc phần dưới. LƯU Ý: đừng import nó qua
# `from scripts.evaluate import ...` — thư mục `scripts/` không phải package và bị
# package cùng tên trong site-packages che mất. Import thẳng từ
# `src.models.vlm_registry`.
build_gen_kwargs = _build_gen_kwargs


def main() -> None:
    """Entry point: load model, infer test set, tính & lưu metric."""
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
    # Chuỗi thô model sinh ra, trước khi parse. BẮT BUỘC lưu: nếu chỉ giữ dict đã
    # parse thì mọi ảnh parse hỏng chỉ còn `{}` và output gốc MẤT VĨNH VIỄN — muốn
    # chấm lại sau khi sửa parser là phải chạy lại GPU cho cả tập test. Có `raw`
    # thì chấm lại chỉ tốn vài giây CPU (xem scripts/rescore.py).
    raws: List[str] = []
    latencies_ms: List[float] = []
    n_parse_ok = 0
    n_errors = 0

    gen_kwargs = build_gen_kwargs(args.max_new_tokens)
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()

    logger.info("🚀 Bắt đầu chấm điểm trên tập Test...")
    for rec in tqdm(records, desc="Đánh giá", unit="ảnh"):
        # Lấy đáp án chuẩn (Gold)
        gold = safe_parse(rec["conversations"][1]["value"])
        golds.append(gold)

        img_path = image_root / rec["image"]
        if not img_path.exists():
            img_path = Path(rec["image"])

        try:
            image = Image.open(img_path).convert("RGB")
            # Khớp tiền xử lý lúc train qua đúng một hàm dùng chung của registry —
            # lệch resize là số token ảnh lệch giữa train/inference.
            preprocess_image(image, spec)
            # Lấy câu hỏi từ JSONL
            human_text = rec["conversations"][0]["value"].replace("<image>", "").strip()

            # Khởi tạo form tin nhắn
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

            # Xử lý Prompt và Inference
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

            # Cắt bỏ phần Prompt, chỉ lấy câu trả lời
            generated_ids_trimmed = [
                out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            output_text = processor.batch_decode(
                generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]

            parsed = safe_parse(output_text)
            if parsed:
                n_parse_ok += 1
            preds.append(parsed)
            raws.append(output_text)

        except Exception as exc:
            logger.error("❌ Lỗi khi xử lý ảnh %s: %s", rec["image"], exc)
            preds.append({})  # Gặp lỗi thì tính là sai toàn bộ trường
            # Phải append cùng nhịp với preds, nếu không 3 list lệch nhau và
            # zip() ở dưới sẽ cắt cụt phần dự đoán ghi ra file.
            raws.append(f"<EXCEPTION> {exc}")
            n_errors += 1

    # Ghi dự đoán từng ảnh. BẮT BUỘC cho phần thống kê: bootstrap CI và McNemar
    # test cần kết quả ở mức từng ảnh/từng trường, mà report chỉ có số tổng hợp.
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
            for rec, pred, gold, raw in zip(records, preds, golds, raws):
                f.write(json.dumps(
                    {"image": rec["image"], "pred": pred, "gold": gold, "raw": raw},
                    ensure_ascii=False,
                ) + "\n")
        logger.info("💾 Đã ghi %d dự đoán (kèm output thô) → %s", len(preds), pred_path)

    # Tính toán kết quả
    result = evaluate(preds, golds)
    report = result.as_dict()

    # Thông tin phục vụ bảng so sánh giữa các model (mục 8 của plan doc).
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
    if torch.cuda.is_available():
        report["peak_vram_mb"] = round(torch.cuda.max_memory_allocated() / 1024**2, 1)

    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    logger.info(
        "FA=%.4f | CER=%.4f | F1=%.4f | parse_ok=%.1f%% | p50=%sms",
        report["field_accuracy"], report["cer"], report["f1"],
        100 * report["json_parse_rate"],
        report.get("latency_ms", {}).get("p50", "-"),
    )
    logger.info("✅ Đã lưu báo cáo → %s", report_path)


if __name__ == "__main__":
    main()
