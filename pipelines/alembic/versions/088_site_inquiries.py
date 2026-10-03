"""Store private site inquiries in the existing versioned account workspace."""

from alembic import op

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE public.watchspaces ADD COLUMN site_inquiries jsonb
        NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(site_inquiries) = 'array'
               AND jsonb_array_length(site_inquiries) <= 50);
        COMMENT ON COLUMN public.watchspaces.site_inquiries IS
        'Private user-entered site inquiries and reviewed content revisions. '
        'Source evidence is resolved live and is never copied into this field.';
    """)


def downgrade():
    op.execute("ALTER TABLE public.watchspaces DROP COLUMN site_inquiries")
