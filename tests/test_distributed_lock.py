import pytest
from app.modules.distributed_lock import RedisLock, LockManager


def test_acquire_lock(r):
    lock = RedisLock(r, "test:mylock", ttl_seconds=5)
    acquired = lock.acquire()
    assert acquired is True
    lock.release()


def test_second_acquire_fails_while_held(r):
    lock1 = RedisLock(r, "test:exclusive", ttl_seconds=5)
    lock2 = RedisLock(r, "test:exclusive", ttl_seconds=5)

    assert lock1.acquire() is True
    assert lock2.acquire() is False

    lock1.release()


def test_release_frees_lock(r):
    lock = RedisLock(r, "test:releasable", ttl_seconds=5)
    lock.acquire()
    lock.release()

    lock2 = RedisLock(r, "test:releasable", ttl_seconds=5)
    assert lock2.acquire() is True
    lock2.release()


def test_context_manager_acquires_and_releases(r):
    with RedisLock(r, "test:ctx", ttl_seconds=5):
        key = "lock:test:ctx"
        assert r.exists(key)
    assert not r.exists("lock:test:ctx")


def test_context_manager_releases_on_exception(r):
    try:
        with RedisLock(r, "test:ctx-exc", ttl_seconds=5):
            raise ValueError("boom")
    except ValueError:
        pass
    assert not r.exists("lock:test:ctx-exc")


def test_context_manager_raises_if_cannot_acquire(r):
    lock1 = RedisLock(r, "test:cm-fail", ttl_seconds=5)
    lock1.acquire()
    try:
        with pytest.raises(RuntimeError):
            with RedisLock(r, "test:cm-fail", ttl_seconds=5):
                pass
    finally:
        lock1.release()


def test_lock_manager_factory(r):
    lm = LockManager(r)
    lock = lm.lock("test:factory", ttl_seconds=5)
    assert isinstance(lock, RedisLock)
    lock.acquire()
    lock.release()
