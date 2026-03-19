# Redis Gaming Backend

A multiplayer game backend demonstrating six core Redis capabilities, built with FastAPI and deployed with Docker Compose.

---

## Quick Start

```bash
docker compose up --build
```

All five services start: Redis, Postgres, API, Matchmaker worker, Event Consumer worker.

---

## Seed the Leaderboard

After containers are up:

```bash
docker compose exec api python scripts/seed_leaderboard.py
```

This reads all players from Postgres and populates `leaderboard:global` in Redis.

---

## Run the Load Test

Triggers rate limiting by sending 30 rapid requests:

```bash
docker compose exec api python scripts/load_test.py
```

You will see 20 × HTTP 200 followed by 10 × HTTP 429.

---

## Run Tests

```bash
docker compose exec api pytest tests/ -v
```

---

## API Examples

### Players

```bash
# Create a player
curl -X POST http://localhost:8000/players \
  -H "Content-Type: application/json" \
  -H "X-Player-ID: 1" \
  -d '{"username": "neo", "email": "neo@game.io"}'

# Get player profile (cache-aside)
curl http://localhost:8000/players/1 -H "X-Player-ID: 1"

# Update score
curl -X PUT http://localhost:8000/players/1/score \
  -H "Content-Type: application/json" \
  -H "X-Player-ID: 1" \
  -d '{"score": 5000}'

# Join matchmaking queue
curl -X POST http://localhost:8000/players/1/queue/join -H "X-Player-ID: 1"

# Leave matchmaking queue
curl -X POST http://localhost:8000/players/1/queue/leave -H "X-Player-ID: 1"

# Get leaderboard rank + neighbours
curl http://localhost:8000/players/1/rank -H "X-Player-ID: 1"
```

### Leaderboard

```bash
# Top 10 players
curl "http://localhost:8000/leaderboard/top?n=10" -H "X-Player-ID: 1"

# Players around player 5 (±3 neighbours)
curl "http://localhost:8000/leaderboard/around/5?radius=3" -H "X-Player-ID: 1"
```

### Matches

```bash
# Current queue depth
curl http://localhost:8000/matches/queue/depth -H "X-Player-ID: 1"

# Get match details
curl http://localhost:8000/matches/1 -H "X-Player-ID: 1"

# Complete a match (declare winner)
curl -X POST http://localhost:8000/matches/1/complete \
  -H "Content-Type: application/json" \
  -H "X-Player-ID: 1" \
  -d '{"winner_id": 1}'
```

### System

```bash
# Health check (Redis + Postgres + Stream info)
curl http://localhost:8000/health

# Inspect all Redis keys (dev only)
curl http://localhost:8000/debug/redis-keys -H "X-Player-ID: 1"
```

---

## Redis Patterns Explained

| Module | Redis Structure | Why Redis? |
|---|---|---|
| **Rate Limiter** | ZSet (sliding window) | Atomic Lua script removes expired timestamps and counts active requests in O(log N). Redis is the only right tool for per-request throttling at low latency. |
| **Leaderboard** | ZSet | ZADD/ZREVRANK/ZREVRANGE are O(log N) — a sorted set holds millions of players and rank queries are instant. Postgres ORDER BY at this scale would be far slower. |
| **Profile Cache** | Hash + TTL | HSET stores structured player data with field-level access. TTL auto-expires stale cache. Cache-aside pattern ensures Postgres remains source of truth. |
| **Matchmaking Queue** | List | RPUSH/BLPOP is a textbook job queue: producers push to the tail, workers block-pop from the head. Zero polling overhead. |
| **Distributed Lock** | String NX+EX | SET NX is an atomic test-and-set. The UUID token and Lua release script prevent a slow holder from accidentally releasing a lock it no longer owns. |
| **Game Event Stream** | Stream + Consumer Group | XADD appends events; XREADGROUP delivers each message to exactly one consumer in the group. Enables fan-out to multiple services with at-least-once delivery and crash recovery via XACK/XPENDING. |

---

## Inspect Redis Directly

```bash
docker compose exec redis redis-cli
```

Useful commands:

```redis
# See all key patterns
KEYS *

# View leaderboard (top 10, highest first)
ZREVRANGE leaderboard:global 0 9 WITHSCORES

# View matchmaking queue
LRANGE queue:matchmaking 0 -1

# View a player's cached profile
HGETALL player:1

# View rate limit window for player 1
ZRANGE ratelimit:1 0 -1 WITHSCORES

# Count stream events
XLEN stream:game-events

# Read last 5 stream events
XREVRANGE stream:game-events + - COUNT 5

# View consumer group info
XINFO GROUPS stream:game-events

# View pending messages
XPENDING stream:game-events game-services - + 10
```
