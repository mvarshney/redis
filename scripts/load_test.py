"""
Load test — sends rapid requests to trigger rate limiting.
Run with: docker compose exec api python scripts/load_test.py
"""
import http.client
import json

HOST = "localhost"
PORT = 8000
PATH = "/leaderboard/top?n=5"
PLAYER_ID = "load-test-player"
REQUESTS = 30


def main():
    print(f"Sending {REQUESTS} requests to GET {PATH} with X-Player-ID: {PLAYER_ID}\n")
    ok_count = 0
    rate_limited = 0

    for i in range(1, REQUESTS + 1):
        conn = http.client.HTTPConnection(HOST, PORT, timeout=5)
        conn.request("GET", PATH, headers={"X-Player-ID": PLAYER_ID})
        resp = conn.getresponse()
        body = resp.read().decode()
        limit = resp.getheader("X-RateLimit-Limit", "-")
        remaining = resp.getheader("X-RateLimit-Remaining", "-")
        retry_after = resp.getheader("Retry-After", "")
        conn.close()

        status_str = f"HTTP {resp.status}"
        rate_str = f"limit={limit} remaining={remaining}"
        retry_str = f" retry_after={retry_after}" if retry_after else ""

        print(f"  [{i:2d}] {status_str}  {rate_str}{retry_str}")

        if resp.status == 200:
            ok_count += 1
        elif resp.status == 429:
            rate_limited += 1

    print(f"\nSummary: {ok_count} × 200 OK, {rate_limited} × 429 Too Many Requests")


if __name__ == "__main__":
    main()
