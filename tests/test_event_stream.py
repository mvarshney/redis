import pytest
import time
from app.modules.event_stream import EventStream

TEST_STREAM = "test:stream:game-events"
TEST_GROUP = "test-group"


@pytest.fixture
def stream(r):
    s = EventStream(r, TEST_STREAM)
    yield s
    r.delete(TEST_STREAM)


def test_publish_creates_entry(stream, r):
    entry_id = stream.publish("test_event", {"player_id": "42", "value": "hello"})
    assert entry_id is not None
    length = r.xlen(TEST_STREAM)
    assert length == 1


def test_publish_contains_correct_fields(stream, r):
    stream.publish("score_updated", {"player_id": "1", "score": "500"})
    entries = r.xrange(TEST_STREAM, "-", "+")
    assert len(entries) == 1
    _, data = entries[0]
    assert data["event_type"] == "score_updated"
    assert data["player_id"] == "1"
    assert "timestamp" in data


def test_ensure_consumer_group_idempotent(stream, r):
    stream.ensure_consumer_group(TEST_GROUP)
    # Second call should not raise
    stream.ensure_consumer_group(TEST_GROUP)
    groups = r.xinfo_groups(TEST_STREAM)
    assert any(g["name"] == TEST_GROUP for g in groups)


def test_consume_and_ack(stream, r):
    stream.ensure_consumer_group(TEST_GROUP)
    stream.publish("match_created", {"match_id": "10", "player1_id": "1", "player2_id": "2"})

    messages = r.xreadgroup(
        groupname=TEST_GROUP,
        consumername="test-consumer",
        streams={TEST_STREAM: ">"},
        count=10,
        block=1000,
    )
    assert messages is not None
    assert len(messages) == 1
    _, entries = messages[0]
    assert len(entries) == 1
    entry_id, data = entries[0]
    assert data["event_type"] == "match_created"

    # Acknowledge
    r.xack(TEST_STREAM, TEST_GROUP, entry_id)

    # Pending should now be empty
    pending = r.xpending(TEST_STREAM, TEST_GROUP)
    assert pending["pending"] == 0
