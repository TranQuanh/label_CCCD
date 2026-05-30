"""
CCCD Auto Labeler - Qwen2.5-VL-7B (Local)
==========================================
Đọc ảnh CCCD → JSONL chuẩn format fine-tuning Qwen2.5-VL / Qwen3-VL.

Tính năng:
  - Checkpoint tự động: lưu tiến độ sau mỗi ảnh, chạy lại tiếp từ chỗ dừng
  - Hỗ trợ split train / test / valid hoặc trỏ thẳng vào folder bất kỳ
  - Fallback an toàn nếu model parse JSON thất bại

Format JSONL output (chuẩn qwen-vl-finetune):
  {
    "image": "path/to/image.jpg",
    "conversations": [
      {"from": "human", "value": "<image>\\n<prompt>"},
      {"from": "gpt",   "value": "<JSON string>"}
    ]
  }

Cách dùng:
  python label_cccd.py --split train --data_dir ./data --result_dir ./result
  python label_cccd.py --split all   --data_dir ./data --result_dir ./result
  python label_cccd.py --input_dir ./my_folder --result_dir ./result

  # Đổi model (mặc định là Qwen2.5-VL-7B):
  python label_cccd.py --split all --model_name Qwen/Qwen3-VL-8B-Instruct ...

  # Chạy lại từ checkpoint (tự động, không cần flag thêm):
  python label_cccd.py --split train --data_dir ./data --result_dir ./result
"""

import os
import json
import argparse
import logging
from pathlib import Path
from typing import Optional
from PIL import Image
import torch
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("labeling.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}

# ─────────────────────────────────────────────────────────────────────────────
# Prompt
# ─────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "Bạn là hệ thống OCR chuyên đọc Căn cước công dân (CCCD) Việt Nam. "
    "Chỉ trả về JSON thuần túy, không thêm bất kỳ text hay markdown nào khác."
)

USER_PROMPT = (
    "Đọc ảnh CCCD và trích xuất thông tin ra JSON với các trường sau. "
    "Nếu không đọc được hoặc mặt thẻ không có trường nào thì để null:\n"
    "{\n"
    '  "so_cccd": "12 chữ số",\n'
    '  "ho_va_ten": "họ tên viết hoa",\n'
    '  "ngay_sinh": "DD/MM/YYYY",\n'
    '  "gioi_tinh": "Nam hoặc Nữ",\n'
    '  "quoc_tich": "Việt Nam",\n'
    '  "que_quan": "địa chỉ quê quán",\n'
    '  "noi_thuong_tru": "địa chỉ thường trú đầy đủ",\n'
    '  "ngay_het_han": "DD/MM/YYYY hoặc null",\n'
    '  "dac_diem_nhan_dang": "nếu có hoặc null (thường ở mặt sau)",\n'
    '  "ngay_cap": "DD/MM/YYYY hoặc null (thường ở mặt sau)",\n'
    '  "noi_cap": "nơi cấp thẻ hoặc null (thường ở mặt sau)",\n'
    '  "mat_the": "truoc hoặc sau"\n'
    "}"
)

HUMAN_VALUE = f"<image>\n{USER_PROMPT}"


# ─────────────────────────────────────────────────────────────────────────────
# Checkpoint helpers
# ─────────────────────────────────────────────────────────────────────────────
def checkpoint_path(result_dir: Path, split_name: str) -> Path:
    """Trả về path file checkpoint cho 1 split."""
    return result_dir / f".checkpoint_{split_name}.json"


def load_checkpoint(ckpt_path: Path) -> set:
    """
    Đọc checkpoint: trả về set các image_name đã xử lý xong.
    Checkpoint là dict: {"done": ["img1.jpg", "img2.jpg", ...]}
    """
    if not ckpt_path.exists():
        return set()
    try:
        with open(ckpt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        done = set(data.get("done", []))
        logger.info(f"  [checkpoint] Đã có {len(done)} ảnh hoàn thành từ lần trước")
        return done
    except Exception as e:
        logger.warning(f"  [checkpoint] Đọc lỗi ({e}), bắt đầu lại từ đầu")
        return set()


def save_checkpoint(ckpt_path: Path, done_names: set):
    """Ghi checkpoint ngay sau mỗi ảnh hoàn thành."""
    try:
        with open(ckpt_path, "w", encoding="utf-8") as f:
            json.dump({"done": sorted(done_names)}, f, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"  [checkpoint] Ghi lỗi: {e}")


def clear_checkpoint(ckpt_path: Path):
    """Xóa checkpoint khi split hoàn thành toàn bộ."""
    if ckpt_path.exists():
        ckpt_path.unlink()
        logger.info(f"  [checkpoint] Đã xóa checkpoint (split hoàn tất)")


# ─────────────────────────────────────────────────────────────────────────────
# Load model - Qwen2.5-VL-7B mặc định, tự thử Qwen3-VL nếu truyền vào
# ─────────────────────────────────────────────────────────────────────────────
def load_model(model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct"):
    logger.info(f"Loading: {model_name}")
    logger.info("Lần đầu chạy sẽ download model, vui lòng chờ...")

    # Thử Qwen3-VL trước nếu user truyền model Qwen3
    if "Qwen3" in model_name or "qwen3" in model_name.lower():
        try:
            from transformers import Qwen3VLForConditionalGeneration, AutoProcessor
            processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
            model = Qwen3VLForConditionalGeneration.from_pretrained(
                model_name,
                torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
                device_map="auto",
                trust_remote_code=True,
            )
            model.eval()
            logger.info(f"✓ Qwen3-VL loaded: {model_name}")
            return model, processor
        except (ImportError, AttributeError, OSError) as e:
            logger.warning(f"⚠ Không load được Qwen3-VL ({e})")
            logger.warning("  Fix: pip install git+https://github.com/huggingface/transformers")
            logger.warning("  → Fallback sang Qwen2.5-VL-7B")
            model_name = "Qwen/Qwen2.5-VL-7B-Instruct"

    # Qwen2.5-VL (mặc định và fallback)
    from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
    processor = AutoProcessor.from_pretrained(model_name, trust_remote_code=True)
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        model_name,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    logger.info(f"✓ Qwen2.5-VL loaded: {model_name}")
    return model, processor


# ─────────────────────────────────────────────────────────────────────────────
# Inference 1 ảnh
# ─────────────────────────────────────────────────────────────────────────────
def infer_image(image_path: str, model, processor, max_new_tokens: int = 512) -> str:
    image = Image.open(image_path).convert("RGB")

    messages = [
        {
            "role": "system",
            "content": [{"type": "text", "text": SYSTEM_PROMPT}],
        },
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": USER_PROMPT},
            ],
        },
    ]

    text_input = processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = processor(
        text=[text_input],
        images=[image],
        return_tensors="pt",
        padding=True,
    )
    inputs = {k: v.to(model.device) for k, v in inputs.items()}

    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            top_p=None,
        )

    input_len = inputs["input_ids"].shape[1]
    generated = output_ids[:, input_len:]
    return processor.batch_decode(generated, skip_special_tokens=True)[0].strip()


# ─────────────────────────────────────────────────────────────────────────────
# Parse JSON từ output model
# ─────────────────────────────────────────────────────────────────────────────
def parse_json_safe(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        import re
        m = re.search(r"\{.*?\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Build record đúng format fine-tuning
# ─────────────────────────────────────────────────────────────────────────────
def build_training_record(image_path: str, gpt_answer: str) -> dict:
    return {
        "image": str(image_path),
        "conversations": [
            {"from": "human", "value": HUMAN_VALUE},
            {"from": "gpt",   "value": gpt_answer},
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Label 1 folder với checkpoint
# ─────────────────────────────────────────────────────────────────────────────
def label_folder(
    input_dir: Path,
    result_dir: Path,
    output_filename: str,
    model,
    processor,
    max_new_tokens: int = 512,
    reset: bool = False,
):
    """
    Label toàn bộ ảnh trong input_dir.
    Checkpoint lưu sau MỖI ảnh → chạy lại không bị mất tiến độ.

    Args:
        reset: Nếu True → xóa checkpoint cũ, label lại từ đầu.
    """
    split_name = input_dir.name
    ckpt_path = checkpoint_path(result_dir, split_name)
    output_path = result_dir / output_filename

    result_dir.mkdir(parents=True, exist_ok=True)

    # Xử lý reset
    if reset:
        if ckpt_path.exists():
            ckpt_path.unlink()
            logger.info(f"[{split_name}] Reset: đã xóa checkpoint cũ")
        if output_path.exists():
            output_path.unlink()
            logger.info(f"[{split_name}] Reset: đã xóa output cũ")

    # Load checkpoint
    done_names = load_checkpoint(ckpt_path)

    # Collect ảnh
    all_images = sorted([
        p for p in input_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
    ])
    logger.info(f"[{split_name}] Tổng ảnh: {len(all_images)}")

    if not all_images:
        logger.warning(f"[{split_name}] Không có ảnh!")
        return 0

    # Lọc ảnh chưa xử lý
    todo = [p for p in all_images if p.name not in done_names]
    skipped = len(all_images) - len(todo)

    if skipped > 0:
        logger.info(f"[{split_name}] ✓ Bỏ qua {skipped} ảnh (đã có checkpoint)")
    logger.info(f"[{split_name}] Cần label: {len(todo)} ảnh")

    if not todo:
        logger.info(f"[{split_name}] Tất cả đã hoàn thành!")
        return 0

    # Mở file output (append nếu đang resume)
    write_mode = "a" if output_path.exists() else "w"
    success = errors = parse_fail = 0

    with open(output_path, write_mode, encoding="utf-8") as f_out:
        for img_path in tqdm(todo, desc=f"  [{split_name}]", unit="img"):
            try:
                raw = infer_image(str(img_path), model, processor, max_new_tokens)
                parsed = parse_json_safe(raw)

                if parsed is not None:
                    gpt_answer = json.dumps(parsed, ensure_ascii=False)
                    success += 1
                else:
                    gpt_answer = raw
                    parse_fail += 1
                    logger.warning(f"  parse_fail: {img_path.name} | {raw[:60]}...")

                record = build_training_record(str(img_path), gpt_answer)
                record["_meta"] = {
                    "parse_ok": parsed is not None,
                    "raw_output": raw,
                }

                # Ghi record vào JSONL
                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()  # flush ngay để không mất data khi ngắt

                # ── Lưu checkpoint sau mỗi ảnh ──
                done_names.add(img_path.name)
                save_checkpoint(ckpt_path, done_names)

            except KeyboardInterrupt:
                # Ctrl+C: lưu checkpoint trước khi thoát
                logger.warning(f"\n[{split_name}] Bị ngắt! Đã lưu checkpoint ({len(done_names)} ảnh)")
                raise

            except Exception as e:
                logger.error(f"  ERROR {img_path.name}: {e}")
                errors += 1
                # Vẫn lưu checkpoint với ảnh lỗi (bỏ qua lần sau)
                done_names.add(img_path.name)
                save_checkpoint(ckpt_path, done_names)

    # Xóa checkpoint khi split hoàn tất hoàn toàn
    if len(done_names) >= len(all_images):
        clear_checkpoint(ckpt_path)

    total = success + parse_fail
    logger.info(
        f"[{split_name}] DONE → {output_filename} | "
        f"✓ {success} | parse_fail: {parse_fail} | error: {errors} | tổng: {total}"
    )
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CCCD Auto Labeler → JSONL fine-tuning (Qwen2.5-VL-7B)",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Ví dụ:
  # Label split train (tự resume nếu đã chạy dở)
  python label_cccd.py --split train --data_dir ./data --result_dir ./result

  # Label tất cả splits
  python label_cccd.py --split all --data_dir ./data --result_dir ./result

  # Trỏ thẳng vào folder bất kỳ
  python label_cccd.py --input_dir ./my_folder --result_dir ./result

  # Dùng model local đã tải về
  python label_cccd.py --split all --model_name ./models/Qwen2.5-VL-7B-Instruct ...

  # Đổi sang Qwen3-VL-8B (nếu server đủ mạnh)
  python label_cccd.py --split all --model_name Qwen/Qwen3-VL-8B-Instruct ...

  # Reset checkpoint, label lại từ đầu
  python label_cccd.py --split train --reset ...
        """,
    )

    # Nguồn ảnh
    g = parser.add_argument_group("Nguồn ảnh (chọn 1)")
    g.add_argument(
        "--split", choices=["train", "test", "valid", "all"],
        help="Split cần label. Dùng với --data_dir",
    )
    g.add_argument(
        "--data_dir", default="./data",
        help="Root folder chứa train/test/valid (default: ./data)",
    )
    g.add_argument(
        "--input_dir",
        help="Trỏ thẳng vào 1 folder bất kỳ (bỏ qua --split / --data_dir)",
    )

    # Output
    parser.add_argument(
        "--result_dir", default="./result",
        help="Folder lưu JSONL output và checkpoint (default: ./result)",
    )

    # Model
    parser.add_argument(
        "--model_name", default="Qwen/Qwen2.5-VL-7B-Instruct",
        help="HuggingFace ID hoặc path local (default: Qwen/Qwen2.5-VL-7B-Instruct)",
    )
    parser.add_argument("--max_new_tokens", type=int, default=512)

    # Checkpoint control
    parser.add_argument(
        "--reset", action="store_true",
        help="Xóa checkpoint và output cũ, label lại từ đầu",
    )

    args = parser.parse_args()

    # Xác định tasks
    tasks = []  # (input_dir, output_filename)
    if args.input_dir:
        p = Path(args.input_dir)
        if not p.exists():
            logger.error(f"Folder không tồn tại: {p}")
            return
        tasks.append((p, f"{p.name}_labels.jsonl"))
    elif args.split:
        data_dir = Path(args.data_dir)
        splits = ["train", "test", "valid"] if args.split == "all" else [args.split]
        for s in splits:
            folder = data_dir / s
            if not folder.exists():
                logger.warning(f"Bỏ qua, không tồn tại: {folder}")
                continue
            tasks.append((folder, f"{s}_labels.jsonl"))
    else:
        logger.error("Cần truyền --split hoặc --input_dir")
        parser.print_help()
        return

    if not tasks:
        logger.error("Không có folder nào hợp lệ!")
        return

    result_dir = Path(args.result_dir)

    logger.info(f"\n{'='*60}")
    logger.info(f"Model     : {args.model_name}")
    logger.info(f"Output    : {result_dir}/")
    logger.info(f"Checkpoint: {result_dir}/.checkpoint_<split>.json")
    logger.info(f"Reset     : {args.reset}")
    for folder, fname in tasks:
        logger.info(f"  {folder.name:10s} → {fname}")
    logger.info(f"{'='*60}\n")

    # Load model (1 lần duy nhất cho tất cả splits)
    model, processor = load_model(args.model_name)

    # Chạy từng split
    for input_dir, output_filename in tasks:
        logger.info(f"\n{'─'*40}")
        logger.info(f"Split: {input_dir}")
        try:
            label_folder(
                input_dir=input_dir,
                result_dir=result_dir,
                output_filename=output_filename,
                model=model,
                processor=processor,
                max_new_tokens=args.max_new_tokens,
                reset=args.reset,
            )
        except KeyboardInterrupt:
            logger.warning("\nDừng theo yêu cầu. Checkpoint đã được lưu.")
            logger.warning("Chạy lại cùng lệnh để tiếp tục từ chỗ dừng.")
            break

    logger.info(f"\n{'='*60}")
    logger.info(f"KẾT QUẢ trong: {result_dir}/")
    for _, fname in tasks:
        out = result_dir / fname
        if out.exists():
            n = sum(1 for _ in open(out, encoding="utf-8"))
            logger.info(f"  {fname}: {n} records")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()