"""create users, links, clicks

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("long_url", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_links_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_links"),
        sa.UniqueConstraint("code", name="uq_links_code"),
    )
    op.create_index("ix_links_code", "links", ["code"])
    op.create_index("ix_links_user_id", "links", ["user_id"])

    op.create_table(
        "clicks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("link_id", sa.Integer(), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("country", sa.String(64), nullable=False),
        sa.Column("device", sa.String(16), nullable=False),
        sa.Column("browser", sa.String(64), nullable=False),
        sa.Column("os", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["link_id"], ["links.id"], name="fk_clicks_link_id_links", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_clicks"),
    )
    op.create_index("ix_clicks_link_id", "clicks", ["link_id"])
    op.create_index("ix_clicks_link_id_clicked_at", "clicks", ["link_id", "clicked_at"])


def downgrade() -> None:
    op.drop_table("clicks")
    op.drop_table("links")
    op.drop_table("users")
