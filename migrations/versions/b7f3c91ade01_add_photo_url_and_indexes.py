"""add_photo_url_and_indexes

- users.photo_url ustuni (avval qo'lda qo'shilgan edi — migrate_photo.py)
- tartiblash/indeks uchun tushgan indexlar: orders.created_at, users.role, offers.created_at

Revision ID: b7f3c91ade01
Revises: 8da0c4784fe0
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7f3c91ade01'
down_revision: Union[str, None] = '8da0c4784fe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. users.photo_url — mavjud bo'lmasa qo'shamiz (eski bazalarda allaqachon bor)
    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "photo_url" not in user_cols:
        op.add_column("users", sa.Column("photo_url", sa.String(length=500), nullable=True))

    # 2. Indekslar (mavjud bo'lmasa)
    def _ensure_index(table: str, name: str, columns: list[str]) -> None:
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns)

    _ensure_index("orders", "ix_orders_created_at", ["created_at"])
    _ensure_index("users", "ix_users_role", ["role"])
    _ensure_index("offers", "ix_offers_created_at", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table, name in (
        ("offers", "ix_offers_created_at"),
        ("users", "ix_users_role"),
        ("orders", "ix_orders_created_at"),
    ):
        existing = {ix["name"] for ix in inspector.get_indexes(table)}
        if name in existing:
            op.drop_index(name, table_name=table)

    user_cols = {c["name"] for c in inspector.get_columns("users")}
    if "photo_url" in user_cols:
        op.drop_column("users", "photo_url")
