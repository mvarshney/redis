import time
import uuid
import logging
import redis

logger = logging.getLogger(__name__)

_SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local req_id = ARGV[4]
local ttl_seconds = tonumber(ARGV[5])

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window_ms)

-- Add current request
redis.call('ZADD', key, now, req_id)

-- Set TTL so key auto-cleans
redis.call('EXPIRE', key, ttl_seconds)

-- Return current count
return redis.call('ZCARD', key)
"""


class RateLimiter:
    def __init__(self, r: redis.Redis, limit: int, window_seconds: int):
        self.r = r
        self.limit = limit
        self.window_seconds = window_seconds
        self.window_ms = window_seconds * 1000
        self._script = r.register_script(_SLIDING_WINDOW_LUA)

    def is_allowed(self, player_id: str) -> tuple[bool, int, int]:
        key = f"ratelimit:{player_id}"
        now_ms = int(time.time() * 1000)
        req_id = str(uuid.uuid4())

        try:
            count = self._script(
                keys=[key],
                args=[now_ms, self.window_ms, self.limit, req_id, self.window_seconds],
            )
            count = int(count)
            allowed = count <= self.limit
            retry_after = self.window_seconds if not allowed else 0
            logger.debug(
                "[RATE_LIMITER] check player_id=%s count=%d limit=%d allowed=%s",
                player_id, count, self.limit, allowed,
            )
            return allowed, count, retry_after
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[RATE_LIMITER] Redis error: %s", e)
            # Fail open on Redis error
            return True, 0, 0
