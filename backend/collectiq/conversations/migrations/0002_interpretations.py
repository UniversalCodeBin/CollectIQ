"""What a model read in a customer reply, kept apart from anything a person decided.

An interpretation is AI-derived and unverified. It never marks anything paid. The processing record
keeps only hashes and metadata, never the redacted text itself.
"""

from django.db import migrations

from collectiq.platform.rls import enable_rls

CREATE = """
CREATE TABLE ai_processing_records (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    task_id text NOT NULL,
    subject_type text NOT NULL,
    subject_id uuid,
    provider text,
    model_version text,
    input_sha256 text,
    status text NOT NULL,
    attempts integer NOT NULL DEFAULT 0,
    repaired boolean NOT NULL DEFAULT false,
    dropped_fields text[] NOT NULL DEFAULT '{}',
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (workspace_id, id)
);
CREATE INDEX ai_processing_subject ON ai_processing_records (workspace_id, subject_type, subject_id);

CREATE TABLE message_interpretations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id uuid NOT NULL REFERENCES workspaces (id),
    message_id uuid NOT NULL,
    status text NOT NULL DEFAULT 'PENDING_REVIEW' CHECK (status IN
        ('PENDING_REVIEW', 'ACCEPTED', 'DISMISSED', 'CORRECTED', 'NEEDS_MANUAL_REVIEW')),
    derived_by text NOT NULL DEFAULT 'AI' CHECK (derived_by = 'AI'),
    labels text[] NOT NULL DEFAULT '{}',
    primary_label text,
    confidence text CHECK (confidence IN ('LOW', 'MEDIUM', 'HIGH')),
    evidence_span text CHECK (char_length(evidence_span) <= 1000),
    date_hint text CHECK (char_length(date_hint) <= 200),
    date_status text NOT NULL DEFAULT 'NONE' CHECK (date_status IN ('NONE', 'RESOLVED', 'AMBIGUOUS')),
    resolved_date date,
    date_note text,
    failure_code text,
    applied jsonb NOT NULL DEFAULT '[]',
    processing_record_id uuid,
    decided_by uuid REFERENCES users (id),
    decided_at timestamptz,
    decision_note text CHECK (char_length(decision_note) <= 1000),
    corrected_labels text[],
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (workspace_id, message_id) REFERENCES messages (workspace_id, id),
    CONSTRAINT decided_by_a_person CHECK (status IN ('PENDING_REVIEW', 'NEEDS_MANUAL_REVIEW')
        OR decided_by IS NOT NULL),
    UNIQUE (workspace_id, id)
);
CREATE INDEX message_interpretations_message ON message_interpretations (workspace_id, message_id, created_at DESC);
"""

DROP = """
DROP TABLE message_interpretations;
DROP TABLE ai_processing_records;
"""


class Migration(migrations.Migration):
    dependencies = [("conversations", "0001_conversations")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=DROP),
        enable_rls("ai_processing_records"),
        enable_rls("message_interpretations"),
    ]
