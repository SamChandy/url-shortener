"""The web interface: one static page that talks to the JSON API."""
from flask import Blueprint, Response, current_app

bp = Blueprint("web", __name__)


@bp.get("/")
def home() -> Response:
    response = current_app.send_static_file("index.html")
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response
