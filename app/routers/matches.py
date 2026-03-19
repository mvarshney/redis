import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_db, fetch_one, execute_returning
from app.redis_client import get_redis
from app.modules.matchmaking import MatchmakingQueue
from app.modules.leaderboard import Leaderboard
from app.modules.profile_cache import ProfileCache
from app.modules.event_stream import EventStream
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/matches", tags=["matches"])

SCORE_WIN = 100
SCORE_LOSS = -50


class CompleteMatchRequest(BaseModel):
    winner_id: int


@router.get("/queue/depth")
def queue_depth():
    r = get_redis()
    queue = MatchmakingQueue(r)
    return {"depth": queue.depth()}


@router.get("/{match_id}")
def get_match(match_id: int):
    match = fetch_one(
        "SELECT id, player1_id, player2_id, winner_id, status, created_at, completed_at "
        "FROM matches WHERE id = %s",
        (match_id,),
    )
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    return match


@router.post("/{match_id}/complete")
def complete_match(match_id: int, body: CompleteMatchRequest):
    r = get_redis()
    db = get_db()

    match = fetch_one("SELECT * FROM matches WHERE id = %s", (match_id,))
    if match is None:
        raise HTTPException(status_code=404, detail="Match not found")
    if match["status"] != "pending":
        raise HTTPException(status_code=409, detail="Match already completed")

    winner_id = body.winner_id
    if winner_id not in (match["player1_id"], match["player2_id"]):
        raise HTTPException(status_code=400, detail="winner_id must be one of the match players")

    loser_id = match["player2_id"] if winner_id == match["player1_id"] else match["player1_id"]

    # Update match in Postgres
    execute_returning(
        "UPDATE matches SET winner_id = %s, status = 'completed', completed_at = NOW() WHERE id = %s RETURNING id",
        (winner_id, match_id),
    )

    # Update wins/losses
    with db.cursor() as cur:
        cur.execute("UPDATE players SET wins = wins + 1, updated_at = NOW() WHERE id = %s", (winner_id,))
        cur.execute("UPDATE players SET losses = losses + 1, updated_at = NOW() WHERE id = %s", (loser_id,))
    db.commit()

    # Get usernames
    winner = fetch_one("SELECT username, score FROM players WHERE id = %s", (winner_id,))
    loser = fetch_one("SELECT username, score FROM players WHERE id = %s", (loser_id,))

    # Update leaderboard
    lb = Leaderboard(r)
    lb.increment_score(winner["username"], SCORE_WIN)
    lb.increment_score(loser["username"], SCORE_LOSS)

    # Update scores in Postgres and invalidate cache
    cache = ProfileCache(r, db)
    new_winner_score = winner["score"] + SCORE_WIN
    new_loser_score = loser["score"] + SCORE_LOSS
    cache.update(winner_id, {"score": new_winner_score})
    cache.update(loser_id, {"score": new_loser_score})

    # Publish event
    stream = EventStream(r, settings.stream_key)
    stream.publish("match_completed", {
        "match_id": match_id,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "score_delta": SCORE_WIN,
    })

    return {
        "match_id": match_id,
        "winner_id": winner_id,
        "loser_id": loser_id,
        "score_delta": SCORE_WIN,
    }
