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
import time
from typing import Optional

from redis import Redis
from redis.exceptions import RedisError

from . import config

logger = logging.getLogger(__name__)

_client: Optional[Redis] = None
# Thời điểm (time.monotonic) lần kết nối/lệnh Redis thất bại gần nhất. Trong
# REDIS_RETRY_SECONDS giây sau đó get_redis() trả None ngay, không thử lại
# (DEF-08: Redis tắt không làm mỗi request chậm vài giây).
_last_failure: Optional[float] = None

# Timeout ngắn (giây) cho kết nối và từng lệnh Redis.
_SOCKET_TIMEOUT = 0.5

# Prefix key blacklist; TTL tính bằng giây.
BLACKLIST_PREFIX = "cccd:blacklist:jti:"


def _mark_failed() -> None:
    """Bỏ client hiện tại + ghi thời điểm lỗi để tạm ngưng thử lại."""
    global _client, _last_failure
    _client = None
    _last_failure = time.monotonic()


def get_redis() -> Optional[Redis]:
    """Trả client Redis (lười khởi tạo), hoặc None nếu không kết nối được."""
    global _client, _last_failure
    if _client is not None:
        return _client
    if (_last_failure is not None
            and time.monotonic() - _last_failure < config.REDIS_RETRY_SECONDS):
        return None
    try:
        # protocol=2: tránh lệnh HELLO (RESP3) — Redis bản Windows cũ (3.x)
        # không hỗ trợ; redis-py 8 mặc định protocol=3.
        client = Redis.from_url(
            config.REDIS_URL,
            decode_responses=True,
            protocol=2,
            socket_connect_timeout=_SOCKET_TIMEOUT,
            socket_timeout=_SOCKET_TIMEOUT,
        )
        client.ping()
        _client = client
        _last_failure = None
        logger.info("✓ Redis sẵn sàng (%s)", config.REDIS_URL)
    except RedisError as exc:
        logger.warning("Không kết nối được Redis (%s) → blacklist token bị bỏ qua "
                       "(thử lại sau %ss): %s",
                       config.REDIS_URL, config.REDIS_RETRY_SECONDS, exc)
        _mark_failed()
    return _client


def ping() -> bool:
    """Redis còn trả lời không (dùng cho /health; không chờ lâu khi Redis tắt)."""
    client = get_redis()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except RedisError as exc:
        logger.warning("Redis ping thất bại: %s", exc)
        _mark_failed()
        return False


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
        _mark_failed()
        return False


def is_blacklisted(jti: str) -> bool:
    """Access token có nằm trong blacklist không (đã logout)?

    Fail-open: Redis lỗi → coi như chưa bị blacklist (không chặn request)."""
    client = get_redis()
    if client is None:
        return False
    try:
        return client.exists(f"{BLACKLIST_PREFIX}{jti}") == 1
    except RedisError as exc:
        logger.warning("Redis kiểm tra blacklist thất bại: %s", exc)
        _mark_failed()
        return False