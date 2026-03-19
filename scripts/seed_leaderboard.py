"""
Seed the leaderboard from Postgres player data.
Run with: docker compose exec api python scripts/seed_leaderboard.py
"""
import sys
import os

sys.path.insert(0, "/app")

from app.redis_client import get_redis
from app.db import fetch_all
from app.modules.leaderboard import Leaderboard


def main():
    r = get_redis()
    lb = Leaderboard(r)

    players = fetch_all("SELECT username, score FROM players ORDER BY score DESC")
    print(f"Seeding {len(players)} players into leaderboard...")

    for player in players:
        lb.add_or_update(player["username"], player["score"])
        print(f"  + {player['username']} ({player['score']})")

    print("\nTop 10 leaderboard:")
    top10 = lb.get_top(10)
    for entry in top10:
        print(f"  #{entry['rank']:2d}  {entry['username']:<12}  {entry['score']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
