"""Self-owned communication preferences and durable tenant scoped deliveries."""
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE communication_preferences (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY (tenant_id,user_id))""")
    op.execute("""CREATE TABLE communication_deliveries (
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        delivery_key text NOT NULL CHECK(length(delivery_key)<=160),
        content_hash text NOT NULL,
        state text NOT NULL CHECK(state IN ('sending','sent','failed','ambiguous','unavailable')),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        PRIMARY KEY(tenant_id,user_id,delivery_key))""")
    for table in ("communication_preferences", "communication_deliveries"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_isolation ON {table} USING(tenant_id=current_tenant_id()) WITH CHECK(tenant_id=current_tenant_id())")
        op.execute(f"GRANT SELECT,INSERT,UPDATE,DELETE ON {table} TO sanket_app")


def downgrade():
    op.execute("DROP TABLE communication_deliveries")
    op.execute("DROP TABLE communication_preferences")
