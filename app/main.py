import logging
import time
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.config import settings
from app.redis_client import get_redis
from app.db import get_db, fetch_all
from app.modules.rate_limiter import RateLimiter
from app.routers import players, leaderboard, matches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Redis Gaming Backend", version="1.0.0")

# Mount routers
app.include_router(players.router)
app.include_router(leaderboard.router)
app.include_router(matches.router)


# ── Rate limiting middleware ──────────────────────────────────────────────────

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    # Skip health endpoint
    if request.url.path in ("/health", "/debug/redis-keys"):
        return await call_next(request)

    player_id = request.headers.get("X-Player-ID") or request.client.host

    try:
        r = get_redis()
        limiter = RateLimiter(r, settings.rate_limit_requests, settings.rate_limit_window_seconds)
        allowed, count, retry_after = limiter.is_allowed(player_id)
    except Exception as e:
        logger.error("Rate limiter error: %s", e)
        return await call_next(request)

    remaining = max(0, settings.rate_limit_requests - count)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "code": "RATE_LIMIT_EXCEEDED"},
            headers={
                "X-RateLimit-Limit": str(settings.rate_limit_requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(retry_after),
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Limit"] = str(settings.rate_limit_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return response


# ── System endpoints ──────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health():
    status = {"redis": "ok", "postgres": "ok", "stream": {}}

    # Redis check
    try:
        r = get_redis()
        r.ping()
        info = r.xinfo_stream(settings.stream_key) if r.exists(settings.stream_key) else {}
        status["stream"] = {
            "length": info.get("length", 0) if info else 0,
            "key": settings.stream_key,
        }
    except Exception as e:
        status["redis"] = f"error: {e}"

    # Postgres check
    try:
        db = get_db()
        with db.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception as e:
        status["postgres"] = f"error: {e}"

    http_status = 200 if status["redis"] == "ok" and status["postgres"] == "ok" else 503
    return JSONResponse(content=status, status_code=http_status)


@app.get("/debug/redis-keys", tags=["system"])
def debug_redis_keys():
    r = get_redis()
    patterns = [
        "ratelimit:*",
        "leaderboard:*",
        "player:*",
        "queue:*",
        "lock:*",
        "stream:*",
    ]
    result = {}
    for pattern in patterns:
        keys = r.keys(pattern)
        for key in keys:
            try:
                key_type = r.type(key)
                result[key] = key_type
            except Exception:
                result[key] = "unknown"
    return result
