"""Small helpers shared by routes (Flask's stand-in for dependency injection)."""
from flask import current_app

from app.config import Settings
from app.services.cache import LinkCache


def current_settings() -> Settings:
    """The Settings object the running app was created with (tests can override it)."""
    return current_app.extensions["settings"]


def current_cache() -> LinkCache:
    """The redirect cache (Redis-backed, falls back to 'no cache' when Redis is down)."""
    return current_app.extensions["link_cache"]
