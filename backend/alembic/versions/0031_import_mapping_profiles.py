"""Workspace-confirmed import formats, protected by FORCE RLS."""
from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE import_mapping_profiles (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        kind text NOT NULL CHECK (kind IN ('sales','inventory','products')),
        fingerprint text NOT NULL CHECK (length(fingerprint)=64),
        mapping jsonb NOT NULL,
        column_types jsonb NOT NULL DEFAULT '{}'::jsonb,
        options jsonb NOT NULL DEFAULT '{}'::jsonb,
        revision integer NOT NULL DEFAULT 1 CHECK (revision > 0),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id,kind,fingerprint)
    )""")
    op.execute("ALTER TABLE import_mapping_profiles ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE import_mapping_profiles FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY import_mapping_profiles_isolation ON import_mapping_profiles
        USING (tenant_id=current_tenant_id()) WITH CHECK (tenant_id=current_tenant_id())""")
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON import_mapping_profiles TO sanket_app")


def downgrade():
    op.execute("DROP TABLE import_mapping_profiles")
