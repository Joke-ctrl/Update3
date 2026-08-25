"""phase 2 analysis runs and persisted SMC evidence

Revision ID: 3c1e5d9a7b42
Revises: 9942621f6fdd
"""
from alembic import op
import sqlalchemy as sa

revision = "3c1e5d9a7b42"
down_revision = "9942621f6fdd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_runs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("primary_timeframe", sa.String(), nullable=False),
        sa.Column("timeframes", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("direction", sa.String(), nullable=False),
        sa.Column("market_bias", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confluence_score", sa.Float(), nullable=False),
        sa.Column("entry_zone_low", sa.Float(), nullable=True),
        sa.Column("entry_zone_high", sa.Float(), nullable=True),
        sa.Column("invalidation", sa.Float(), nullable=True),
        sa.Column("stop_loss", sa.Float(), nullable=True),
        sa.Column("take_profits", sa.JSON(), nullable=False),
        sa.Column("risk_reward", sa.Float(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_analysis_runs_symbol_created", "analysis_runs", ["symbol", "created_at"])

    evidence_tables = {
        "structure_events": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("symbol", sa.String(), False), ("timeframe", sa.String(), False),
            ("event_index", sa.Integer(), False), ("event_time", sa.DateTime(timezone=True), False),
            ("event_type", sa.String(), False), ("direction", sa.String(), False),
            ("price", sa.Float(), False), ("broken_swing_price", sa.Float(), False),
        ],
        "fair_value_gaps": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("symbol", sa.String(), False), ("timeframe", sa.String(), False),
            ("event_index", sa.Integer(), False), ("event_time", sa.DateTime(timezone=True), False),
            ("direction", sa.String(), False), ("top", sa.Float(), False), ("bottom", sa.Float(), False),
            ("filled", sa.Boolean(), False), ("fill_index", sa.Integer(), True),
        ],
        "order_blocks": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("symbol", sa.String(), False), ("timeframe", sa.String(), False),
            ("event_index", sa.Integer(), False), ("event_time", sa.DateTime(timezone=True), False),
            ("direction", sa.String(), False), ("top", sa.Float(), False), ("bottom", sa.Float(), False),
            ("mitigated", sa.Boolean(), False), ("mitigation_index", sa.Integer(), True),
            ("break_index", sa.Integer(), True),
        ],
        "liquidity_sweeps": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("symbol", sa.String(), False), ("timeframe", sa.String(), False),
            ("event_index", sa.Integer(), False), ("event_time", sa.DateTime(timezone=True), False),
            ("direction", sa.String(), False), ("swept_level", sa.Float(), False),
            ("swept_swing_index", sa.Integer(), False),
        ],
        "economic_events": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("name", sa.String(), False), ("currency", sa.String(), False),
            ("impact", sa.String(), False), ("event_time", sa.DateTime(timezone=True), False),
            ("forecast", sa.String(), True), ("previous", sa.String(), True), ("actual", sa.String(), True),
        ],
        "news_articles": [
            ("id", sa.String(), False), ("analysis_run_id", sa.String(), False),
            ("title", sa.Text(), False), ("link", sa.Text(), False),
            ("published", sa.DateTime(timezone=True), True), ("summary", sa.Text(), False),
            ("sentiment", sa.Float(), False),
        ],
    }

    for table, columns in evidence_tables.items():
        op.create_table(
            table,
            *[sa.Column(name, typ, nullable=nullable) for name, typ, nullable in columns],
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(
                ["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"
            ),
        )

    # Batch mode keeps the migration compatible with SQLite as well as PostgreSQL.
    with op.batch_alter_table("signals", recreate="always") as batch:
        batch.add_column(sa.Column("analysis_run_id", sa.String(), nullable=True))
        batch.add_column(sa.Column("setup_status", sa.String(), nullable=False, server_default="NO_SETUP"))
        batch.add_column(sa.Column("market_bias", sa.String(), nullable=False, server_default="neutral"))
        batch.add_column(sa.Column("entry_zone_low", sa.Float(), nullable=True))
        batch.add_column(sa.Column("entry_zone_high", sa.Float(), nullable=True))
        batch.add_column(sa.Column("invalidation", sa.Float(), nullable=True))
        batch.add_column(sa.Column("take_profits", sa.JSON(), nullable=False, server_default="[]"))
        batch.create_foreign_key(
            "fk_signals_analysis_run_id", "analysis_runs", ["analysis_run_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("signals", recreate="always") as batch:
        batch.drop_constraint("fk_signals_analysis_run_id", type_="foreignkey")
        for column in [
            "take_profits", "invalidation", "entry_zone_high", "entry_zone_low",
            "market_bias", "setup_status", "analysis_run_id",
        ]:
            batch.drop_column(column)

    for table in [
        "news_articles", "economic_events", "liquidity_sweeps",
        "order_blocks", "fair_value_gaps", "structure_events",
    ]:
        op.drop_table(table)
    op.drop_index("ix_analysis_runs_symbol_created", table_name="analysis_runs")
    op.drop_table("analysis_runs")
