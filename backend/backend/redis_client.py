"""
redis_client.py
===============
Kết nối Redis + thao tác blacklist token.

Dùng để:
  - Vô hiệu hóa access token đã logout bằng jti (TTL = thời gian còn lại).
  - (P4) hàng đợi công việc batch.

Redis không có sẵn thì hệ thống VẪN chạy (blacklist bỏ qua) — ghi log cảnh báo
thay vì crash, giúp máy dev không có Redis vẫn test được auth.
"""

from __future__ import annotations

import logging
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError

from . import config

logger = logging.getLogger(__name__)

_client: Optional[Redis] = None

# Prefix key blacklist; TTL tính bằng giây.
BLACKLIST_PREFIX = "cccd:blacklist:jti:"


def get_redis() -> Optional[Redis]:
    """Trả client Redis (lười khởi tạo), hoặc None nếu không kết nối được."""
    global _client
    if _client is not None:
        return _client
    try:
        # protocol=2: tránh lệnh HELLO (RESP3) — Redis bản Windows cũ (3.x)
        # không hỗ trợ; redis-py 8 mặc định protocol=3.
        _client = Redis.from_url(config.REDIS_URL, decode_responses=True, protocol=2)
        _client.ping()
        logger.info("✓ Redis sẵn sàng (%s)", config.REDIS_URL)
    except RedisError as exc:
        logger.warning("Không kết nối được Redis (%s) → blacklist token bị bỏ qua: %s",
                       config.REDIS_URL, exc)
        _client = None
    return _client


def blacklist_jti(jti: str, ttl_seconds: int) -> bool:
    """Đưa jti của access token vào blacklist trong `ttl_seconds` giây."""
    client = get_redis()
    if client is None:
        return False
    try:
        client.setex(f"{BLACKLIST_PREFIX}{jti}", ttl_seconds, "1")
        return True
    except RedisError as exc:
        logger.warning("Redis blacklist thất bại: %s", exc)
        return False


def is_blacklisted(jti: str) -> bool:
    """Access token có nằm trong blacklist không (đã logout)?"""
    client = get_redis()
    if client is None:
        return False
    try:
        return client.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
    except RedisError:
        return False