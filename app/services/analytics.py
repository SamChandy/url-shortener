"""Analytics queries. Every aggregation happens in SQL (GROUP BY), not in Python loops."""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import Date, cast, func, select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.errors import ApiError
from app.models import Click, Link, User


def get_owned_link(db: Session, code: str, user: User) -> Link:
    """404 if the link does not exist, 403 if it belongs to someone else."""
    link = db.scalar(select(Link).where(Link.code == code))
    if link is None:
        raise ApiError(404, "Link not found")
    if link.user_id != user.id:
        raise ApiError(403, "You do not own this link")
    return link


def total_clicks(db: Session, link_id: int) -> int:
    return db.scalar(select(func.count(Click.id)).where(Click.link_id == link_id)) or 0


def clicks_by(db: Session, link_id: int, column: InstrumentedAttribute[str]) -> list[tuple[str, int]]:
    """Clicks grouped by one column (country or device), biggest first."""
    n = func.count(Click.id)
    rows = db.execute(
        select(column, n).where(Click.link_id == link_id).group_by(column).order_by(n.desc(), column)
    )
    return [(value, count) for value, count in rows]


def _utc_day(db: Session):
    """SQL expression for the UTC calendar day of a click, on PostgreSQL and SQLite."""
    if db.get_bind().dialect.name == "postgresql":
        return cast(func.timezone("UTC", Click.clicked_at), Date)
    return func.date(Click.clicked_at)  # SQLite stores UTC wall-clock time


def clicks_per_day(
    db: Session, link_id: int, days: int, now: datetime | None = None
) -> list[tuple[str, int]]:
    """The last `days` UTC days (today included), with 0 for days without clicks."""
    today: date = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).date()
    first_day = today - timedelta(days=days - 1)
    start = datetime.combine(first_day, time.min, tzinfo=timezone.utc)

    day = _utc_day(db)
    rows = db.execute(
        select(day, func.count(Click.id))
        .where(Click.link_id == link_id, Click.clicked_at >= start)
        .group_by(day)
    )
    counts = {str(d): n for d, n in rows}
    series = (first_day + timedelta(days=i) for i in range(days))
    return [(d.isoformat(), counts.get(d.isoformat(), 0)) for d in series]


def top_links(db: Session, user_id: int, limit: int) -> list[tuple[str, str, int]]:
    """The user's links ranked by clicks (links with no clicks included, as 0)."""
    n = func.count(Click.id)
    rows = db.execute(
        select(Link.code, Link.long_url, n)
        .outerjoin(Click, Click.link_id == Link.id)
        .where(Link.user_id == user_id)
        .group_by(Link.id, Link.code, Link.long_url)
        .order_by(n.desc(), Link.id.desc())
        .limit(limit)
    )
    return [(code, long_url, count) for code, long_url, count in rows]
