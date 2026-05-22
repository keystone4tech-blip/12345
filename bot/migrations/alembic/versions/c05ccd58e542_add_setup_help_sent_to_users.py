"""Add setup_help_sent to users

Revision ID: c05ccd58e542
Revises: 5f8a9b1c2d3e
Create Date: 2026-05-22 17:24:15.734519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c05ccd58e542'
down_revision: Union[str, None] = '5f8a9b1c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('setup_help_sent', sa.Boolean(), server_default='false', nullable=False))


def downgrade() -> None:
    op.drop_column('users', 'setup_help_sent')
