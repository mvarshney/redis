import pytest
from app.modules.leaderboard import Leaderboard

TEST_KEY = "test:leaderboard"


@pytest.fixture
def lb(r):
    """Leaderboard using test: key."""
    board = Leaderboard(r)
    board_key = TEST_KEY
    # Patch the key
    import app.modules.leaderboard as lb_mod
    original = lb_mod.LEADERBOARD_KEY
    lb_mod.LEADERBOARD_KEY = board_key
    yield board
    lb_mod.LEADERBOARD_KEY = original
    r.delete(board_key)


def test_add_and_get_rank(lb):
    lb.add_or_update("alice", 1000)
    lb.add_or_update("bob", 2000)
    rank = lb.get_rank("bob")
    assert rank["rank"] == 1
    assert rank["score"] == 2000
    rank_alice = lb.get_rank("alice")
    assert rank_alice["rank"] == 2


def test_get_top(lb):
    lb.add_or_update("p1", 300)
    lb.add_or_update("p2", 200)
    lb.add_or_update("p3", 100)
    top = lb.get_top(2)
    assert len(top) == 2
    assert top[0]["username"] == "p1"
    assert top[1]["username"] == "p2"


def test_get_rank_not_on_leaderboard(lb):
    result = lb.get_rank("nobody")
    assert result is None


def test_increment_score(lb):
    lb.add_or_update("player", 500)
    new_score = lb.increment_score("player", 100)
    assert new_score == 600.0
    rank = lb.get_rank("player")
    assert rank["score"] == 600


def test_remove_player(lb):
    lb.add_or_update("to_remove", 999)
    lb.remove_player("to_remove")
    assert lb.get_rank("to_remove") is None


def test_get_around_player(lb):
    for i, name in enumerate(["e", "d", "c", "b", "a"]):
        lb.add_or_update(name, (i + 1) * 100)
    # "c" is in the middle — rank 3 of 5
    neighbours = lb.get_around_player("c", radius=1)
    usernames = [n["username"] for n in neighbours]
    assert "c" in usernames
    assert "b" in usernames
    assert "d" in usernames
