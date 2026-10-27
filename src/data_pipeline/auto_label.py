"""Generate draft CCCD labels with Qwen2.5-VL for humans to review in `label_tool.py`."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Must be set before torch is imported to take effect.
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

import torch  # noqa: E402  (imported after the allocator setting above, on purpose)
from PIL import Image
from tqdm import tqdm

from src.utils.cccd_schema import (
    SYSTEM_PROMPT,
    CardSide,
    build_user_prompt,
    human_value,
    infer_side_from_filename,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("auto_label.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}


def checkpoint_path(result_dir: Path, split_name: str) -> Path:
    return result_dir / f".checkpoint_{split_name}.json"


def load_checkpoint(ckpt_path: Path) -> Set[str]:
    if not ckpt_path.exists():
        return set()
    try:
        with open(ckpt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        done = set(data.get("done", []))
        logger.info("  [checkpoint] đã có %d ảnh hoàn thành từ lần trước", len(done))
        return done
    except Exception as exc:
        logger.warning("  [checkpoint] đọc lỗi (%s), bắt đầu lại từ đầu", exc)
        return set()


def save_checkpoint(ckpt_path: Path, done_names: Set[str]) -> None:
    try:
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump({"done": sorted(done_names)}, f, ensure_ascii=False)
    except Exception as exc:
        logger.warning("  [checkpoint] ghi lỗi: %s", exc)


def clear_checkpoint(ckpt_path: Path) -> None:
    if ckpt_path.exists():
        ckpt_path.unlink()
        logger.info("  [checkpoint] đã xóa checkpoint (folder hoàn tất)")


# max_pixels must be a multiple of 28*28 (Qwen-VL requirement).
DEFAULT_MAX_PIXELS: int = 2560 * 28 * 28      # ~2.0 MP, keeps small handwriting legible
DEFAULT_MIN_PIXELS: int = 256 * 28 * 28
DEFAULT_IMG_LONG_SIDE: int = 2048


def load_model(
    model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct",
    min_pixels: int = DEFAULT_MIN_PIXELS,
    max_pixels: int = DEFAULT_MAX_PIXELS,
    load_in_4bit: bool = False,
) -> Tuple[object, object]:
    """Load Qwen2.5-VL; `load_in_4bit` is for running the 7B on a 16GB T4."""
    logger.info(
        "Loading: %s (min_pixels=%d, max_pixels=%d, 4bit=%s)",
        model_name, min_pixels, max_pixels, load_in_4bit,
    )
    from transformers import AutoProcessor

    # float16 overflows Qwen2.5-VL's vision tower and it emits "!" until the token limit.
    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    processor = AutoProcessor.from_pretrained(
        model_name, trust_remote_code=True, min_pixels=min_pixels, max_pixels=max_pixels
    )

    if "Qwen3" in model_name:
        from transformers import Qwen3VLForConditionalGeneration as ModelCls
    elif "Qwen2.5" in model_name or "Qwen2_5" in model_name:
        from transformers import Qwen2_5_VLForConditionalGeneration as ModelCls
    else:
        from transformers import Qwen2VLForConditionalGeneration as ModelCls

    model_kwargs = dict(torch_dtype=dtype, device_map="auto", trust_remote_code=True)

    if load_in_4bit:
        from transformers import BitsAndBytesConfig

        model_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_use_double_quant=True,
        )
        logger.info("  [4-bit] NF4 + double-quant (compute=%s) để vừa VRAM T4", dtype)

    model = ModelCls.from_pretrained(model_name, **model_kwargs)
    model.eval()
    logger.info("✓ Model loaded: %s", model_name)
    return model, processor


def infer_image(
    image_path: str,
    side: CardSide,
    model,
    processor,
    max_new_tokens: int = 512,
    img_long_side: int = DEFAULT_IMG_LONG_SIDE,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> str:
    """Run one image through Qwen-VL with the prompt for that card side."""
    image = Image.open(image_path).convert("RGB")
    image.thumbnail((img_long_side, img_long_side))

    user_prompt = build_user_prompt(side)

    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "image": image,
                    "max_pixels": max_pixels,
                },
                {"type": "text", "text": user_prompt},
            ],
        },
    ]

    text_input = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(
        text=[text_input], images=[image], return_tensors="pt", padding=True
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

    input_len = inputs["input_ids"].shape[1]
    generated = output_ids[:, input_len:]
    return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()


def parse_json_safe(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()

    parsed_dict = None
    try:
        parsed_dict = json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                parsed_dict = json.loads(m.group())
            except json.JSONDecodeError:
                return None

    if parsed_dict is None:
        return None

    # A date here means the model confused ngay_cap with dac_diem_nhan_dang.
    ddnd = parsed_dict.get("dac_diem_nhan_dang")
    if isinstance(ddnd, str) and "/" in ddnd:
        parsed_dict["dac_diem_nhan_dang"] = None

    # Canonical form, which also fixes the common OCR slip "TRẠT TỰ".
    noi_cap = parsed_dict.get("noi_cap")
    if isinstance(noi_cap, str) and "QUẢN LÝ HÀNH CHÍNH" in noi_cap.upper():
         parsed_dict["noi_cap"] = "CỤC TRƯỞNG CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI"

    return parsed_dict


def build_training_record(
    image_path: str, side: CardSide, gpt_answer: str, parse_ok: bool, raw: str
) -> dict:
    return {
        "image": str(image_path).replace("\\", "/"),
        "conversations": [
            {"from": "human", "value": human_value(side)},
            {"from": "gpt", "value": gpt_answer},
        ],
        "_meta": {
            "side": side.value,
            "parse_ok": parse_ok,
            "raw_output": raw,
            "reviewed": False,
        },
    }


def label_folder(
    input_dir: Path,
    result_dir: Path,
    output_filename: str,
    model,
    processor,
    max_new_tokens: int = 512,
    reset: bool = False,
    img_long_side: int = DEFAULT_IMG_LONG_SIDE,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> int:
    split_name = input_dir.name
    ckpt_path = checkpoint_path(result_dir, split_name)
    output_path = result_dir / output_filename
    result_dir.mkdir(parents=True, exist_ok=True)

    if reset:
        for p in (ckpt_path, output_path):
            if p.exists():
                p.unlink()
                logger.info("[%s] Reset: đã xóa %s", split_name, p.name)

    done_names = load_checkpoint(ckpt_path)

    all_images: List[Path] = sorted(
        p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_EXTENSIONS
    )
    logger.info("[%s] Tổng ảnh: %d", split_name, len(all_images))
    if not all_images:
        logger.warning("[%s] Không có ảnh!", split_name)
        return 0

    todo = [p for p in all_images if p.name not in done_names]
    if len(all_images) - len(todo) > 0:
        logger.info("[%s] ⏭ Bỏ qua %d ảnh (đã checkpoint)", split_name, len(all_images) - len(todo))
    logger.info("[%s] Cần label: %d ảnh", split_name, len(todo))
    if not todo:
        logger.info("[%s] Tất cả đã hoàn thành!", split_name)
        return 0

    write_mode = "a" if output_path.exists() else "w"
    success = errors = parse_fail = 0

    with open(output_path, write_mode, encoding="utf-8") as f_out:
        for img_path in tqdm(todo, desc=f"  [{split_name}]", unit="img"):
            try:
                side = infer_side_from_filename(img_path.name)
                raw = infer_image(
                    str(img_path), side, model, processor,
                    max_new_tokens, img_long_side, max_pixels,
                )
                parsed = parse_json_safe(raw)

                if parsed is not None:
                    if side != CardSide.UNKNOWN:
                        parsed["mat_the"] = side.value
                    gpt_answer = json.dumps(parsed, ensure_ascii=False)
                    success += 1
                else:
                    gpt_answer = raw
                    parse_fail += 1
                    logger.warning("  parse_fail: %s | %s...", img_path.name, raw[:60])

                record = build_training_record(
                    str(img_path), side, gpt_answer, parsed is not None, raw
                )
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()

            except KeyboardInterrupt:
                logger.warning(
                    "\n[%s] Bị ngắt! Đã lưu checkpoint (%d ảnh)", split_name, len(done_names)
                )
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("  ERROR %s: %s", img_path.name, exc)
                errors += 1
                # Keep one OOM from fragmenting memory for the next image.
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            finally:
                done_names.add(img_path.name)
                save_checkpoint(ckpt_path, done_names)

    if len(done_names) >= len(all_images):
        clear_checkpoint(ckpt_path)

    total = success + parse_fail
    logger.info(
        "[%s] DONE → %s | ✓%d | parse_fail:%d | error:%d | tổng:%d",
        split_name, output_filename, success, parse_fail, errors, total,
    )
    return total


def _is_null(v) -> bool:
    return v is None or (isinstance(v, str) and v.strip().lower() in ("", "null", "none"))


_KHONGCO_TOKENS = ("không có", "khong co", "ko có", "ko co")


def _is_missing(v) -> bool:
    """Null, empty, or the model writing "không có..." all count as missing."""
    if _is_null(v):
        return True
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("không", "khong", "na", "n/a"):
            return True
        if any(tok in t for tok in _KHONGCO_TOKENS):
            return True
    return False


def retry_null_records(
    jsonl_path: Path,
    model,
    processor,
    retry_fields: List[str],
    max_new_tokens: int = 512,
    img_long_side: int = DEFAULT_IMG_LONG_SIDE,
    max_pixels: int = DEFAULT_MAX_PIXELS,
) -> int:
    """Re-read only records missing `retry_fields`; overwrite a field only if a real value comes back."""
    jsonl_path = Path(jsonl_path)
    if not jsonl_path.exists():
        logger.error("[retry] Không thấy file: %s", jsonl_path)
        return 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]

    targets = []
    for idx, rec in enumerate(records):
        try:
            ans = json.loads(rec["conversations"][1]["value"])
        except Exception:
            continue
        if any(_is_missing(ans.get(fld)) for fld in retry_fields):
            targets.append(idx)

    logger.info("[retry] Tổng record: %d | cần đọc lại (null + 'không có'): %d", len(records), len(targets))
    if not targets:
        logger.info("[retry] Không có ca null nào để xử lý.")
        return 0

    backup = jsonl_path.with_suffix(jsonl_path.suffix + ".bak")
    backup.write_text(jsonl_path.read_text(encoding="utf-8"), encoding="utf-8")
    logger.info("[retry] Đã sao lưu bản gốc → %s", backup.name)

    fixed = 0
    for idx in tqdm(targets, desc="  [retry-null]", unit="img"):
        rec = records[idx]
        img = rec["image"]
        try:
            side_val = rec.get("_meta", {}).get("side")
            side = CardSide(side_val) if side_val in (s.value for s in CardSide) \
                else infer_side_from_filename(img)
            raw = infer_image(img, side, model, processor, max_new_tokens, img_long_side, max_pixels)
            parsed = parse_json_safe(raw)
            if parsed is None:
                continue

            old = json.loads(rec["conversations"][1]["value"])
            changed = False
            for fld in retry_fields:
                if _is_missing(old.get(fld)) and not _is_missing(parsed.get(fld)):
                    old[fld] = parsed[fld]
                    changed = True
            if changed:
                rec["conversations"][1]["value"] = json.dumps(old, ensure_ascii=False)
                rec["_meta"]["retry_raw_output"] = raw
                rec["_meta"]["retry_done"] = True
                fixed += 1
        except Exception as exc:  # noqa: BLE001
            logger.error("  [retry] ERROR %s: %s", img, exc)

    with open(jsonl_path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    logger.info("[retry] DONE → đã đọc bổ sung được %d/%d ca null", fixed, len(targets))
    return fixed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CCCD Auto Labeler (draft) — Qwen2.5-VL-7B-Instruct, prompt động theo mặt thẻ",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--input_dir", default="data/raw", help="Folder ảnh nguồn")
    parser.add_argument("--result_dir", default="data/draft", help="Folder JSONL + checkpoint")
    parser.add_argument(
        "--model_name", default="Qwen/Qwen2.5-VL-7B-Instruct",
        help="HF ID hoặc path local đã tải sẵn (default: Qwen/Qwen2.5-VL-7B-Instruct)",
    )
    parser.add_argument("--max_new_tokens", type=int, default=512)
    parser.add_argument("--reset", action="store_true", help="Xóa checkpoint+output cũ, làm lại")

    parser.add_argument(
        "--img_long_side", type=int, default=DEFAULT_IMG_LONG_SIDE,
        help=f"Cạnh dài tối đa khi thumbnail (default {DEFAULT_IMG_LONG_SIDE})",
    )
    parser.add_argument(
        "--max_pixels", type=int, default=DEFAULT_MAX_PIXELS,
        help=f"Trần pixel cho image processor (default {DEFAULT_MAX_PIXELS} ≈ 2MP)",
    )

    parser.add_argument(
        "--retry_jsonl", default=None,
        help="Nếu đặt: BỎ QUA bước label folder, chỉ đọc LẠI các ca null trong file "
             "JSONL này bằng --model_name (thường là Qwen2.5-VL-7B để tiết kiệm RAM).",
    )
    parser.add_argument(
        "--retry_fields", default="dac_diem_nhan_dang",
        help="Các trường null cần retry, cách nhau dấu phẩy (vd: dac_diem_nhan_dang,ngay_cap)",
    )
    parser.add_argument(
        "--load_4bit", action="store_true",
        help="Nén model NF4 4-bit (bitsandbytes). Cần khi chạy 7B trên T4 16GB để "
             "tránh CUDA out of memory (weights 7B bf16 ~12GB không vừa).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.retry_jsonl:
        retry_fields = [f.strip() for f in args.retry_fields.split(",") if f.strip()]
        logger.info("=" * 60)
        logger.info("RETRY-NULL mode")
        logger.info("Model     : %s", args.model_name)
        logger.info("File      : %s", args.retry_jsonl)
        logger.info("Fields    : %s", retry_fields)
        logger.info("=" * 60)
        model, processor = load_model(
            args.model_name, max_pixels=args.max_pixels, load_in_4bit=args.load_4bit
        )
        retry_null_records(
            jsonl_path=Path(args.retry_jsonl),
            model=model,
            processor=processor,
            retry_fields=retry_fields,
            max_new_tokens=args.max_new_tokens,
            img_long_side=args.img_long_side,
            max_pixels=args.max_pixels,
        )
        return

    input_dir = Path(args.input_dir)
    if not input_dir.exists():
        logger.error("Folder không tồn tại: %s", input_dir)
        return

    result_dir = Path(args.result_dir)
    logger.info("=" * 60)
    logger.info("Model     : %s", args.model_name)
    logger.info("Input     : %s", input_dir)
    logger.info("Output    : %s/%s_draft.jsonl", result_dir, input_dir.name)
    logger.info("=" * 60)

    model, processor = load_model(
        args.model_name, max_pixels=args.max_pixels, load_in_4bit=args.load_4bit
    )
    label_folder(
        input_dir=input_dir,
        result_dir=result_dir,
        output_filename=f"{input_dir.name}_draft.jsonl",
        model=model,
        processor=processor,
        max_new_tokens=args.max_new_tokens,
        reset=args.reset,
        img_long_side=args.img_long_side,
        max_pixels=args.max_pixels,
    )


if __name__ == "__main__":
    main()
