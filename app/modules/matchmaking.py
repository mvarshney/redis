import logging
import redis

logger = logging.getLogger(__name__)

QUEUE_KEY = "queue:matchmaking"
MEMBERS_KEY = "queue:matchmaking:members"


class MatchmakingQueue:
    def __init__(self, r: redis.Redis):
        self.r = r

    def join(self, player_id: int) -> int:
        if self.is_queued(player_id):
            raise ValueError(f"Player {player_id} is already in the queue")
        pipe = self.r.pipeline()
        pipe.rpush(QUEUE_KEY, str(player_id))
        pipe.sadd(MEMBERS_KEY, str(player_id))
        results = pipe.execute()
        queue_len = results[0]
        logger.info("[MATCHMAKING] player_id=%d joined queue depth=%d", player_id, queue_len)
        return queue_len

    def leave(self, player_id: int) -> bool:
        pipe = self.r.pipeline()
        pipe.lrem(QUEUE_KEY, 1, str(player_id))
        pipe.srem(MEMBERS_KEY, str(player_id))
        results = pipe.execute()
        removed = results[0] > 0
        logger.info("[MATCHMAKING] player_id=%d left queue removed=%s", player_id, removed)
        return removed

    def depth(self) -> int:
        return self.r.llen(QUEUE_KEY)

    def is_queued(self, player_id: int) -> bool:
        return bool(self.r.sismember(MEMBERS_KEY, str(player_id)))
