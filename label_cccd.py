"""
CCCD Auto Labeler - Qwen3-VL-8B (Local)
========================================
Đọc ảnh CCCD, extract thông tin, xuất ra JSONL đúng format fine-tuning của Qwen3-VL.

Format JSONL chuẩn cho Qwen3-VL fine-tuning (official qwen-vl-finetune):
{
  "image": "path/to/image.jpg",
  "conversations": [
    {"from": "human", "value": "<image>\n<prompt>"},
    {"from": "gpt",   "value": "<answer JSON>"}
  ]
}

Cách dùng:
  python label_cccd.py --split train --data_dir ./data --result_dir ./result
  python label_cccd.py --split all   --data_dir ./data --result_dir ./result
  python label_cccd.py --input_dir ./my_folder --result_dir ./result
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
# Prompt dùng để inference (cũng là prompt trong conversations["human"])
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

# Human value trong conversations: <image> tag PHẢI đứng đầu
HUMAN_VALUE = f"<image>\n{USER_PROMPT}"


# ─────────────────────────────────────────────────────────────────────────────
# Load model
# ─────────────────────────────────────────────────────────────────────────────
def load_model(model_name: str = "Qwen/Qwen3-VL-8B-Instruct"):
    logger.info(f"Loading: {model_name}")
    logger.info("Lần đầu chạy sẽ download ~17GB, vui lòng chờ...")

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
        logger.info("✓ Qwen3-VL-8B loaded!")
        return model, processor

    except (ImportError, AttributeError):
        logger.warning("⚠ transformers chưa có Qwen3VL → fallback Qwen2.5-VL-7B")
        logger.warning("Fix: pip install git+https://github.com/huggingface/transformers")
        from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
        fb = "Qwen/Qwen2.5-VL-7B-Instruct"
        processor = AutoProcessor.from_pretrained(fb, trust_remote_code=True)
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            fb,
            torch_dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
            device_map="auto",
            trust_remote_code=True,
        )
        model.eval()
        logger.info("✓ Qwen2.5-VL-7B (fallback) loaded!")
        return model, processor


# ─────────────────────────────────────────────────────────────────────────────
# Inference 1 ảnh → raw text
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
# Parse JSON an toàn từ output model
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
# Build record đúng format Qwen3-VL fine-tuning
# ─────────────────────────────────────────────────────────────────────────────
def build_training_record(image_path: str, gpt_answer: str) -> dict:
    """
    Format chuẩn theo qwen-vl-finetune/README.md:

    {
      "image": "path/to/image.jpg",          ← path tương đối hoặc tuyệt đối
      "conversations": [
        {"from": "human", "value": "<image>\\n<prompt>"},
        {"from": "gpt",   "value": "<extracted JSON string>"}
      ]
    }
    """
    return {
        "image": str(image_path),
        "conversations": [
            {
                "from": "human",
                "value": HUMAN_VALUE,           # "<image>\n<prompt>" - bắt buộc có <image>
            },
            {
                "from": "gpt",
                "value": gpt_answer,            # JSON string (raw output của model)
            },
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Label toàn bộ 1 folder
# ─────────────────────────────────────────────────────────────────────────────
def label_folder(
    input_dir: Path,
    result_dir: Path,
    output_filename: str,
    model,
    processor,
    max_new_tokens: int = 512,
    resume: bool = True,
):
    image_files = sorted([
        p for p in input_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTENSIONS
    ])
    logger.info(f"[{input_dir.name}] {len(image_files)} ảnh tìm thấy")

    if not image_files:
        logger.warning(f"[{input_dir.name}] Không có ảnh!")
        return 0

    result_dir.mkdir(parents=True, exist_ok=True)
    output_path = result_dir / output_filename

    # Resume: đọc image name đã xử lý
    done_names = set()
    if resume and output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    done_names.add(Path(rec.get("image", "")).name)
                except Exception:
                    pass
        if done_names:
            logger.info(f"[{input_dir.name}] Resume: bỏ qua {len(done_names)} ảnh đã có")

    todo = [p for p in image_files if p.name not in done_names]
    logger.info(f"[{input_dir.name}] Còn lại: {len(todo)} ảnh cần label")

    if not todo:
        logger.info(f"[{input_dir.name}] Tất cả đã label!")
        return 0

    success = errors = parse_fail = 0
    write_mode = "a" if (resume and output_path.exists()) else "w"

    with open(output_path, write_mode, encoding="utf-8") as f_out:
        for img_path in tqdm(todo, desc=f"  [{input_dir.name}]"):
            try:
                raw = infer_image(str(img_path), model, processor, max_new_tokens)
                parsed = parse_json_safe(raw)

                # Gpt answer: nếu parse được → dùng JSON đẹp; nếu không → giữ raw
                if parsed is not None:
                    gpt_answer = json.dumps(parsed, ensure_ascii=False)
                    success += 1
                else:
                    # Vẫn lưu raw, đánh dấu parse_fail để review sau
                    gpt_answer = raw
                    parse_fail += 1
                    logger.warning(f"  parse_fail: {img_path.name} | raw: {raw[:80]}...")

                record = build_training_record(str(img_path), gpt_answer)

                # Thêm metadata debug vào field riêng (không ảnh hưởng training)
                record["_meta"] = {
                    "parse_ok": parsed is not None,
                    "raw_output": raw,
                }

                f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                f_out.flush()

            except Exception as e:
                logger.error(f"  ERROR {img_path.name}: {e}")
                errors += 1

    total = success + parse_fail
    logger.info(
        f"[{input_dir.name}] DONE → {output_filename} | "
        f"✓ JSON ok: {success} | parse_fail: {parse_fail} | error: {errors}"
    )
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="CCCD Auto Labeler → Qwen3-VL fine-tuning JSONL",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Ví dụ:
  python label_cccd.py --split train --data_dir ./data --result_dir ./result
  python label_cccd.py --split all   --data_dir ./data --result_dir ./result
  python label_cccd.py --input_dir ./my_folder --result_dir ./result
  python label_cccd.py --split all   --model_name ./models/Qwen3-VL-8B-Instruct \\
                       --data_dir ./data --result_dir ./result
        """,
    )

    # Nguồn ảnh
    g = parser.add_argument_group("Nguồn ảnh (chọn 1)")
    g.add_argument(
        "--split", choices=["train", "test", "valid", "all"],
        help="Chọn split. Dùng với --data_dir",
    )
    g.add_argument("--data_dir", default="./data",
                   help="Root folder chứa train/test/valid (default: ./data)")
    g.add_argument("--input_dir",
                   help="Trỏ thẳng vào 1 folder bất kỳ")

    # Output
    parser.add_argument("--result_dir", default="./result",
                        help="Folder lưu JSONL output (default: ./result)")

    # Model
    parser.add_argument("--model_name", default="Qwen/Qwen3-VL-8B-Instruct",
                        help="HuggingFace ID hoặc path local model")
    parser.add_argument("--max_new_tokens", type=int, default=512)
    parser.add_argument("--no_resume", action="store_true",
                        help="Ghi đè file output (không resume)")

    args = parser.parse_args()
    resume = not args.no_resume

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
    logger.info(f"Model  : {args.model_name}")
    logger.info(f"Output : {result_dir}/")
    for folder, fname in tasks:
        logger.info(f"  {folder.name:10s} → {fname}")
    logger.info(f"{'='*60}\n")

    model, processor = load_model(args.model_name)

    for input_dir, output_filename in tasks:
        logger.info(f"\n── {input_dir} ──")
        label_folder(
            input_dir=input_dir,
            result_dir=result_dir,
            output_filename=output_filename,
            model=model,
            processor=processor,
            max_new_tokens=args.max_new_tokens,
            resume=resume,
        )

    logger.info(f"\n{'='*60}")
    logger.info(f"HOÀN THÀNH! Kết quả trong: {result_dir}/")
    for _, fname in tasks:
        out = result_dir / fname
        if out.exists():
            n = sum(1 for _ in open(out, encoding="utf-8"))
            logger.info(f"  {fname}: {n} records")
    logger.info(f"{'='*60}")


if __name__ == "__main__":
    main()
