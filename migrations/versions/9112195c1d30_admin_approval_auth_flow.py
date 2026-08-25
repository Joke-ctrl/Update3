"""admin-approval auth flow: is_approved, registration_codes, login_otps, refresh_tokens

Revision ID: 9112195c1d30
Revises: 3c1e5d9a7b42
Create Date: 2026-08-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "9112195c1d30"
down_revision = "3c1e5d9a7b42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- users.is_approved -----------------------------------------
    # Add as nullable-with-server-default first so the column backfills
    # cleanly on existing rows, then grandfather in every currently-active
    # user as approved (they registered under the pre-approval flow and
    # must not be locked out), and finally drop the server default so new
    # rows rely on the application's explicit default (False) instead.
    op.add_column(
        "users",
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE users SET is_approved = true WHERE is_active = true")
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column("is_approved", server_default=None)

    # --- registration_codes -----------------------------------------
    op.create_table(
        "registration_codes",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_registration_codes_user_id"), "registration_codes", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_registration_codes_code_hash"), "registration_codes", ["code_hash"], unique=True
    )

    # --- login_otps ----------------------------------------------------
    op.create_table(
        "login_otps",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("code_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_login_otps_user_id"), "login_otps", ["user_id"], unique=False)
    op.create_index(op.f("ix_login_otps_code_hash"), "login_otps", ["code_hash"], unique=True)

    # --- refresh_tokens --------------------------------------------
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("jti", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("replaced_by_jti", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_refresh_tokens_user_id"), "refresh_tokens", ["user_id"], unique=False)
    op.create_index(op.f("ix_refresh_tokens_jti"), "refresh_tokens", ["jti"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_refresh_tokens_jti"), table_name="refresh_tokens")
    op.drop_index(op.f("ix_refresh_tokens_user_id"), table_name="refresh_tokens")
    op.drop_table("refresh_tokens")

    op.drop_index(op.f("ix_login_otps_code_hash"), table_name="login_otps")
    op.drop_index(op.f("ix_login_otps_user_id"), table_name="login_otps")
    op.drop_table("login_otps")

    op.drop_index(op.f("ix_registration_codes_code_hash"), table_name="registration_codes")
    op.drop_index(op.f("ix_registration_codes_user_id"), table_name="registration_codes")
    op.drop_table("registration_codes")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("is_approved")
