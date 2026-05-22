"""merge_branches

Revision ID: ea387d7d1381
Revises: c05ccd58e542, c4a72e00fcdf
Create Date: 2026-05-22 17:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ea387d7d1381'
down_revision: Union[str, tuple[str, ...], None] = ('c05ccd58e542', 'c4a72e00fcdf')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
