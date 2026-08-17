"""
Shim tương thích ngược — KHÔNG chứa mã nguồn.

Codebase đã tách thành ba phần: `frontend/` · `backend/` · `model/`.
Mã nguồn thật của package này nằm ở **model/src/** — sửa code ở đó.

File này chỉ trỏ `__path__` của package `src` sang `model/src`, để mọi lệnh và
mọi import cũ vẫn chạy nguyên vẹn sau khi tái cấu trúc:

    python -m src.data_pipeline.auto_label ...
    python -m src.models.vlm_registry --model internvl --image ...
    from src.utils.cccd_schema import SYSTEM_PROMPT

Notebook Colab 01–05 đang import theo đường `src.*` nên không phải sửa gì.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "model" / "src")]
