import pytest
import redis
import psycopg2
from app.config import settings


@pytest.fixture(scope="session")
def r():
    client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    client.close()


@pytest.fixture(scope="session")
def db():
    conn = psycopg2.connect(
        host=settings.postgres_host,
        port=settings.postgres_port,
        dbname=settings.postgres_db,
        user=settings.postgres_user,
        password=settings.postgres_password,
    )
    conn.autocommit = False
    yield conn
    conn.close()


@pytest.fixture(autouse=True)
def clean_test_keys(r):
    """Delete all test:* keys before and after each test."""
    def _clean():
        keys = r.keys("test:*")
        if keys:
            r.delete(*keys)
    _clean()
    yield
    _clean()
