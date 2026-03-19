# Redis Gaming Backend — Claude Code Build Instructions

## Overview

Build a multiplayer game backend that demonstrates six core Redis capabilities,
deployed with Docker Compose on a single machine. The system simulates the
backend infrastructure used by big tech gaming companies.

The six Redis capabilities to implement:

| Module | Redis structure | Use case |
|---|---|---|
| Rate limiter | ZSet (sliding window) | API gateway — per-player request throttling |
| Leaderboard | ZSet | Global ranked leaderboard with neighbour lookup |
| Player profile cache | Hash + TTL | Cache-aside in front of Postgres |
| Matchmaking queue | List | FIFO job queue with blocking worker |
| Distributed lock | String NX+EX | Prevent duplicate match creation |
| Game event stream | Stream + consumer group | Fan-out events to multiple services |

---

## Technology Stack

- **Language**: Python 3.11
- **Redis client**: `redis-py` (synchronous)
- **Database**: PostgreSQL 15 (source of truth for player profiles and matches)
- **HTTP framework**: FastAPI
- **Deployment**: Docker Compose (single machine)
- **Testing**: pytest

---

## Project Structure to Create

```
redis-gaming-backend/
├── docker-compose.yml
├── .env
├── README.md
├── requirements.txt
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app, mounts all routers
│   ├── config.py                # Settings from environment variables
│   ├── db.py                    # Postgres connection (psycopg2)
│   ├── redis_client.py          # Redis connection singleton
│   │
│   ├── modules/
│   │   ├── __init__.py
│   │   ├── rate_limiter.py      # Module 1
│   │   ├── leaderboard.py       # Module 2
│   │   ├── profile_cache.py     # Module 3
│   │   ├── matchmaking.py       # Module 4
│   │   ├── distributed_lock.py  # Module 5
│   │   └── event_stream.py      # Module 6
│   │
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── players.py           # Player CRUD + profile endpoints
│   │   ├── leaderboard.py       # Leaderboard endpoints
│   │   └── matches.py           # Match creation + matchmaking endpoints
│   │
│   └── workers/
│       ├── __init__.py
│       ├── matchmaker.py        # Blocking BRPOP worker process
│       └── event_consumer.py    # Stream consumer group worker process
│
├── db/
│   └── init.sql                 # Postgres schema + seed data
│
├── scripts/
│   ├── seed_leaderboard.py      # Populate leaderboard with test data
│   └── load_test.py             # Simple load test to trigger rate limiting
│
└── tests/
    ├── conftest.py
    ├── test_rate_limiter.py
    ├── test_leaderboard.py
    ├── test_profile_cache.py
    ├── test_matchmaking.py
    ├── test_distributed_lock.py
    └── test_event_stream.py
```

---

## Docker Compose Configuration

Create `docker-compose.yml` with these services:

### Services

**redis**
- Image: `redis:7.2-alpine`
- Port: `6379:6379`
- Command: `redis-server --appendonly yes --appendfsync everysec`
  (AOF persistence enabled — survives container restart)
- Volume: `redis_data:/data`
- Healthcheck: `redis-cli ping`

**postgres**
- Image: `postgres:15-alpine`
- Port: `5432:5432`
- Environment: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` from `.env`
- Volume: `postgres_data:/var/lib/postgresql/data`
- Mount: `./db/init.sql:/docker-entrypoint-initdb.d/init.sql`
- Healthcheck: `pg_isready`

**api**
- Build: `.` (Dockerfile in root)
- Port: `8000:8000`
- Command: `uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`
- Depends on: redis (healthy), postgres (healthy)
- Environment: from `.env`
- Volume: `.:/app` (for --reload to work in dev)

**matchmaker** (worker process)
- Build: `.` (same image as api)
- Command: `python -m app.workers.matchmaker`
- Depends on: redis (healthy), postgres (healthy)
- Restart: `unless-stopped`

**event-consumer** (worker process)
- Build: `.` (same image as api)
- Command: `python -m app.workers.event_consumer`
- Depends on: redis (healthy)
- Restart: `unless-stopped`

### Volumes
- `redis_data`
- `postgres_data`

---

## Environment Variables (.env)

```
REDIS_URL=redis://redis:6379/0
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=gamedb
POSTGRES_USER=gameuser
POSTGRES_PASSWORD=gamepass
POSTGRES_URL=postgresql://gameuser:gamepass@postgres:5432/gamedb

# Rate limiter config
RATE_LIMIT_REQUESTS=20
RATE_LIMIT_WINDOW_SECONDS=60

# Matchmaking config
MATCH_LOCK_TTL_SECONDS=10
MATCHMAKER_POLL_TIMEOUT_SECONDS=5

# Stream config
STREAM_KEY=stream:game-events
CONSUMER_GROUP=game-services
```

---

## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
```

---

## Requirements

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
redis==5.0.4
psycopg2-binary==2.9.9
pydantic-settings==2.2.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

---

## Database Schema (db/init.sql)

```sql
CREATE TABLE IF NOT EXISTS players (
    id          SERIAL PRIMARY KEY,
    username    VARCHAR(50) UNIQUE NOT NULL,
    email       VARCHAR(100) UNIQUE NOT NULL,
    score       INTEGER DEFAULT 0,
    wins        INTEGER DEFAULT 0,
    losses      INTEGER DEFAULT 0,
    created_at  TIMESTAMP DEFAULT NOW(),
    updated_at  TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS matches (
    id          SERIAL PRIMARY KEY,
    player1_id  INTEGER REFERENCES players(id),
    player2_id  INTEGER REFERENCES players(id),
    winner_id   INTEGER REFERENCES players(id),
    status      VARCHAR(20) DEFAULT 'pending',
    created_at  TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Seed 10 players for development
INSERT INTO players (username, email, score) VALUES
    ('nova',    'nova@game.io',    4200),
    ('blaze',   'blaze@game.io',   3800),
    ('storm',   'storm@game.io',   3500),
    ('viper',   'viper@game.io',   3100),
    ('echo',    'echo@game.io',    2900),
    ('titan',   'titan@game.io',   2600),
    ('ghost',   'ghost@game.io',   2200),
    ('pixel',   'pixel@game.io',   1800),
    ('sage',    'sage@game.io',    1400),
    ('drift',   'drift@game.io',   900)
ON CONFLICT DO NOTHING;
```

---

## Module Specifications

Implement each module as a Python class in `app/modules/`. All classes receive
a `redis.Redis` instance in `__init__`. Keep modules pure — no FastAPI imports,
no HTTP concerns. Routers call the modules; modules only know about Redis and
Postgres.

---

### Module 1: Rate Limiter (`rate_limiter.py`)

**Algorithm**: Sliding window using a ZSet. Each member is a unique request ID
(UUID), and the score is the Unix timestamp in milliseconds. On each request:
1. Remove all members with score older than `now - window_ms`
2. Add current request with score = now, member = uuid
3. Count members in the ZSet
4. If count > limit, reject

All three steps must run atomically. Use a Lua script registered with
`redis.register_script()` so the check-and-increment is atomic.

**Class interface**:
```python
class RateLimiter:
    def __init__(self, r: redis.Redis, limit: int, window_seconds: int): ...
    def is_allowed(self, player_id: str) -> tuple[bool, int, int]:
        """
        Returns (allowed, current_count, retry_after_seconds).
        retry_after_seconds is 0 if allowed.
        Key pattern: ratelimit:{player_id}
        Set TTL on the key equal to window_seconds to auto-cleanup.
        """
```

**FastAPI middleware**: Apply rate limiting as a FastAPI middleware in
`main.py`. Extract player_id from the `X-Player-ID` request header. If the
header is missing, use the client IP. Return HTTP 429 with headers:
- `X-RateLimit-Limit`: the configured limit
- `X-RateLimit-Remaining`: requests left in window
- `Retry-After`: seconds until window resets (only on 429)

---

### Module 2: Leaderboard (`leaderboard.py`)

**Data structure**: Single ZSet with key `leaderboard:global`. Members are
player usernames. Scores are player scores (integers, but stored as floats by
Redis — this is fine).

**Class interface**:
```python
class Leaderboard:
    def __init__(self, r: redis.Redis): ...

    def add_or_update(self, username: str, score: float) -> None:
        """ZADD leaderboard:global score username"""

    def get_rank(self, username: str) -> dict | None:
        """
        Returns {username, score, rank} where rank is 1-based (1 = highest).
        Use ZREVRANK for rank, ZSCORE for score.
        Returns None if player not on leaderboard.
        """

    def get_top(self, n: int) -> list[dict]:
        """
        Returns top N players as [{rank, username, score}].
        Use ZREVRANGE with WITHSCORES.
        """

    def get_around_player(self, username: str, radius: int = 3) -> list[dict]:
        """
        Returns the `radius` players above and below the given player,
        plus the player themselves. This is the 'friends nearby' feature.
        Use ZREVRANK to find position, then ZREVRANGE with calculated slice.
        """

    def increment_score(self, username: str, delta: float) -> float:
        """
        ZINCRBY — atomically adds delta to score. Returns new score.
        Used when a match completes.
        """

    def remove_player(self, username: str) -> None:
        """ZREM — remove from leaderboard."""
```

---

### Module 3: Player Profile Cache (`profile_cache.py`)

**Pattern**: Cache-aside (lazy loading). The cache is never the source of
truth — Postgres always is.

**Data structure**: Redis Hash, one per player. Key: `player:{player_id}`.
TTL: 5 minutes (300 seconds). All hash field values are strings (Redis
requirement) — convert types on the way in and out.

**Class interface**:
```python
class ProfileCache:
    def __init__(self, r: redis.Redis, db_conn): ...

    def get(self, player_id: int) -> dict | None:
        """
        Cache-aside read:
        1. HGETALL player:{player_id}
        2. If hit: return deserialized dict, reset TTL with EXPIRE
        3. If miss: fetch from Postgres, HSET all fields, set TTL, return dict
        Returns None if player doesn't exist in Postgres either.
        """

    def invalidate(self, player_id: int) -> None:
        """
        DEL player:{player_id}
        Call this whenever Postgres is updated for this player.
        """

    def update(self, player_id: int, fields: dict) -> dict:
        """
        Write-through update:
        1. UPDATE players SET ... WHERE id = player_id in Postgres
        2. Invalidate cache (DEL)
        3. Return fresh get() to repopulate cache
        This ensures Postgres is always updated first.
        """
```

**Fields to cache**: `id`, `username`, `email`, `score`, `wins`, `losses`,
`created_at`.

---

### Module 4: Matchmaking Queue (`matchmaking.py`)

**Data structure**: Redis List. Key: `queue:matchmaking`. Players join at the
tail (RPUSH). The matchmaker worker pops from the head (BLPOP).

**Queue-side class** (used by the API):
```python
class MatchmakingQueue:
    def __init__(self, r: redis.Redis): ...

    def join(self, player_id: int) -> int:
        """
        RPUSH queue:matchmaking player_id.
        Returns queue length (position hint).
        Check player is not already in queue first:
        use a Set key queue:matchmaking:members for O(1) membership test.
        SADD queue:matchmaking:members player_id — add to tracking set.
        """

    def leave(self, player_id: int) -> bool:
        """
        LREM queue:matchmaking 1 player_id.
        SREM queue:matchmaking:members player_id.
        Returns True if player was in queue.
        """

    def depth(self) -> int:
        """LLEN queue:matchmaking"""

    def is_queued(self, player_id: int) -> bool:
        """SISMEMBER queue:matchmaking:members player_id"""
```

**Worker** (`workers/matchmaker.py`):
```python
# Run as: python -m app.workers.matchmaker
# Loop forever:
#   BLPOP queue:matchmaking {timeout}  — blocks until a player is available
#   If two players are popped (pop twice), create a match:
#     - Use distributed lock (Module 5) on lock:match:{p1_id}:{p2_id}
#     - INSERT into matches table in Postgres
#     - Publish event to stream (Module 6): match_created
#     - SREM both players from queue:matchmaking:members
#   Log all actions with timestamps
```

The worker should handle SIGTERM gracefully — finish the current iteration
and exit cleanly.

---

### Module 5: Distributed Lock (`distributed_lock.py`)

**Algorithm**: `SET key value NX EX ttl`. The value is a unique token (UUID)
generated at lock acquisition time. Release only if the token matches — this
prevents a slow lock holder from releasing a lock already acquired by someone
else. Use a Lua script for the atomic check-and-delete on release.

**Implement as a context manager**:
```python
class RedisLock:
    def __init__(self, r: redis.Redis, name: str, ttl_seconds: int = 10): ...

    def acquire(self) -> bool:
        """
        SET lock:{name} {token} NX EX {ttl_seconds}
        Returns True if acquired, False if already held.
        Stores the token as instance variable for release validation.
        """

    def release(self) -> bool:
        """
        Lua script: if GET key == token then DEL key end
        Returns True if released, False if lock was not ours.
        """

    def __enter__(self) -> 'RedisLock':
        """Acquire lock. Raise RuntimeError if cannot acquire."""

    def __exit__(self, *args):
        """Always attempt release."""

class LockManager:
    def __init__(self, r: redis.Redis): ...

    def lock(self, name: str, ttl_seconds: int = 10) -> RedisLock:
        """Factory: return RedisLock(self.r, name, ttl_seconds)"""
```

**Usage example** (in matchmaker worker):
```python
with lock_manager.lock(f"match:{p1_id}:{p2_id}", ttl_seconds=10):
    # create match — only one worker can be here at a time
```

---

### Module 6: Game Event Stream (`event_stream.py`)

**Data structure**: Redis Stream. Key: `stream:game-events`. Consumer group:
`game-services`.

**Events to publish** (each as a stream message with these fields):

| Event type | Fields |
|---|---|
| `player_joined_queue` | player_id, username, timestamp |
| `match_created` | match_id, player1_id, player2_id, timestamp |
| `match_completed` | match_id, winner_id, loser_id, score_delta, timestamp |
| `score_updated` | player_id, username, old_score, new_score, timestamp |

**Publisher class**:
```python
class EventStream:
    def __init__(self, r: redis.Redis, stream_key: str): ...

    def publish(self, event_type: str, data: dict) -> str:
        """
        XADD stream:game-events * event_type {event_type} **data
        Returns the stream entry ID.
        Automatically adds event_type and timestamp fields.
        """

    def ensure_consumer_group(self, group: str) -> None:
        """
        XGROUP CREATE stream:game-events {group} $ MKSTREAM
        Ignore error if group already exists (BUSYGROUP).
        Call this at startup.
        """
```

**Consumer worker** (`workers/event_consumer.py`):
```python
# Run as: python -m app.workers.event_consumer
# Setup:
#   ensure_consumer_group("game-services")
#
# Loop forever:
#   XREADGROUP GROUP game-services consumer-{hostname} COUNT 10 BLOCK 2000 STREAMS stream:game-events >
#   For each message:
#     dispatch to handler based on event_type field
#     XACK stream:game-events game-services {message_id}
#   Also process pending messages (XPENDING) on startup to handle
#   messages that were delivered but not acknowledged before crash.
#
# Handlers (just log for now, but structure for extensibility):
#   on_player_joined_queue(data) -> log
#   on_match_created(data) -> log
#   on_match_completed(data) -> update leaderboard score
#   on_score_updated(data) -> invalidate profile cache
```

---

## API Endpoints

### Players (`/players`)

```
POST   /players                    Create player (writes to Postgres, invalidates cache)
GET    /players/{id}               Get player profile (cache-aside)
PUT    /players/{id}/score         Update score (write-through cache, update leaderboard)
POST   /players/{id}/queue/join    Join matchmaking queue
POST   /players/{id}/queue/leave   Leave matchmaking queue
GET    /players/{id}/rank          Get leaderboard rank + neighbours
```

### Leaderboard (`/leaderboard`)

```
GET    /leaderboard/top?n=10       Top N players
GET    /leaderboard/around/{id}?radius=3   Players around a given player
```

### Matches (`/matches`)

```
GET    /matches/queue/depth        Current matchmaking queue depth
GET    /matches/{id}               Get match details from Postgres
POST   /matches/{id}/complete      Complete match — declare winner, update scores
```

### System (`/`)

```
GET    /health                     Returns Redis ping, Postgres check, stream info
GET    /debug/redis-keys           Returns all key patterns and their types (dev only)
```

---

## API Conventions

- All endpoints require `X-Player-ID` header for rate limiting (except `/health`)
- All responses are JSON
- Error responses: `{"error": "message", "code": "ERROR_CODE"}`
- HTTP 429 responses include `Retry-After` header
- Player IDs in URLs are integers; usernames in leaderboard are strings

---

## Key Patterns Reference

All Redis keys used in the system:

```
ratelimit:{player_id}            ZSet   sliding window of request timestamps
leaderboard:global               ZSet   all players, score = game score
player:{player_id}               Hash   cached player profile
queue:matchmaking                List   FIFO queue of player_ids awaiting match
queue:matchmaking:members        Set    O(1) membership check for queue
lock:{name}                      String NX+EX distributed lock token
stream:game-events               Stream append-only event log
```

---

## Seed Script (`scripts/seed_leaderboard.py`)

After containers are up, this script:
1. Connects to Redis
2. Reads all players from Postgres
3. Calls `leaderboard.add_or_update(username, score)` for each
4. Prints the top 10 to confirm

Run with: `docker compose exec api python scripts/seed_leaderboard.py`

---

## Load Test Script (`scripts/load_test.py`)

Sends rapid HTTP requests to `GET /leaderboard/top` with the same
`X-Player-ID` header to trigger rate limiting. Prints each response status
and the rate limit headers. Should show 200s followed by 429s once the
window fills.

Run with: `docker compose exec api python scripts/load_test.py`

---

## Tests

Write pytest tests for each module. Tests should use a real Redis instance
(the one from Docker Compose) and clean up their keys in `setup`/`teardown`.
Use a test key prefix `test:` for all keys to avoid colliding with dev data.

Each test file should have:
- At least one happy-path test
- At least one boundary/edge case test
- Cleanup fixture that deletes all `test:*` keys after the test

Key things to test:
- Rate limiter: exactly N requests succeed, N+1 is rejected, window resets
- Leaderboard: correct rank after multiple updates, neighbour lookup correct
- Cache: miss populates cache, hit skips Postgres, invalidation clears cache
- Queue: join/leave/depth, duplicate join rejected
- Lock: second acquire fails while first is held, context manager releases on exception
- Stream: published message is consumed and acknowledged

---

## README.md

Write a README with:
1. One-command startup: `docker compose up --build`
2. How to seed data: the seed script command
3. How to run the load test
4. A `curl` example for each endpoint group
5. A section explaining which Redis pattern each module demonstrates and why
6. How to inspect Redis directly: `docker compose exec redis redis-cli`
   with example commands (ZRANGE, XLEN, etc.) to see live data

---

## Implementation Notes

**Connection management**: Create a single Redis connection in
`app/redis_client.py` using `redis.Redis.from_url(settings.REDIS_URL,
decode_responses=True)`. Pass this instance into each module. Use
`decode_responses=True` so all values come back as Python strings, not bytes.

**Lua scripts**: Register Lua scripts at module `__init__` time using
`r.register_script(lua_code)`. This compiles and caches the script. Do not
inline Lua in hot paths.

**Error handling**: Wrap Redis calls in try/except for
`redis.exceptions.ConnectionError` and `redis.exceptions.TimeoutError`.
Log errors and return appropriate HTTP 503 responses from the API layer.

**Logging**: Use Python's `logging` module with structured log lines that
include `module`, `operation`, `player_id` (when relevant), and timing.
Format: `[MODULE] operation player_id=X duration_ms=Y result=Z`

**Worker shutdown**: Both worker processes should catch `SIGTERM` and
`SIGINT`, set a `running = False` flag, and exit the main loop cleanly.
Docker Compose sends SIGTERM before SIGKILL.

**Type hints**: Use type hints throughout. Pydantic models for all request
and response bodies in the routers.

---

## Acceptance Criteria

The project is complete when:

1. `docker compose up --build` starts all 5 services with no errors
2. `GET /health` returns 200 with Redis and Postgres both showing healthy
3. Seeding the leaderboard and calling `GET /leaderboard/top?n=5` returns
   5 ranked players
4. Sending 25 rapid requests returns 20 × 200 then 5 × 429
5. Creating two players and having them both join the queue results in the
   matchmaker worker creating a match (visible in Postgres matches table)
6. After match completion, both players' leaderboard scores are updated
7. The event consumer logs show all events flowing through the stream
8. All tests pass: `docker compose exec api pytest tests/ -v`
