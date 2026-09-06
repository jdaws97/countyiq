"""Private, capability-authenticated watches and a durable notification inbox.

Revision ID: 055
Revises: 054
"""

from alembic import op

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
    CREATE TABLE public.watchspaces (
        workspace_id UUID PRIMARY KEY,
        token_hash TEXT NOT NULL UNIQUE,
        version BIGINT NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE public.watch_items (
        workspace_id UUID NOT NULL REFERENCES public.watchspaces ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK (kind IN ('parcel','project','entity','municipality')),
        subject_key TEXT NOT NULL,
        label TEXT NOT NULL,
        added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (workspace_id, kind, subject_key)
    );
    CREATE INDEX watch_items_subject ON public.watch_items(kind, subject_key);
    CREATE TABLE public.watch_notifications (
        notification_id BIGSERIAL PRIMARY KEY,
        workspace_id UUID NOT NULL REFERENCES public.watchspaces ON DELETE CASCADE,
        event_key TEXT NOT NULL,
        event_detected_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        read_at TIMESTAMPTZ,
        UNIQUE(workspace_id,event_key)
    );
    CREATE INDEX watch_notifications_inbox ON public.watch_notifications(workspace_id, notification_id DESC);
    CREATE FUNCTION public.refresh_watch_notifications() RETURNS BIGINT
    LANGUAGE plpgsql AS $$
    DECLARE inserted BIGINT;
    BEGIN
      INSERT INTO public.watch_notifications(workspace_id,event_key,event_detected_at)
      SELECT DISTINCT w.workspace_id,e.event_key,e.detected_at
      FROM public.watch_items w
      JOIN public.intelligence_events e ON e.detected_at > w.added_at
       AND (
         (w.kind='parcel' AND w.subject_key=ANY(e.related_pidns))
         OR (w.kind='project' AND w.subject_key=e.project_key)
         OR (w.kind='municipality' AND lower(replace(w.subject_key,'_',' '))=lower(replace(e.municipality,'_',' ')))
         OR (w.kind='entity' AND EXISTS (
           SELECT 1 FROM public.owners o
           WHERE o.owner_id::text=w.subject_key AND (
             EXISTS (SELECT 1 FROM unnest(e.related_entities) name
               WHERE lower(name)=lower(o.canonical_name)
                 OR lower(name)=ANY(ARRAY(SELECT lower(alias) FROM unnest(o.aliases) alias)))
           )))
       )
      WHERE e.detected_at >= NOW()-INTERVAL '90 days'
        AND NOT (e.source_kind='delinquency_event'
          AND COALESCE(e.source_evidence->0->'details'->>'change_kind','')='new'
          AND e.detected_at=(SELECT MIN(b.detected_at) FROM public.intelligence_events b WHERE b.source_kind='delinquency_event'))
        AND NOT (e.source_kind='delinquency_event'
          AND COALESCE(e.source_evidence->0->'details'->>'change_kind','') IN ('increased','decreased')
          AND ABS(COALESCE((e.source_evidence->0->'details'->>'new_affected_total')::numeric,0)
                -COALESCE((e.source_evidence->0->'details'->>'old_affected_total')::numeric,0))
            < GREATEST(100,ABS(COALESCE((e.source_evidence->0->'details'->>'old_affected_total')::numeric,0))*0.10))
      ON CONFLICT DO NOTHING;
      GET DIAGNOSTICS inserted=ROW_COUNT;
      RETURN inserted;
    END $$;
    """)


def downgrade():
    op.execute("""
    DROP FUNCTION public.refresh_watch_notifications();
    DROP TABLE public.watch_notifications;
    DROP TABLE public.watch_items;
    DROP TABLE public.watchspaces;
    """)
