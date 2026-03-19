import time
import logging
import redis

logger = logging.getLogger(__name__)


class EventStream:
    def __init__(self, r: redis.Redis, stream_key: str):
        self.r = r
        self.stream_key = stream_key

    def publish(self, event_type: str, data: dict) -> str:
        message = {
            "event_type": event_type,
            "timestamp": str(int(time.time() * 1000)),
            **{k: str(v) for k, v in data.items()},
        }
        try:
            entry_id = self.r.xadd(self.stream_key, message)
            logger.info("[STREAM] published event_type=%s id=%s", event_type, entry_id)
            return entry_id
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[STREAM] publish error: %s", e)
            raise

    def ensure_consumer_group(self, group: str) -> None:
        try:
            self.r.xgroup_create(self.stream_key, group, id="$", mkstream=True)
            logger.info("[STREAM] consumer group created group=%s", group)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.debug("[STREAM] consumer group already exists group=%s", group)
            else:
                raise
