import pytest
from app.modules.matchmaking import MatchmakingQueue

TEST_QUEUE_KEY = "test:queue:matchmaking"
TEST_MEMBERS_KEY = "test:queue:matchmaking:members"


@pytest.fixture
def queue(r):
    import app.modules.matchmaking as mm
    mm.QUEUE_KEY = TEST_QUEUE_KEY
    mm.MEMBERS_KEY = TEST_MEMBERS_KEY
    q = MatchmakingQueue(r)
    yield q
    r.delete(TEST_QUEUE_KEY, TEST_MEMBERS_KEY)


def test_join_queue(queue):
    depth = queue.join(101)
    assert depth == 1
    assert queue.is_queued(101)


def test_queue_depth(queue):
    queue.join(201)
    queue.join(202)
    assert queue.depth() == 2


def test_leave_queue(queue):
    queue.join(301)
    removed = queue.leave(301)
    assert removed is True
    assert not queue.is_queued(301)
    assert queue.depth() == 0


def test_leave_nonexistent_player(queue):
    removed = queue.leave(999)
    assert removed is False


def test_duplicate_join_rejected(queue):
    queue.join(401)
    with pytest.raises(ValueError):
        queue.join(401)


def test_is_queued(queue):
    assert not queue.is_queued(501)
    queue.join(501)
    assert queue.is_queued(501)
