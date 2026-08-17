"""
Shim tương thích ngược — KHÔNG chứa mã nguồn.

Service FastAPI đã chuyển sang **backend/** — sửa code ở đó.

File này trỏ `__path__` của package `app` sang `backend/`, để các lệnh cũ vẫn chạy:

    uvicorn app.main:app --port 8000          # notebook 04_deployment
    from app import main as serving           # model/scripts/benchmark.py

Lưu ý: chỉ dùng MỘT trong hai tên (`app.main` hoặc `backend.main`) trong cùng một
tiến trình. Import cả hai sẽ tạo hai module riêng biệt ⇒ nạp model 4-bit hai lần
và ngốn gấp đôi VRAM.
"""

from pathlib import Path

__path__ = [str(Path(__file__).resolve().parent.parent / "backend")]
