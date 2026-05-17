"""
test_local.py - Test pipeline trên máy local trước khi đưa lên server
======================================================================
Script này làm 4 việc:
  1. Kiểm tra môi trường (Python, torch, transformers, CUDA)
  2. Tạo ảnh CCCD giả để test (không cần ảnh thật)
  3. Chạy inference thử (nếu có GPU hoặc bỏ qua nếu chỉ muốn check format)
  4. Validate format JSONL output đúng chuẩn Qwen3-VL fine-tuning

Chạy:
  python test_local.py                     # check full
  python test_local.py --skip_inference    # chỉ check env + format, không load model
  python test_local.py --model_name ./models/Qwen3-VL-8B-Instruct
"""

import sys
import os
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

    # Python version
    v = sys.version_info
    print(f"  Python : {v.major}.{v.minor}.{v.micro}")
    if v.major < 3 or (v.major == 3 and v.minor < 10):
        print("  [✗] Cần Python >= 3.10")
        ok = False
    else:
        print("  [✓] Python OK")

    # torch
    try:
        import torch
        print(f"  torch  : {torch.__version__}")
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"  GPU    : {gpu}")
            print(f"  VRAM   : {vram:.1f} GB")
            if vram < 15:
                print("  [!] CẢNH BÁO: VRAM < 15GB, có thể bị OOM khi load Qwen3-VL-8B")
        else:
            print("  [!] CUDA không có — inference sẽ rất chậm (CPU mode)")
    except ImportError:
        print("  [✗] torch chưa cài: pip install torch")
        ok = False

    # transformers
    try:
        import transformers
        print(f"  transformers: {transformers.__version__}")
        # Kiểm tra có Qwen3VL chưa
        try:
            from transformers import Qwen3VLForConditionalGeneration
            print("  [✓] Qwen3VLForConditionalGeneration: có")
        except ImportError:
            print("  [!] Qwen3VL chưa có trong transformers hiện tại")
            print("      Fix: pip install git+https://github.com/huggingface/transformers")
            print("      Script sẽ fallback sang Qwen2.5-VL-7B")
    except ImportError:
        print("  [✗] transformers chưa cài")
        ok = False

    # PIL
    try:
        from PIL import Image
        import PIL
        print(f"  Pillow : {PIL.__version__} [✓]")
    except ImportError:
        print("  [✗] Pillow chưa cài: pip install Pillow")
        ok = False

    # qwen-vl-utils
    try:
        import qwen_vl_utils
        print(f"  qwen-vl-utils: OK [✓]")
    except ImportError:
        print("  [!] qwen-vl-utils chưa cài: pip install qwen-vl-utils>=0.0.14")

    return ok


# ─────────────────────────────────────────────────────────────────────────────
# 2. Tạo ảnh CCCD giả
# ─────────────────────────────────────────────────────────────────────────────
def create_dummy_cccd(save_path: str, side: str = "truoc"):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (856, 540), color=(240, 245, 255))
    draw = ImageDraw.Draw(img)

    # Viền
    draw.rectangle([(5, 5), (851, 535)], outline=(0, 80, 160), width=3)

    if side == "truoc":
        lines = [
            ("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM", (428, 30)),
            ("Độc lập - Tự do - Hạnh phúc", (428, 55)),
            ("CĂN CƯỚC CÔNG DÂN", (428, 90)),
            ("Số: 001204012345", (200, 150)),
            ("Họ và tên: NGUYỄN VĂN TEST", (200, 190)),
            ("Ngày sinh: 01/01/1990", (200, 225)),
            ("Giới tính: Nam    Quốc tịch: Việt Nam", (200, 260)),
            ("Quê quán: Xã Tân Hưng, Huyện Tân Châu, Tỉnh Tây Ninh", (200, 295)),
            ("Nơi thường trú: 123 Đường Lê Lợi, Phường Bến Nghé,", (200, 330)),
            ("Quận 1, Thành phố Hồ Chí Minh", (200, 355)),
            ("Có giá trị đến: 01/01/2035", (200, 400)),
        ]
        for text, pos in lines:
            anchor = "mm" if pos[0] == 428 else "lm"
            draw.text(pos, text, fill=(0, 0, 0), anchor=anchor)
    else:
        lines = [
            ("Đặc điểm nhận dạng: Nốt ruồi bên trái trán", (50, 100)),
            ("Ngày, tháng, năm: 15/03/2020", (50, 200)),
            ("Nơi cấp: CỤC CẢNH SÁT QUẢN LÝ HÀNH CHÍNH VỀ TRẬT TỰ XÃ HỘI", (50, 250)),
        ]
        for text, pos in lines:
            draw.text(pos, text, fill=(0, 0, 0))

    img.save(save_path, quality=95)
    return save_path


# ─────────────────────────────────────────────────────────────────────────────
# 3. Validate format JSONL
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_KEYS_EXTRACTED = [
    "so_cccd", "ho_va_ten", "ngay_sinh", "gioi_tinh",
    "quoc_tich", "que_quan", "noi_thuong_tru", "ngay_het_han",
    "dac_diem_nhan_dang", "mat_the",
]

def validate_jsonl_format(jsonl_path: str) -> bool:
    print(f"\n{'='*60}")
    print("BƯỚC 3: Validate JSONL format")
    print("="*60)

    errors = []
    records = []

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                records.append((i, rec))
            except json.JSONDecodeError as e:
                errors.append(f"  Dòng {i}: JSON parse lỗi - {e}")

    if not records:
        print("  [✗] File rỗng hoặc không có record hợp lệ!")
        return False

    print(f"  Tổng records: {len(records)}")

    ok_count = 0
    for i, rec in records:
        rec_errors = []

        # Kiểm tra field "image"
        if "image" not in rec:
            rec_errors.append("thiếu field 'image'")
        elif not rec["image"]:
            rec_errors.append("'image' rỗng")

        # Kiểm tra field "conversations"
        if "conversations" not in rec:
            rec_errors.append("thiếu field 'conversations'")
        else:
            convs = rec["conversations"]
            if not isinstance(convs, list) or len(convs) != 2:
                rec_errors.append(f"'conversations' phải là list 2 phần tử, hiện có {len(convs)}")
            else:
                human, gpt = convs[0], convs[1]

                # human turn
                if human.get("from") != "human":
                    rec_errors.append("conversations[0].from phải là 'human'")
                if "<image>" not in human.get("value", ""):
                    rec_errors.append("conversations[0].value phải chứa '<image>'")

                # gpt turn
                if gpt.get("from") != "gpt":
                    rec_errors.append("conversations[1].from phải là 'gpt'")
                if not gpt.get("value", "").strip():
                    rec_errors.append("conversations[1].value (gpt answer) rỗng")
                else:
                    # Thử parse JSON trong gpt answer
                    try:
                        extracted = json.loads(gpt["value"])
                        missing = [k for k in REQUIRED_KEYS_EXTRACTED if k not in extracted]
                        if missing:
                            rec_errors.append(f"gpt answer thiếu keys: {missing}")
                    except json.JSONDecodeError:
                        rec_errors.append("gpt answer không phải JSON hợp lệ")

        if rec_errors:
            errors.append(f"  Record {i} ({Path(rec.get('image','')).name}): {'; '.join(rec_errors)}")
        else:
            ok_count += 1

    if errors:
        print(f"\n  [!] Tìm thấy {len(errors)} lỗi:")
        for e in errors[:10]:  # Chỉ in 10 lỗi đầu
            print(e)
        if len(errors) > 10:
            print(f"  ... và {len(errors)-10} lỗi nữa")
    else:
        print(f"  [✓] Tất cả {ok_count} records đều hợp lệ!")

    print(f"\n  [✓] OK: {ok_count}/{len(records)} records")

    # In mẫu 1 record
    print("\n  Mẫu record đầu tiên:")
    print("  " + "-"*50)
    sample = records[0][1].copy()
    sample.pop("_meta", None)  # bỏ metadata debug
    print("  " + json.dumps(sample, ensure_ascii=False, indent=2).replace("\n", "\n  "))

    return ok_count == len(records)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Chạy inference thật (optional)
# ─────────────────────────────────────────────────────────────────────────────
def run_inference_test(model_name: str, tmp_dir: Path):
    print(f"\n{'='*60}")
    print("BƯỚC 2: Test inference (load model + chạy thử)")
    print("="*60)
    print(f"  Model: {model_name}")

    # Tạo ảnh test
    img_path = tmp_dir / "test_cccd_truoc.jpg"
    create_dummy_cccd(str(img_path), "truoc")
    print(f"  Ảnh test: {img_path}")

    # Tạo folder giả
    test_input = tmp_dir / "test_split"
    test_input.mkdir(exist_ok=True)
    (test_input / "cccd_001.jpg").write_bytes(img_path.read_bytes())
    (test_input / "cccd_002.jpg").write_bytes(img_path.read_bytes())

    result_dir = tmp_dir / "result"

    # Gọi label_cccd.py
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
    return str(out_file)


# ─────────────────────────────────────────────────────────────────────────────
# Validate format của file jsonl bất kỳ (không cần inference)
# ─────────────────────────────────────────────────────────────────────────────
def create_mock_jsonl(save_path: str, tmp_dir: Path):
    """Tạo JSONL mẫu đúng format để test validate mà không cần model"""
    img_path = tmp_dir / "mock_cccd.jpg"
    create_dummy_cccd(str(img_path), "truoc")

    records = [
        {
            "image": str(img_path),
            "conversations": [
                {
                    "from": "human",
                    "value": "<image>\nĐọc ảnh CCCD và trích xuất thông tin ra JSON...",
                },
                {
                    "from": "gpt",
                    "value": json.dumps({
                        "so_cccd": "001204012345",
                        "ho_va_ten": "NGUYỄN VĂN TEST",
                        "ngay_sinh": "01/01/1990",
                        "gioi_tinh": "Nam",
                        "quoc_tich": "Việt Nam",
                        "que_quan": "Xã Tân Hưng, Huyện Tân Châu, Tỉnh Tây Ninh",
                        "noi_thuong_tru": "123 Đường Lê Lợi, Phường Bến Nghé, Quận 1, TP.HCM",
                        "ngay_het_han": "01/01/2035",
                        "dac_diem_nhan_dang": None,
                        "mat_the": "truoc",
                    }, ensure_ascii=False),
                },
            ],
            "_meta": {"parse_ok": True, "raw_output": "..."},
        },
        # Record lỗi để test validator
        {
            "image": str(img_path),
            "conversations": [
                {"from": "human", "value": "<image>\nprompt..."},
                {
                    "from": "gpt",
                    "value": json.dumps({
                        "so_cccd": "001204099999",
                        "ho_va_ten": "TRẦN THỊ B",
                        "ngay_sinh": "15/08/1985",
                        "gioi_tinh": "Nữ",
                        "quoc_tich": "Việt Nam",
                        "que_quan": "Hà Nội",
                        "noi_thuong_tru": "456 Đường XYZ, Hà Nội",
                        "ngay_het_han": None,
                        "dac_diem_nhan_dang": "Sẹo trên trán",
                        "mat_the": "sau",
                    }, ensure_ascii=False),
                },
            ],
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
    parser.add_argument("--model_name", default="Qwen/Qwen3-VL-8B-Instruct")
    parser.add_argument(
        "--skip_inference", action="store_true",
        help="Bỏ qua bước load model/inference, chỉ test env + format validation"
    )
    parser.add_argument(
        "--validate_file",
        help="Validate 1 file JSONL có sẵn (bỏ qua inference)"
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  CCCD Labeler - Local Test")
    print("="*60)

    # Bước 1: Check env
    env_ok = check_environment()

    tmp_dir = Path(tempfile.mkdtemp(prefix="cccd_test_"))
    print(f"\n  Thư mục tạm: {tmp_dir}")

    # Nếu validate file có sẵn
    if args.validate_file:
        validate_jsonl_format(args.validate_file)
        return

    if args.skip_inference:
        # Tạo mock JSONL và validate
        print(f"\n{'='*60}")
        print("BƯỚC 2: Tạo JSONL mẫu (skip inference)")
        print("="*60)
        mock_path = str(tmp_dir / "mock_labels.jsonl")
        create_mock_jsonl(mock_path, tmp_dir)
        print(f"  Tạo mock JSONL: {mock_path}")
        validate_jsonl_format(mock_path)
    else:
        if not env_ok:
            print("\n[✗] Môi trường chưa đủ, fix lỗi trên trước khi chạy inference!")
            print("    Hoặc chạy: python test_local.py --skip_inference")
            return

        out_file = run_inference_test(args.model_name, tmp_dir)
        if out_file:
            validate_jsonl_format(out_file)

    print(f"\n{'='*60}")
    print("  Test hoàn tất!")
    if args.skip_inference:
        print("  → Chạy lại không có --skip_inference để test inference thật")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
