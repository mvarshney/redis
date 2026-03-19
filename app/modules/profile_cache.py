import logging
import redis

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 minutes


class ProfileCache:
    def __init__(self, r: redis.Redis, db_conn):
        self.r = r
        self.db = db_conn

    def _key(self, player_id: int) -> str:
        return f"player:{player_id}"

    def _deserialize(self, raw: dict) -> dict:
        return {
            "id": int(raw["id"]),
            "username": raw["username"],
            "email": raw["email"],
            "score": int(raw["score"]),
            "wins": int(raw["wins"]),
            "losses": int(raw["losses"]),
            "created_at": raw["created_at"],
        }

    def _fetch_from_db(self, player_id: int) -> dict | None:
        import psycopg2.extras
        with self.db.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, username, email, score, wins, losses, created_at "
                "FROM players WHERE id = %s",
                (player_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get(self, player_id: int) -> dict | None:
        key = self._key(player_id)
        try:
            raw = self.r.hgetall(key)
            if raw:
                logger.debug("[PROFILE_CACHE] hit player_id=%d", player_id)
                self.r.expire(key, CACHE_TTL)
                return self._deserialize(raw)

            logger.debug("[PROFILE_CACHE] miss player_id=%d — fetching from DB", player_id)
            player = self._fetch_from_db(player_id)
            if player is None:
                return None

            mapping = {k: str(v) for k, v in player.items()}
            self.r.hset(key, mapping=mapping)
            self.r.expire(key, CACHE_TTL)
            return self._deserialize(mapping)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[PROFILE_CACHE] Redis error: %s", e)
            return self._fetch_from_db(player_id)

    def invalidate(self, player_id: int) -> None:
        key = self._key(player_id)
        try:
            self.r.delete(key)
            logger.debug("[PROFILE_CACHE] invalidated player_id=%d", player_id)
        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error("[PROFILE_CACHE] Redis error on invalidate: %s", e)

    def update(self, player_id: int, fields: dict) -> dict:
        set_clauses = ", ".join(f"{k} = %s" for k in fields)
        values = list(fields.values()) + [player_id]
        with self.db.cursor() as cur:
            cur.execute(
                f"UPDATE players SET {set_clauses}, updated_at = NOW() WHERE id = %s",
                values,
            )
        self.db.commit()
        self.invalidate(player_id)
        return self.get(player_id)
