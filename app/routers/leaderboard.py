import logging
from fastapi import APIRouter, HTTPException, Query

from app.redis_client import get_redis
from app.modules.leaderboard import Leaderboard

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leaderboard", tags=["leaderboard"])


@router.get("/top")
def get_top(n: int = Query(default=10, ge=1, le=100)):
    r = get_redis()
    lb = Leaderboard(r)
    return lb.get_top(n)


@router.get("/around/{player_id}")
def get_around(player_id: int, radius: int = Query(default=3, ge=1, le=20)):
    from app.db import fetch_one
    r = get_redis()
    db_player = fetch_one("SELECT username FROM players WHERE id = %s", (player_id,))
    if db_player is None:
        raise HTTPException(status_code=404, detail="Player not found")
    lb = Leaderboard(r)
    return lb.get_around_player(db_player["username"], radius=radius)
