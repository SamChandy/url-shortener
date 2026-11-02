"""POST /api/auth/signup and /api/auth/login."""
from flask import Blueprint, jsonify
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import create_access_token, hash_password, verify_password
from app.database import get_db
from app.errors import ApiError
from app.models import User
from app.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut, parse_json

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/signup")
def signup():
    data = parse_json(SignupRequest)
    db = get_db()

    if db.scalar(select(User.id).where(User.email == data.email)) is not None:
        raise ApiError(409, "Email already registered")

    user = User(email=data.email, hashed_password=hash_password(data.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:  # two signups raced past the check above
        db.rollback()
        raise ApiError(409, "Email already registered") from None
    db.refresh(user)
    return jsonify(UserOut.from_user(user).model_dump(mode="json")), 201


@bp.post("/login")
def login():
    data = parse_json(LoginRequest)
    user = get_db().scalar(select(User).where(User.email == data.email))

    # Same message for "no such user" and "wrong password": don't leak which emails exist.
    if user is None or not verify_password(data.password, user.hashed_password):
        raise ApiError(401, "Incorrect email or password", headers={"WWW-Authenticate": "Bearer"})

    token, expires_in = create_access_token(user.id)
    return jsonify(TokenResponse(access_token=token, expires_in=expires_in).model_dump())
