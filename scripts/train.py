"""
Shim tương thích ngược — KHÔNG chứa mã nguồn.

Script thật nằm ở **model/scripts/** (cùng tên file) — sửa code ở đó.
File này chỉ chuyển tiếp nguyên vẹn tham số dòng lệnh, để lệnh cũ vẫn chạy:

    python scripts/train.py --train_jsonl ... --output_dir ...

Notebook Colab 02–05 gọi theo đường `scripts/*.py` nên không phải sửa gì.
"""

import runpy
import sys
from pathlib import Path

_real = Path(__file__).resolve().parent.parent / "model" / "scripts" / Path(__file__).name
if not _real.exists():
    raise SystemExit(f"Không tìm thấy script thật: {_real}")

sys.argv[0] = str(_real)
runpy.run_path(str(_real), run_name="__main__")
