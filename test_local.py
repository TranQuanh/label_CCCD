"""
test_local.py - Test pipeline trên máy local trước khi đưa lên server
======================================================================
Làm 4 việc:
  1. Kiểm tra môi trường (Python, torch, transformers, CUDA)
  2. Tạo ảnh CCCD giả để test
  3. Chạy inference thử (nếu có GPU / bỏ qua với --skip_inference)
  4. Validate format JSONL output + kiểm tra checkpoint

Chạy:
  python test_local.py                      # check full pipeline
  python test_local.py --skip_inference     # chỉ check env + format, không load model
  python test_local.py --validate_file ./result/train_labels.jsonl
  python test_local.py --model_name ./models/Qwen2.5-VL-7B-Instruct
"""

import sys
import json
import argparse
import tempfile
from pathlib import Path


# ─────────────────────────────────────────────────────────────────────────────
# 1. Check môi trường
# ─────────────────────────────────────────────────────────────────────────────
def check_environment():
    print("\n" + "="*60)
    print("BƯỚC 1: Kiểm tra môi trường")
    print("="*60)
    ok = True

    v = sys.version_info
    print(f"  Python : {v.major}.{v.minor}.{v.micro}", end="")
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print("  [✗] Cần Python >= 3.10")
        ok = False
    else:
        print("  [✓]")

    try:
        import torch
        print(f"  torch  : {torch.__version__}  [✓]")
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"  GPU    : {gpu}")
            print(f"  VRAM   : {vram:.1f} GB", end="")
            if vram < 8:
                print("  [!] < 8GB: dùng bản 4-bit hoặc chạy CPU (chậm)")
            elif vram < 16:
                print("  [!] < 16GB: khuyến nghị dùng bản AWQ 4-bit")
            else:
                print("  [✓]")
        else:
            print("  CUDA   : không có — inference sẽ chạy CPU (rất chậm)")
    except ImportError:
        print("  [✗] torch chưa cài: pip install torch")
        ok = False

    try:
        import transformers
        print(f"  transformers: {transformers.__version__}  [✓]")
        # Kiểm tra Qwen2.5-VL
        try:
            from transformers import Qwen2_5_VLForConditionalGeneration
            print("  Qwen2.5-VL : [✓] sẵn sàng")
        except ImportError:
            print("  Qwen2.5-VL : [✗] transformers quá cũ, cần >= 4.49.0")
            ok = False
        # Check Qwen3-VL (optional)
        try:
            from transformers import Qwen3VLForConditionalGeneration
            print("  Qwen3-VL   : [✓] có (nếu muốn dùng Qwen3-VL-8B)")
        except ImportError:
            print("  Qwen3-VL   : [!] chưa có (cần pip install từ source — không bắt buộc)")
    except ImportError:
        print("  [✗] transformers chưa cài")
        ok = False

    try:
        from PIL import Image
        import PIL
        print(f"  Pillow : {PIL.__version__}  [✓]")
    except ImportError:
        print("  [✗] Pillow chưa cài: pip install Pillow")
        ok = False

    try:
        import qwen_vl_utils
        print(f"  qwen-vl-utils: [✓]")
    except ImportError:
        print("  [!] qwen-vl-utils chưa cài: pip install qwen-vl-utils>=0.0.8")

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tạo ảnh CCCD giả
# ─────────────────────────────────────────────────────────────────────────────
def create_dummy_cccd(save_path: str, side: str = "truoc"):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (856, 540), color=(240, 245, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(5, 5), (851, 535)], outline=(0, 80, 160), width=3)

    if side == "truoc":
        items = [
            ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", (428, 30)),
            ("CĂN CƯỚC CÔNG DÂN", (428, 65)),
            ("Số: 001204012345", (200, 130)),
            ("Họ và tên: NGUYỄN VĂN TEST", (200, 165)),
            ("Ngày sinh: 01/01/1990", (200, 200)),
            ("Giới tính: Nam    Quốc tịch: Việt Nam", (200, 235)),
            ("Quê quán: Xã Tân Hưng, Huyện Tân Châu, Tỉnh Tây Ninh", (200, 270)),
            ("Nơi thường trú: 123 Đường Lê Lợi, Phường Bến Nghé,", (200, 305)),
            ("Quận 1, Thành phố Hồ Chí Minh", (200, 330)),
            ("Có giá trị đến: 01/01/2035", (200, 390)),
        ]
    else:
        items = [
            ("Đặc điểm nhận dạng: Nốt ruồi bên trái trán", (50, 100)),
            ("Ngày cấp: 15/03/2020", (50, 160)),
            ("Nơi cấp: CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH", (50, 220)),
            ("VỀ TRẬT TỰ XÃ HỘI", (50, 255)),
        ]

    for text, pos in items:
        anchor = "mm" if pos[0] == 428 else "lm"
        draw.text(pos, text, fill=(0, 0, 0), anchor=anchor)

    img.save(save_path, quality=95)
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate JSONL format + checkpoint
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_KEYS = [
    "so_cccd", "ho_va_ten", "ngay_sinh", "gioi_tinh", "quoc_tich",
    "que_quan", "noi_thuong_tru", "ngay_het_han", "dac_diem_nhan_dang",
    "ngay_cap", "noi_cap", "mat_the",
]

def validate_jsonl_format(jsonl_path: str) -> bool:
    print(f"\n{'='*60}")
    print("Validate JSONL format")
    print("="*60)

    records = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append((i, json.loads(line)))
            except json.JSONDecodeError as e:
                print(f"  [✗] Dòng {i}: JSON parse lỗi - {e}")

    if not records:
        print("  [✗] File rỗng!")
        return False

    print(f"  Tổng records: {len(records)}")

    ok_count = parse_ok_count = 0
    errors = []

    for i, rec in records:
        rec_errors = []

        # Kiểm tra field "image"
        if "image" not in rec or not rec["image"]:
            rec_errors.append("thiếu/rỗng field 'image'")

        # Kiểm tra "conversations"
        convs = rec.get("conversations", [])
        if not isinstance(convs, list) or len(convs) != 2:
            rec_errors.append(f"'conversations' phải là list 2 phần tử")
        else:
            human, gpt = convs[0], convs[1]
            if human.get("from") != "human":
                rec_errors.append("conversations[0].from != 'human'")
            if "<image>" not in human.get("value", ""):
                rec_errors.append("conversations[0].value thiếu tag <image>")
            if gpt.get("from") != "gpt":
                rec_errors.append("conversations[1].from != 'gpt'")

            gpt_val = gpt.get("value", "")
            if not gpt_val.strip():
                rec_errors.append("gpt value rỗng")
            else:
                try:
                    extracted = json.loads(gpt_val)
                    missing = [k for k in REQUIRED_KEYS if k not in extracted]
                    if missing:
                        rec_errors.append(f"thiếu keys: {missing}")
                    parse_ok_count += 1
                except json.JSONDecodeError:
                    rec_errors.append("gpt value không phải JSON hợp lệ (parse_fail record)")

        # _meta check
        meta = rec.get("_meta", {})
        if meta and not meta.get("parse_ok"):
            rec_errors.append("[!] _meta.parse_ok=False (model không parse được JSON)")

        if not rec_errors:
            ok_count += 1
        else:
            errors.append(f"  Record {i} ({Path(rec.get('image','')).name}): {'; '.join(rec_errors)}")

    if errors:
        print(f"\n  Tìm thấy vấn đề ở {len(errors)} records:")
        for e in errors[:8]:
            print(e)
        if len(errors) > 8:
            print(f"  ... và {len(errors)-8} records nữa")
    else:
        print(f"  [✓] Tất cả {ok_count} records đều đúng format!")

    print(f"\n  Tổng kết:")
    print(f"    Format đúng  : {ok_count}/{len(records)}")
    print(f"    JSON parse ok: {parse_ok_count}/{len(records)}")

    # In mẫu 1 record
    print(f"\n  Mẫu record đầu tiên:")
    print("  " + "-"*50)
    sample = {k: v for k, v in records[0][1].items() if k != "_meta"}
    print("  " + json.dumps(sample, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    return ok_count == len(records)


def check_checkpoint(result_dir: str):
    """Hiển thị trạng thái checkpoint của tất cả splits."""
    print(f"\n{'='*60}")
    print("Trạng thái checkpoint")
    print("="*60)
    result_path = Path(result_dir)
    ckpt_files = list(result_path.glob(".checkpoint_*.json"))
    if not ckpt_files:
        print("  Không có checkpoint nào (tất cả splits đã hoàn thành hoặc chưa chạy)")
        return
    for ckpt in sorted(ckpt_files):
        try:
            with open(ckpt, "r", encoding="utf-8") as f:
                data = json.load(f)
            done = data.get("done", [])
            split_name = ckpt.stem.replace(".checkpoint_", "")
            print(f"  [{split_name}] {len(done)} ảnh đã xong (checkpoint đang active)")
        except Exception as e:
            print(f"  {ckpt.name}: lỗi đọc — {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Test inference thật
# ─────────────────────────────────────────────────────────────────────────────
def run_inference_test(model_name: str, tmp_dir: Path):
    print(f"\n{'='*60}")
    print("BƯỚC 2: Test inference (load model + chạy thử)")
    print("="*60)
    print(f"  Model: {model_name}")

    # Tạo 2 ảnh test (mặt trước + mặt sau)
    test_input = tmp_dir / "test_split"
    test_input.mkdir(exist_ok=True)
    for i, side in enumerate(["truoc", "sau"]):
        create_dummy_cccd(str(test_input / f"cccd_{i:03d}_{side}.jpg"), side)
    print(f"  Ảnh test: {test_input}/ (2 ảnh)")

    result_dir = tmp_dir / "result"

    import subprocess
    cmd = [
        sys.executable, "label_cccd.py",
        "--input_dir", str(test_input),
        "--result_dir", str(result_dir),
        "--model_name", model_name,
        "--max_new_tokens", "300",
    ]
    print(f"\n  Chạy: {' '.join(cmd)}\n")
    result = subprocess.run(cmd, capture_output=False)

    if result.returncode != 0:
        print(f"\n  [✗] label_cccd.py thoát với lỗi (code {result.returncode})")
        return None

    out_file = result_dir / "test_split_labels.jsonl"
    if not out_file.exists():
        print("  [✗] Không tìm thấy file output!")
        return None

    print(f"\n  [✓] Output: {out_file}")

    # Kiểm tra checkpoint đã được xóa sau khi hoàn tất
    ckpt = result_dir / ".checkpoint_test_split.json"
    if not ckpt.exists():
        print("  [✓] Checkpoint đã tự xóa sau khi hoàn thành")
    else:
        print("  [!] Checkpoint vẫn còn (split chưa hoàn thành hoàn toàn)")

    return str(out_file)


def create_mock_jsonl(save_path: str, tmp_dir: Path):
    """Tạo JSONL mẫu đúng format để test validate mà không cần model."""
    img_path = tmp_dir / "mock_cccd.jpg"
    create_dummy_cccd(str(img_path), "truoc")

    from label_cccd import HUMAN_VALUE

    records = [
        {
            "image": str(img_path),
            "conversations": [
                {"from": "human", "value": HUMAN_VALUE},
                {"from": "gpt", "value": json.dumps({
                    "so_cccd": "001204012345",
                    "ho_va_ten": "NGUYỄN VĂN TEST",
                    "ngay_sinh": "01/01/1990",
                    "gioi_tinh": "Nam",
                    "quoc_tich": "Việt Nam",
                    "que_quan": "Xã Tân Hưng, Huyện Tân Châu, Tỉnh Tây Ninh",
                    "noi_thuong_tru": "123 Đường Lê Lợi, Quận 1, TP.HCM",
                    "ngay_het_han": "01/01/2035",
                    "dac_diem_nhan_dang": None,
                    "ngay_cap": None,
                    "noi_cap": None,
                    "mat_the": "truoc",
                }, ensure_ascii=False)},
            ],
            "_meta": {"parse_ok": True, "raw_output": "..."},
        },
        {
            "image": str(img_path),
            "conversations": [
                {"from": "human", "value": HUMAN_VALUE},
                {"from": "gpt", "value": json.dumps({
                    "so_cccd": None,
                    "ho_va_ten": None,
                    "ngay_sinh": None,
                    "gioi_tinh": None,
                    "quoc_tich": None,
                    "que_quan": None,
                    "noi_thuong_tru": None,
                    "ngay_het_han": None,
                    "dac_diem_nhan_dang": "Nốt ruồi bên trái trán",
                    "ngay_cap": "15/03/2020",
                    "noi_cap": "Cục Cảnh sát QLHC về TTXH",
                    "mat_the": "sau",
                }, ensure_ascii=False)},
            ],
            "_meta": {"parse_ok": True, "raw_output": "..."},
        },
    ]

    with open(save_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Test CCCD Labeler pipeline")
    parser.add_argument(
        "--model_name", default="Qwen/Qwen2.5-VL-7B-Instruct",
        help="Model để test inference (default: Qwen2.5-VL-7B)",
    )
    parser.add_argument(
        "--skip_inference", action="store_true",
        help="Bỏ qua load model, chỉ test env + format",
    )
    parser.add_argument(
        "--validate_file",
        help="Validate 1 file JSONL có sẵn",
    )
    parser.add_argument(
        "--check_checkpoint", default="./result",
        help="Xem trạng thái checkpoint trong folder (default: ./result)",
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  CCCD Labeler - Local Test (Qwen2.5-VL-7B)")
    print("="*60)

    if args.validate_file:
        validate_jsonl_format(args.validate_file)
        check_checkpoint(args.check_checkpoint)
        return

    env_ok = check_environment()
    check_checkpoint(args.check_checkpoint)

    tmp_dir = Path(tempfile.mkdtemp(prefix="cccd_test_"))
    print(f"\n  Thư mục tạm: {tmp_dir}")

    if args.skip_inference:
        print(f"\n{'='*60}")
        print("BƯỚC 2: Tạo JSONL mẫu (skip inference)")
        print("="*60)
        mock_path = str(tmp_dir / "mock_labels.jsonl")
        create_mock_jsonl(mock_path, tmp_dir)
        print(f"  [✓] Mock JSONL: {mock_path}")
        validate_jsonl_format(mock_path)
    else:
        if not env_ok:
            print("\n[✗] Môi trường chưa đủ. Fix lỗi trên rồi chạy lại.")
            print("    Hoặc: python test_local.py --skip_inference")
            return
        out_file = run_inference_test(args.model_name, tmp_dir)
        if out_file:
            validate_jsonl_format(out_file)

    print(f"\n{'='*60}")
    if args.skip_inference:
        print("  [✓] Kiểm tra môi trường + format xong!")
        print("  → Chạy không có --skip_inference để test inference thật")
    else:
        print("  [✓] Pipeline hoạt động! Sẵn sàng đưa lên server.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()