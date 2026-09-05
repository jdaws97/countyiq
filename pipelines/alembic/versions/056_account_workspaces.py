"""Provider-independent users and account-owned investigation workspaces.

Revision ID: 056
Revises: 055
"""
from alembic import op
revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE public.app_users (
        user_id UUID PRIMARY KEY,
        email TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE public.app_identities (
        provider TEXT NOT NULL,
        issuer TEXT NOT NULL,
        subject TEXT NOT NULL,
        user_id UUID NOT NULL REFERENCES public.app_users ON DELETE CASCADE,
        PRIMARY KEY(provider, issuer, subject)
    );
    ALTER TABLE public.watchspaces ALTER COLUMN token_hash DROP NOT NULL;
    ALTER TABLE public.watchspaces ADD COLUMN owner_user_id UUID UNIQUE REFERENCES public.app_users;
    ALTER TABLE public.watchspaces ADD COLUMN saved_searches JSONB NOT NULL DEFAULT '[]';
    ALTER TABLE public.watchspaces ADD COLUMN comparison TEXT[] NOT NULL DEFAULT '{}';
    ALTER TABLE public.watchspaces ADD COLUMN recent_investigations JSONB NOT NULL DEFAULT '[]';
    CREATE TABLE public.workspace_members (
        workspace_id UUID NOT NULL REFERENCES public.watchspaces ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES public.app_users ON DELETE CASCADE,
        role TEXT NOT NULL CHECK(role IN ('owner','member')),
        PRIMARY KEY(workspace_id,user_id)
    );
    CREATE INDEX workspace_members_user ON public.workspace_members(user_id);
    """)


def downgrade():
    # Never discard account-owned workspace data through a blind downgrade.
    op.execute("""
    DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.watchspaces WHERE owner_user_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Export/migrate account workspaces before downgrading 056';
      END IF;
    END $$;
    DROP TABLE public.workspace_members;
    ALTER TABLE public.watchspaces DROP COLUMN recent_investigations, DROP COLUMN comparison,
      DROP COLUMN saved_searches, DROP COLUMN owner_user_id;
    ALTER TABLE public.watchspaces ALTER COLUMN token_hash SET NOT NULL;
    DROP TABLE public.app_identities;
    DROP TABLE public.app_users;
    """)
