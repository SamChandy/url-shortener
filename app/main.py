"""Flask application factory."""
from typing import Any

from flask import Flask, jsonify
from redis import Redis
from werkzeug.middleware.proxy_fix import ProxyFix

from app.config import Settings, get_settings
from app.database import close_db, init_db
from app.errors import register_error_handlers
from app.routers import analytics as analytics_routes
from app.routers import auth as auth_routes
from app.routers import links as link_routes
from app.routers import redirect as redirect_routes
from app.routers import web as web_routes
from app.services.cache import LinkCache
from app.services.rate_limiter import RateLimiter


def create_app(overrides: dict[str, Any] | None = None, redis_client: Redis | None = None) -> Flask:
    """Build the app. Tests pass `overrides` (config) and `redis_client` (fakeredis)."""
    settings: Settings = get_settings()
    if overrides:
        settings = settings.model_copy(update=overrides)

    app = Flask(__name__)
    app.extensions["settings"] = settings

    # Behind a reverse proxy, request.remote_addr would be the proxy's IP. Only trust
    # X-Forwarded-For when told how many proxies to expect (otherwise it can be spoofed).
    if settings.trusted_proxy_count > 0:
        n = settings.trusted_proxy_count
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=n, x_proto=n, x_host=n)  # type: ignore[method-assign]

    init_db(settings.database_url)
    app.teardown_appcontext(close_db)
    register_error_handlers(app)

    # Redis connects lazily, so creating the client never fails even if Redis is down.
    if redis_client is None:
        redis_client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
    app.extensions["redis"] = redis_client
    app.extensions["link_cache"] = LinkCache(
        redis_client if settings.cache_enabled else None, settings.cache_ttl_seconds
    )

    app.extensions["rate_limiter"] = RateLimiter(
        redis_client,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
        enabled=settings.rate_limit_enabled,
    )

    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(link_routes.bp)
    app.register_blueprint(analytics_routes.bp)
    app.register_blueprint(web_routes.bp)

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    # Registered last on purpose: /health and /api/... are more specific than /<code>.
    app.register_blueprint(redirect_routes.bp)

    return app
