"""add_media_to_faq

Revision ID: 1020_add_media_to_faq
Revises: ea387d7d1381
Create Date: 2026-05-22 17:46:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1020_add_media_to_faq'
down_revision: Union[str, None] = 'ea387d7d1381'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('faq_pages', sa.Column('media_type', sa.String(length=50), nullable=True))
    op.add_column('faq_pages', sa.Column('media_file_id', sa.String(length=255), nullable=True))
    op.add_column('faq_pages', sa.Column('media_group_data', sa.JSON(), nullable=True))
    op.add_column('faq_pages', sa.Column('inline_buttons', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('faq_pages', 'inline_buttons')
    op.drop_column('faq_pages', 'media_group_data')
    op.drop_column('faq_pages', 'media_file_id')
    op.drop_column('faq_pages', 'media_type')
