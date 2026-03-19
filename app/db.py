import psycopg2
import psycopg2.extras
from app.config import settings

_db_conn = None


def get_db():
    global _db_conn
    if _db_conn is None or _db_conn.closed:
        _db_conn = psycopg2.connect(
            host=settings.postgres_host,
            port=settings.postgres_port,
            dbname=settings.postgres_db,
            user=settings.postgres_user,
            password=settings.postgres_password,
        )
        _db_conn.autocommit = False
    return _db_conn


def fetch_one(query: str, params=None) -> dict | None:
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        return dict(row) if row else None


def fetch_all(query: str, params=None) -> list[dict]:
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]


def execute(query: str, params=None) -> None:
    conn = get_db()
    with conn.cursor() as cur:
        cur.execute(query, params)
    conn.commit()


def execute_returning(query: str, params=None) -> dict | None:
    conn = get_db()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None
