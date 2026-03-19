import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.db import get_db, execute_returning, fetch_one
from app.redis_client import get_redis
from app.modules.profile_cache import ProfileCache
from app.modules.leaderboard import Leaderboard
from app.modules.matchmaking import MatchmakingQueue
from app.modules.event_stream import EventStream
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/players", tags=["players"])


class CreatePlayerRequest(BaseModel):
    username: str
    email: str


class UpdateScoreRequest(BaseModel):
    score: int


@router.post("", status_code=201)
def create_player(body: CreatePlayerRequest):
    r = get_redis()
    db = get_db()
    player = execute_returning(
        "INSERT INTO players (username, email) VALUES (%s, %s) RETURNING id, username, email, score, wins, losses, created_at",
        (body.username, body.email),
    )
    if player is None:
        raise HTTPException(status_code=500, detail="Failed to create player")

    # Add to leaderboard with initial score 0
    lb = Leaderboard(r)
    lb.add_or_update(player["username"], player["score"])

    stream = EventStream(r, settings.stream_key)
    logger.info("[PLAYERS] created player_id=%d username=%s", player["id"], player["username"])
    return player


@router.get("/{player_id}")
def get_player(player_id: int):
    r = get_redis()
    db = get_db()
    cache = ProfileCache(r, db)
    player = cache.get(player_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    return player


@router.put("/{player_id}/score")
def update_score(player_id: int, body: UpdateScoreRequest):
    r = get_redis()
    db = get_db()

    # Get current player for old score
    current = fetch_one("SELECT id, username, score FROM players WHERE id = %s", (player_id,))
    if current is None:
        raise HTTPException(status_code=404, detail="Player not found")

    old_score = current["score"]
    new_score = body.score

    cache = ProfileCache(r, db)
    updated = cache.update(player_id, {"score": new_score})

    lb = Leaderboard(r)
    lb.add_or_update(current["username"], new_score)

    stream = EventStream(r, settings.stream_key)
    stream.publish("score_updated", {
        "player_id": player_id,
        "username": current["username"],
        "old_score": old_score,
        "new_score": new_score,
    })

    return updated


@router.post("/{player_id}/queue/join")
def join_queue(player_id: int):
    r = get_redis()
    db = get_db()

    player = fetch_one("SELECT id, username FROM players WHERE id = %s", (player_id,))
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    queue = MatchmakingQueue(r)
    try:
        depth = queue.join(player_id)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    stream = EventStream(r, settings.stream_key)
    stream.publish("player_joined_queue", {
        "player_id": player_id,
        "username": player["username"],
    })

    return {"player_id": player_id, "position": depth, "status": "queued"}


@router.post("/{player_id}/queue/leave")
def leave_queue(player_id: int):
    r = get_redis()
    queue = MatchmakingQueue(r)
    removed = queue.leave(player_id)
    return {"player_id": player_id, "removed": removed}


@router.get("/{player_id}/rank")
def get_rank(player_id: int):
    r = get_redis()
    db = get_db()

    player = fetch_one("SELECT id, username FROM players WHERE id = %s", (player_id,))
    if player is None:
        raise HTTPException(status_code=404, detail="Player not found")

    lb = Leaderboard(r)
    rank_info = lb.get_rank(player["username"])
    if rank_info is None:
        raise HTTPException(status_code=404, detail="Player not on leaderboard")

    neighbours = lb.get_around_player(player["username"], radius=3)
    return {"player": rank_info, "neighbours": neighbours}
