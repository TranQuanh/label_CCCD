"""
db.py
=====
Kết nối PostgreSQL (psycopg3) + khởi tạo lược đồ từ `schema.sql`.

Dùng `psycopg_pool.ConnectionPool` để các endpoint chạy trong threadpool của
FastAPI có thể mở kết nối riêng (kết nối psycopg không an toàn khi dùng chung
giữa các thread cùng lúc).

Hàm public:
  init_db()          — chạy schema.sql (idempotent) + seed
  get_conn()         — lấy kết nối từ pool (trả về khi xong bằng context manager)
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from psycopg import Connection, sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from . import config

logger = logging.getLogger(__name__)

_pool: Optional[ConnectionPool] = None

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def init_db() -> None:
    """Khởi tạo pool + chạy schema.sql (an toàn khi gọi lại nhiều lần)."""
    global _pool
    if _pool is not None:
        return
    _pool = ConnectionPool(
        config.DATABASE_URL,
        min_size=1,
        max_size=8,
        open=False,          # chưa mở cho tới khi server sẵn sàng
        kwargs={"row_factory": dict_row},
    )
    _pool.open()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with _pool.connection() as conn:
        conn.execute(schema)
        conn.commit()
    logger.info("✓ DB sẵn sàng (schema + seed đã áp dụng)")


def close_db() -> None:
    """Đóng pool khi server tắt."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


@contextmanager
def get_conn() -> Iterator[Connection]:
    """Kết nối dùng chung cho mọi truy vấn (tự trả về pool sau khi thoát)."""
    if _pool is None:
        raise RuntimeError("Chưa gọi init_db() — DB chưa sẵn sàng")
    with _pool.connection() as conn:
        yield conn


def ping() -> bool:
    """Kiểm tra nhanh DB có kết nối được không (dùng cho /health)."""
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("DB ping thất bại: %s", exc)
        return False


def fetch_one(query: sql.Composed | str, params=None) -> Optional[dict]:
    """Truy vấn trả về 1 dòng dict (hoặc None)."""
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchone()


def fetch_all(query: sql.Composed | str, params=None) -> list[dict]:
    """Truy vấn trả về nhiều dòng dict."""
    with get_conn() as conn:
        cur = conn.execute(query, params)
        return cur.fetchall()


def execute(query: sql.Composed | str, params=None) -> None:
    """Truy vấn ghi (INSERT/UPDATE/DELETE), tự commit."""
    with get_conn() as conn:
        conn.execute(query, params)
        conn.commit()