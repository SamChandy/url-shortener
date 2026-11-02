"""One JSON error format for the whole API: {"error": "...", "details": [...]}."""
from typing import Any

from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    """Raise anywhere (routes or services) to return a clean JSON error."""

    def __init__(
        self,
        status_code: int,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details
        self.headers = headers or {}


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(err: ApiError):
        body: dict[str, Any] = {"error": err.message}
        if err.details:
            body["details"] = err.details
        return jsonify(body), err.status_code, err.headers

    @app.errorhandler(HTTPException)
    def handle_http_error(err: HTTPException):
        # 404, 405, 500 ... as JSON instead of Flask's default HTML pages.
        return jsonify(error=err.description or err.name), err.code
