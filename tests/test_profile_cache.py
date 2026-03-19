import pytest
from unittest.mock import MagicMock, patch
from app.modules.profile_cache import ProfileCache


def make_fake_player(player_id=1):
    return {
        "id": player_id,
        "username": "testuser",
        "email": "testuser@test.io",
        "score": 1000,
        "wins": 5,
        "losses": 2,
        "created_at": "2024-01-01 00:00:00",
    }


@pytest.fixture
def mock_db(db):
    """Return real db but intercept the cursor for unit-style tests."""
    return db


@pytest.fixture
def cache(r, mock_db):
    c = ProfileCache(r, mock_db)
    # Patch _fetch_from_db to return a fake player
    return c


def test_cache_miss_populates_cache(r):
    fake = make_fake_player(99999)
    db = MagicMock()
    cache = ProfileCache(r, db)
    cache._fetch_from_db = MagicMock(return_value=fake)

    result = cache.get(99999)
    assert result["username"] == "testuser"

    # Key should now be in Redis
    assert r.exists("player:99999")
    cache._fetch_from_db.assert_called_once_with(99999)
    r.delete("player:99999")


def test_cache_hit_skips_db(r):
    fake = make_fake_player(99998)
    db = MagicMock()
    cache = ProfileCache(r, db)
    cache._fetch_from_db = MagicMock(return_value=fake)

    # Prime the cache
    cache.get(99998)
    db_call_count = cache._fetch_from_db.call_count

    # Second call should hit cache
    result = cache.get(99998)
    assert result["username"] == "testuser"
    assert cache._fetch_from_db.call_count == db_call_count  # no new DB call
    r.delete("player:99998")


def test_invalidate_clears_cache(r):
    fake = make_fake_player(99997)
    db = MagicMock()
    cache = ProfileCache(r, db)
    cache._fetch_from_db = MagicMock(return_value=fake)

    cache.get(99997)
    assert r.exists("player:99997")

    cache.invalidate(99997)
    assert not r.exists("player:99997")


def test_returns_none_for_missing_player(r):
    db = MagicMock()
    cache = ProfileCache(r, db)
    cache._fetch_from_db = MagicMock(return_value=None)

    result = cache.get(99996)
    assert result is None
