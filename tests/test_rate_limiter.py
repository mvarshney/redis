import time
import pytest
from app.modules.rate_limiter import RateLimiter


class PrefixedRateLimiter(RateLimiter):
    """Override key prefix for tests to use test: namespace."""
    def is_allowed(self, player_id: str):
        return super().is_allowed(f"test:{player_id}")


@pytest.fixture
def limiter(r):
    return PrefixedRateLimiter(r, limit=5, window_seconds=10)


def test_allows_requests_within_limit(limiter):
    for i in range(5):
        allowed, count, retry_after = limiter.is_allowed("player-rl-1")
        assert allowed is True
        assert retry_after == 0


def test_rejects_request_over_limit(limiter):
    for _ in range(5):
        limiter.is_allowed("player-rl-2")
    allowed, count, retry_after = limiter.is_allowed("player-rl-2")
    assert allowed is False
    assert retry_after > 0


def test_count_increments_correctly(limiter):
    for i in range(3):
        allowed, count, _ = limiter.is_allowed("player-rl-3")
        assert count == i + 1
        assert allowed is True


def test_different_players_have_independent_windows(limiter):
    for _ in range(5):
        limiter.is_allowed("player-rl-a")

    allowed, _, _ = limiter.is_allowed("player-rl-b")
    assert allowed is True


def test_remaining_header_decreases(r):
    lim = PrefixedRateLimiter(r, limit=10, window_seconds=10)
    _, count1, _ = lim.is_allowed("player-rl-rem")
    _, count2, _ = lim.is_allowed("player-rl-rem")
    assert count2 == count1 + 1
