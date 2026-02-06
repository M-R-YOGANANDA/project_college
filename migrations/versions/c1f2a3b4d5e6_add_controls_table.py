"""add controls table

Revision ID: c1f2a3b4d5e6
Revises: a8b4ebe5fe17
Create Date: 2026-02-06 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c1f2a3b4d5e6"
down_revision = "a8b4ebe5fe17"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "controls",
        sa.Column("control_id", sa.Integer(), primary_key=True),
        sa.Column("branch_id", sa.Integer(), nullable=False),
        sa.Column("control_type", sa.String(length=20), nullable=False),
        sa.Column("semester", sa.Integer(), nullable=True),
        sa.Column("month", sa.String(length=2), nullable=True),
        sa.Column("cie_type", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.branch_id"]),
    )


def downgrade():
    op.drop_table("controls")
