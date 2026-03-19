"""
Matchmaker worker — run as: python -m app.workers.matchmaker
Blocks on the matchmaking queue and creates matches when two players are available.
"""
import logging
import signal
import sys
import time

import psycopg2

from app.config import settings
from app.redis_client import get_redis
from app.db import get_db
from app.modules.distributed_lock import LockManager
from app.modules.event_stream import EventStream

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

QUEUE_KEY = "queue:matchmaking"
MEMBERS_KEY = "queue:matchmaking:members"

running = True


def handle_signal(signum, frame):
    global running
    logger.info("[MATCHMAKER] received signal %d — shutting down", signum)
    running = False


def create_match(db, p1_id: int, p2_id: int) -> int:
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO matches (player1_id, player2_id, status) VALUES (%s, %s, 'pending') RETURNING id",
            (p1_id, p2_id),
        )
        match_id = cur.fetchone()[0]
    db.commit()
    return match_id


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    r = get_redis()
    db = get_db()
    lock_manager = LockManager(r)
    stream = EventStream(r, settings.stream_key)
    stream.ensure_consumer_group(settings.consumer_group)

    timeout = settings.matchmaker_poll_timeout_seconds
    logger.info("[MATCHMAKER] started — polling queue with timeout=%ds", timeout)

    while running:
        try:
            result = r.blpop(QUEUE_KEY, timeout=timeout)
            if result is None:
                continue

            _, p1_str = result
            p1_id = int(p1_str)
            logger.info("[MATCHMAKER] popped player1_id=%d — waiting for player2", p1_id)

            # Try to get a second player
            result2 = r.blpop(QUEUE_KEY, timeout=timeout)
            if result2 is None:
                # No second player — push p1 back and wait
                logger.info("[MATCHMAKER] no second player — returning player1_id=%d to queue", p1_id)
                r.lpush(QUEUE_KEY, str(p1_id))
                continue

            _, p2_str = result2
            p2_id = int(p2_str)
            logger.info("[MATCHMAKER] matched player1_id=%d player2_id=%d", p1_id, p2_id)

            lock_name = f"match:{min(p1_id, p2_id)}:{max(p1_id, p2_id)}"
            lock = lock_manager.lock(lock_name, ttl_seconds=settings.match_lock_ttl_seconds)

            if not lock.acquire():
                logger.warning("[MATCHMAKER] could not acquire lock=%s — skipping", lock_name)
                continue

            try:
                match_id = create_match(db, p1_id, p2_id)
                # Remove from members tracking set
                r.srem(MEMBERS_KEY, str(p1_id), str(p2_id))

                stream.publish("match_created", {
                    "match_id": match_id,
                    "player1_id": p1_id,
                    "player2_id": p2_id,
                })
                logger.info(
                    "[MATCHMAKER] match_id=%d created player1_id=%d player2_id=%d",
                    match_id, p1_id, p2_id,
                )
            finally:
                lock.release()

        except psycopg2.Error as e:
            logger.error("[MATCHMAKER] DB error: %s", e)
            try:
                db.rollback()
            except Exception:
                pass
            time.sleep(1)
        except Exception as e:
            logger.error("[MATCHMAKER] unexpected error: %s", e)
            time.sleep(1)

    logger.info("[MATCHMAKER] exited cleanly")


if __name__ == "__main__":
    main()
