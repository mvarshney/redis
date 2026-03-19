import uuid
import logging
import redis

logger = logging.getLogger(__name__)

_RELEASE_LUA = """
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
else
    return 0
end
"""


class RedisLock:
    def __init__(self, r: redis.Redis, name: str, ttl_seconds: int = 10):
        self.r = r
        self.name = name
        self.ttl_seconds = ttl_seconds
        self._key = f"lock:{name}"
        self._token: str | None = None
        self._release_script = r.register_script(_RELEASE_LUA)

    def acquire(self) -> bool:
        token = str(uuid.uuid4())
        acquired = self.r.set(self._key, token, nx=True, ex=self.ttl_seconds)
        if acquired:
            self._token = token
            logger.debug("[LOCK] acquired key=%s token=%s", self._key, token)
        else:
            logger.debug("[LOCK] failed to acquire key=%s (already held)", self._key)
        return bool(acquired)

    def release(self) -> bool:
        if self._token is None:
            return False
        result = self._release_script(keys=[self._key], args=[self._token])
        released = bool(result)
        if released:
            logger.debug("[LOCK] released key=%s", self._key)
            self._token = None
        else:
            logger.warning("[LOCK] release failed — lock not ours key=%s", self._key)
        return released

    def __enter__(self) -> "RedisLock":
        if not self.acquire():
            raise RuntimeError(f"Could not acquire lock: {self._key}")
        return self

    def __exit__(self, *args):
        self.release()


class LockManager:
    def __init__(self, r: redis.Redis):
        self.r = r

    def lock(self, name: str, ttl_seconds: int = 10) -> RedisLock:
        return RedisLock(self.r, name, ttl_seconds)
