"""Initial LlamaGrid control-plane schema."""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False), sa.Column("password_hash", sa.String(512), nullable=False), sa.Column("display_name", sa.String(120), nullable=False), sa.Column("role", sa.String(40), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *_timestamps())
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table("servers", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("provider_server_id", sa.String(120)), sa.Column("private_ip", sa.String(64), nullable=False), sa.Column("public_ip", sa.String(64)), sa.Column("rpc_port", sa.Integer(), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("labels", sa.JSON(), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), *_timestamps())
    op.create_index("ix_servers_name", "servers", ["name"])
    op.create_index("uq_servers_private_ip", "servers", ["private_ip"], unique=True)
    op.create_table("models", sa.Column("id", sa.String(36), primary_key=True), sa.Column("model_id", sa.String(300), nullable=False), sa.Column("display_name", sa.String(300), nullable=False), sa.Column("source", sa.String(40), nullable=False), sa.Column("source_ref", sa.String(500)), sa.Column("quantization", sa.String(80)), sa.Column("context_length", sa.Integer()), sa.Column("status", sa.String(40), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), *_timestamps())
    op.create_index("ix_models_model_id", "models", ["model_id"], unique=True)
    op.create_table("deployments", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("model_id", sa.String(36), sa.ForeignKey("models.id"), nullable=False), sa.Column("desired_replicas", sa.Integer(), nullable=False), sa.Column("strategy", sa.String(40), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("config", sa.JSON(), nullable=False), *_timestamps())
    op.create_table("replicas", sa.Column("id", sa.String(36), primary_key=True), sa.Column("deployment_id", sa.String(36), sa.ForeignKey("deployments.id"), nullable=False), sa.Column("server_id", sa.String(36), sa.ForeignKey("servers.id"), nullable=False), sa.Column("endpoint", sa.String(500)), sa.Column("status", sa.String(40), nullable=False), sa.Column("health", sa.JSON(), nullable=False), *_timestamps())
    op.create_table("provider_credentials", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("provider", sa.String(40), nullable=False), sa.Column("encrypted_secret", sa.Text(), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("is_active", sa.Boolean(), nullable=False), *_timestamps())
    op.create_table("jobs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("kind", sa.String(80), nullable=False), sa.Column("status", sa.String(40), nullable=False), sa.Column("progress", sa.Integer(), nullable=False), sa.Column("message", sa.String(500), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("error", sa.Text()), *_timestamps())
    op.create_index("ix_jobs_kind", "jobs", ["kind"])
    op.create_index("ix_jobs_status", "jobs", ["status"])
    op.create_table("job_events", sa.Column("id", sa.String(36), primary_key=True), sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False), sa.Column("event_type", sa.String(80), nullable=False), sa.Column("message", sa.String(500), nullable=False), sa.Column("progress", sa.Integer(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), *_timestamps())
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_table("api_keys", sa.Column("id", sa.String(36), primary_key=True), sa.Column("name", sa.String(160), nullable=False), sa.Column("key_prefix", sa.String(32), nullable=False), sa.Column("key_digest", sa.String(64), nullable=False), sa.Column("revoked", sa.Boolean(), nullable=False), *_timestamps())
    op.create_index("uq_api_keys_key_digest", "api_keys", ["key_digest"], unique=True)
    op.create_table("audit_logs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36)), sa.Column("action", sa.String(160), nullable=False), sa.Column("resource_type", sa.String(80)), sa.Column("resource_id", sa.String(120)), sa.Column("ip_address", sa.String(64)), sa.Column("details", sa.JSON(), nullable=False), *_timestamps())
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("api_keys")
    op.drop_table("job_events")
    op.drop_table("jobs")
    op.drop_table("provider_credentials")
    op.drop_table("replicas")
    op.drop_table("deployments")
    op.drop_table("models")
    op.drop_table("servers")
    op.drop_table("users")
