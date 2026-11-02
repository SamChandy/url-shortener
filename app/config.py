"""Application settings, loaded from environment variables (or a .env file).

Nothing secret is hardcoded: required values have no default, so the app
fails fast at startup if they are missing.
"""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Shortly"
    base_url: str = "http://localhost:5000"
    # Comma-separated hostnames that must not be shortened (self-referencing check).
    blocked_hosts: str = "localhost,127.0.0.1"

    # Required (no defaults on purpose)
    database_url: str
    redis_url: str
    secret_key: str = Field(min_length=16)

    # JWT
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Links / cache
    short_code_length: int = 7
    cache_ttl_seconds: int = 3600
    cache_enabled: bool = True  # False = always hit the database (for benchmarks)
    click_tracking_enabled: bool = True  # False = redirect without storing clicks (for benchmarks)

    # Rate limiting
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60
    rate_limit_enabled: bool = True

    # How many reverse proxies sit in front of the app (0 = none, X-Forwarded-For is ignored).
    # Only raise this if you really run behind that many proxies, otherwise clients can fake their IP.
    trusted_proxy_count: int = 0

    # GeoIP (optional: country becomes "Unknown" if the file is absent)
    geoip_db_path: str = "data/GeoLite2-Country.mmdb"

    @property
    def blocked_host_list(self) -> list[str]:
        return [h.strip().lower() for h in self.blocked_hosts.split(",") if h.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings; also usable as a FastAPI dependency."""
    return Settings()  # type: ignore[call-arg]
