from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = "gamedb"
    postgres_user: str = "gameuser"
    postgres_password: str = "gamepass"
    postgres_url: str = "postgresql://gameuser:gamepass@localhost:5432/gamedb"

    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60

    match_lock_ttl_seconds: int = 10
    matchmaker_poll_timeout_seconds: int = 5

    stream_key: str = "stream:game-events"
    consumer_group: str = "game-services"

    class Config:
        env_file = ".env"


settings = Settings()
