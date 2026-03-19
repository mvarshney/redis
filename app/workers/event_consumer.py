"""
Event consumer worker — run as: python -m app.workers.event_consumer
Reads from the Redis Stream using a consumer group and dispatches events.
"""
import logging
import signal
import socket

from app.config import settings
from app.redis_client import get_redis
from app.db import get_db
from app.modules.event_stream import EventStream
from app.modules.leaderboard import Leaderboard
from app.modules.profile_cache import ProfileCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

running = True
CONSUMER_NAME = f"consumer-{socket.gethostname()}"


def handle_signal(signum, frame):
    global running
    logger.info("[EVENT_CONSUMER] received signal %d — shutting down", signum)
    running = False


def on_player_joined_queue(data: dict):
    logger.info(
        "[EVENT_CONSUMER] player_joined_queue player_id=%s username=%s",
        data.get("player_id"), data.get("username"),
    )


def on_match_created(data: dict):
    logger.info(
        "[EVENT_CONSUMER] match_created match_id=%s player1_id=%s player2_id=%s",
        data.get("match_id"), data.get("player1_id"), data.get("player2_id"),
    )


def on_match_completed(data: dict, leaderboard: Leaderboard, profile_cache: ProfileCache):
    match_id = data.get("match_id")
    winner_id = data.get("winner_id")
    loser_id = data.get("loser_id")
    score_delta = int(data.get("score_delta", 0))
    logger.info(
        "[EVENT_CONSUMER] match_completed match_id=%s winner_id=%s loser_id=%s score_delta=%d",
        match_id, winner_id, loser_id, score_delta,
    )
    # Update leaderboard scores based on event data (username needed — look up from cache)
    # The score update event will handle profile cache invalidation


def on_score_updated(data: dict, profile_cache: ProfileCache):
    player_id = data.get("player_id")
    logger.info(
        "[EVENT_CONSUMER] score_updated player_id=%s username=%s old=%s new=%s",
        player_id, data.get("username"), data.get("old_score"), data.get("new_score"),
    )
    if player_id:
        profile_cache.invalidate(int(player_id))


def process_messages(messages, r, leaderboard: Leaderboard, profile_cache: ProfileCache):
    for stream_key, entries in messages:
        for entry_id, data in entries:
            event_type = data.get("event_type", "unknown")
            try:
                if event_type == "player_joined_queue":
                    on_player_joined_queue(data)
                elif event_type == "match_created":
                    on_match_created(data)
                elif event_type == "match_completed":
                    on_match_completed(data, leaderboard, profile_cache)
                elif event_type == "score_updated":
                    on_score_updated(data, profile_cache)
                else:
                    logger.warning("[EVENT_CONSUMER] unknown event_type=%s id=%s", event_type, entry_id)

                r.xack(settings.stream_key, settings.consumer_group, entry_id)
                logger.debug("[EVENT_CONSUMER] acked id=%s", entry_id)
            except Exception as e:
                logger.error("[EVENT_CONSUMER] error processing id=%s: %s", entry_id, e)


def claim_pending(r, leaderboard: Leaderboard, profile_cache: ProfileCache):
    """Process any pending (unacknowledged) messages from before crash."""
    try:
        pending = r.xpending_range(
            settings.stream_key,
            settings.consumer_group,
            min="-",
            max="+",
            count=100,
        )
        if not pending:
            return
        ids = [p["message_id"] for p in pending]
        claimed = r.xclaim(
            settings.stream_key,
            settings.consumer_group,
            CONSUMER_NAME,
            min_idle_time=0,
            message_ids=ids,
        )
        if claimed:
            logger.info("[EVENT_CONSUMER] claiming %d pending messages", len(claimed))
            process_messages([(settings.stream_key, claimed)], r, leaderboard, profile_cache)
    except Exception as e:
        logger.error("[EVENT_CONSUMER] error claiming pending: %s", e)


def main():
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    r = get_redis()
    db = get_db()
    stream = EventStream(r, settings.stream_key)
    stream.ensure_consumer_group(settings.consumer_group)
    leaderboard = Leaderboard(r)
    profile_cache = ProfileCache(r, db)

    logger.info("[EVENT_CONSUMER] started consumer=%s", CONSUMER_NAME)

    # Process any pending messages from before restart
    claim_pending(r, leaderboard, profile_cache)

    while running:
        try:
            messages = r.xreadgroup(
                groupname=settings.consumer_group,
                consumername=CONSUMER_NAME,
                streams={settings.stream_key: ">"},
                count=10,
                block=2000,
            )
            if not messages:
                continue
            process_messages(messages, r, leaderboard, profile_cache)
        except Exception as e:
            if running:
                logger.error("[EVENT_CONSUMER] read error: %s", e)

    logger.info("[EVENT_CONSUMER] exited cleanly")


if __name__ == "__main__":
    main()
