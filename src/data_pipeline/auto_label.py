"""
auto_label.py
=============
Bước 1 (Human-in-the-loop): dùng Qwen2.5-VL-7B sinh nhãn DỰ THẢO (draft) cho ảnh CCCD.

Nâng cấp so với bản gốc `label_cccd.py`:
  1. Prompt ĐỘNG theo mặt thẻ: tên file chứa "front" → prompt mặt trước,
     chứa "back" → prompt mặt sau (xem `cccd_schema.infer_side_from_filename`).
     Nhờ vậy model không bịa các trường chỉ có ở mặt còn lại.
  2. Try-except 2 lớp: lỗi 1 ảnh KHÔNG làm dừng cả batch; checkpoint vẫn lưu.
  3. Output là draft để con người duyệt lại bằng `label_tool.py`.

Format JSONL output (chuẩn qwen-vl-finetune), kèm khối `_meta` để label_tool đọc:
  {
    "image": "data/raw/xxx_front.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\\n<prompt theo mặt>"},
      {"from": "gpt",   "value": "<JSON string>"}
    ],
    "_meta": {"side": "truoc", "parse_ok": true, "raw_output": "...", "reviewed": false}
  }

Cách dùng (CLI):
  python -m src.data_pipeline.auto_label --input_dir data/raw --result_dir data/draft
  python -m src.data_pipeline.auto_label --input_dir data/raw --result_dir data/draft --reset
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import torch
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


# ── Checkpoint helpers ──────────────────────────────────────────────────────
def checkpoint_path(result_dir: Path, split_name: str) -> Path:
    """Trả về path file checkpoint cho 1 folder/split."""
    return result_dir / f".checkpoint_{split_name}.json"


def load_checkpoint(ckpt_path: Path) -> Set[str]:
    """Đọc checkpoint → set tên ảnh đã xử lý xong (rỗng nếu chưa có)."""
    if not ckpt_path.exists():
        return set()
    try:
        with open(ckpt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        done = set(data.get("done", []))
        logger.info("  [checkpoint] đã có %d ảnh hoàn thành từ lần trước", len(done))
        return done
    except Exception as exc:  # noqa: BLE001 - checkpoint hỏng thì làm lại từ đầu
        logger.warning("  [checkpoint] đọc lỗi (%s), bắt đầu lại từ đầu", exc)
        return set()


def save_checkpoint(ckpt_path: Path, done_names: Set[str]) -> None:
    """Ghi checkpoint ngay sau mỗi ảnh hoàn thành (atomic-ish)."""
    try:
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump({"done": sorted(done_names)}, f, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("  [checkpoint] ghi lỗi: %s", exc)


def clear_checkpoint(ckpt_path: Path) -> None:
    """Xóa checkpoint khi đã xử lý toàn bộ folder."""
    if ckpt_path.exists():
        ckpt_path.unlink()
        logger.info("  [checkpoint] đã xóa checkpoint (folder hoàn tất)")


# ── Load model ──────────────────────────────────────────────────────────────
def load_model(model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct") -> Tuple[object, object]:
    """
    Tải Qwen2.5-VL (mặc định cho gán nhãn) — hoặc Qwen2-VL/Qwen3-VL nếu đổi model_name.

    Có thể truyền PATH LOCAL (đã tải từ HuggingFace về) thay cho HF ID.

    Lưu ý: auto_label chạy ở chế độ INFERENCE nên load full precision/bf16 là đủ;
    không cần 4-bit (4-bit dành cho lúc fine-tune trên GPU yếu — xem lora_setup.py).

    Args:
        model_name: HuggingFace ID hoặc path local.

    Returns:
        (model, processor) đã sẵn sàng .generate().
    """
    logger.info("Loading: %s", model_name)
    from transformers import AutoProcessor  # import trễ để CLI --help nhẹ

    dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)

    if "Qwen3" in model_name:
        from transformers import Qwen3VLForConditionalGeneration as ModelCls
    elif "Qwen2.5" in model_name or "Qwen2_5" in model_name:
        from transformers import Qwen2_5_VLForConditionalGeneration as ModelCls
    else:
        from transformers import Qwen2VLForConditionalGeneration as ModelCls

    model = ModelCls.from_pretrained(
        model_name,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    logger.info("✓ Model loaded: %s", model_name)
    return model, processor


# ── Inference 1 ảnh ─────────────────────────────────────────────────────────
def infer_image(
    image_path: str,
    side: CardSide,
    model,
    processor,
    max_new_tokens: int = 512,
) -> str:
    """
    Chạy 1 ảnh qua Qwen-VL với prompt tương ứng mặt thẻ.

    Args:
        image_path: Đường dẫn ảnh.
        side: Mặt thẻ (quyết định prompt).
        model, processor: Từ `load_model`.
        max_new_tokens: Giới hạn token sinh ra.

    Returns:
        Chuỗi text model sinh ra (chưa parse JSON).
    """
    image = Image.open(image_path).convert("RGB")
    user_prompt = build_user_prompt(side)

    messages = [
        {"role": "system", "content": [{"type": "text", "text": SYSTEM_PROMPT}]},
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
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


# ── Parse JSON an toàn ──────────────────────────────────────────────────────
def parse_json_safe(text: str) -> Optional[dict]:
    """
    Cố parse JSON từ output model. Bóc ```json fences, fallback regex { ... }.

    Returns:
        dict nếu parse được, None nếu thất bại.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re

        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                return None
    return None


# ── Build record ────────────────────────────────────────────────────────────
def build_training_record(
    image_path: str, side: CardSide, gpt_answer: str, parse_ok: bool, raw: str
) -> dict:
    """Dựng record JSONL chuẩn fine-tuning + khối `_meta` cho label_tool."""
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
            "reviewed": False,  # label_tool sẽ set True sau khi người duyệt
        },
    }


# ── Label 1 folder ──────────────────────────────────────────────────────────
def label_folder(
    input_dir: Path,
    result_dir: Path,
    output_filename: str,
    model,
    processor,
    max_new_tokens: int = 512,
    reset: bool = False,
) -> int:
    """
    Gán nhãn draft toàn bộ ảnh trong `input_dir`, checkpoint sau MỖI ảnh.

    Args:
        input_dir: Folder ảnh nguồn.
        result_dir: Folder lưu JSONL + checkpoint.
        output_filename: Tên file JSONL output.
        model, processor: Từ load_model.
        max_new_tokens: Giới hạn sinh.
        reset: True → xóa checkpoint & output cũ, làm lại từ đầu.

    Returns:
        Tổng số record đã ghi trong lần chạy này.
    """
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
                raw = infer_image(str(img_path), side, model, processor, max_new_tokens)
                parsed = parse_json_safe(raw)

                if parsed is not None:
                    # Ép trường mat_the theo tên file (đáng tin hơn model đoán).
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
            except Exception as exc:  # noqa: BLE001 - 1 ảnh lỗi không dừng cả batch
                logger.error("  ERROR %s: %s", img_path.name, exc)
                errors += 1
            finally:
                # Luôn checkpoint (kể cả ảnh lỗi) để lần sau bỏ qua, không kẹt vòng lặp.
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


# ── Main ────────────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    """Định nghĩa & parse CLI args."""
    parser = argparse.ArgumentParser(
        description="CCCD Auto Labeler (draft) — Qwen2-VL, prompt động theo mặt thẻ",
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
    return parser.parse_args()


def main() -> None:
    """Entry point CLI."""
    args = parse_args()
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

    model, processor = load_model(args.model_name)
    label_folder(
        input_dir=input_dir,
        result_dir=result_dir,
        output_filename=f"{input_dir.name}_draft.jsonl",
        model=model,
        processor=processor,
        max_new_tokens=args.max_new_tokens,
        reset=args.reset,
    )


if __name__ == "__main__":
    main()
