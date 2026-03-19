import logging
import redis

logger = logging.getLogger(__name__)

LEADERBOARD_KEY = "leaderboard:global"


class Leaderboard:
    def __init__(self, r: redis.Redis):
        self.r = r

    def add_or_update(self, username: str, score: float) -> None:
        try:
            self.r.zadd(LEADERBOARD_KEY, {username: score})
            logger.debug("[LEADERBOARD] add_or_update username=%s score=%s", username, score)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise

    def get_rank(self, username: str) -> dict | None:
        try:
            rank = self.r.zrevrank(LEADERBOARD_KEY, username)
            if rank is None:
                return None
            score = self.r.zscore(LEADERBOARD_KEY, username)
            return {"username": username, "score": int(score), "rank": rank + 1}
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise

    def get_top(self, n: int) -> list[dict]:
        try:
            entries = self.r.zrevrange(LEADERBOARD_KEY, 0, n - 1, withscores=True)
            return [
                {"rank": i + 1, "username": username, "score": int(score)}
                for i, (username, score) in enumerate(entries)
            ]
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise

    def get_around_player(self, username: str, radius: int = 3) -> list[dict]:
        try:
            rank = self.r.zrevrank(LEADERBOARD_KEY, username)
            if rank is None:
                return []
            start = max(0, rank - radius)
            stop = rank + radius
            entries = self.r.zrevrange(LEADERBOARD_KEY, start, stop, withscores=True)
            return [
                {"rank": start + i + 1, "username": u, "score": int(s)}
                for i, (u, s) in enumerate(entries)
            ]
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise

    def increment_score(self, username: str, delta: float) -> float:
        try:
            new_score = self.r.zincrby(LEADERBOARD_KEY, delta, username)
            logger.debug("[LEADERBOARD] increment username=%s delta=%s new_score=%s", username, delta, new_score)
            return float(new_score)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise

    def remove_player(self, username: str) -> None:
        try:
            self.r.zrem(LEADERBOARD_KEY, username)
            logger.debug("[LEADERBOARD] remove username=%s", username)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[LEADERBOARD] Redis error: %s", e)
            raise
