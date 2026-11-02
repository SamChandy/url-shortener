"""ORM models: users, links, clicks."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    links: Mapped[list["Link"]] = relationship(back_populates="owner")


class Link(Base):
    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Unique + indexed: this is the hot lookup column for redirects.
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    long_url: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship(back_populates="links")
    clicks: Mapped[list["Click"]] = relationship(
        back_populates="link", cascade="all, delete-orphan", passive_deletes=True
    )


class Click(Base):
    __tablename__ = "clicks"
    # Composite index serves "clicks for link X over a time range" (per-day chart).
    __table_args__ = (Index("ix_clicks_link_id_clicked_at", "link_id", "clicked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    link_id: Mapped[int] = mapped_column(ForeignKey("links.id", ondelete="CASCADE"), index=True)
    clicked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    country: Mapped[str] = mapped_column(String(64), default="Unknown")
    device: Mapped[str] = mapped_column(String(16), default="Other")  # Mobile/Tablet/PC/Other
    browser: Mapped[str] = mapped_column(String(64), default="Other")
    os: Mapped[str] = mapped_column(String(64), default="Other")

    link: Mapped[Link] = relationship(back_populates="clicks")
