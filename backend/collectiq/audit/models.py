"""Read model for audit events. Rows are written only by `audit.record`; the table is built in SQL."""
from django.contrib.postgres.fields import ArrayField
from django.db import models


class AuditEvent(models.Model):
    id = models.BigIntegerField(primary_key=True)
    workspace_id = models.UUIDField()
    occurred_at = models.DateTimeField()
    actor_type = models.TextField()
    actor_id = models.UUIDField(null=True)
    action = models.TextField()
    object_type = models.TextField()
    object_id = models.TextField()
    before_masked = models.JSONField(null=True)
    after_masked = models.JSONField(null=True)
    reason_codes = ArrayField(models.TextField(), null=True)
    evidence_refs = models.JSONField(null=True)
    policy_decision_id = models.UUIDField(null=True)
    correlation_id = models.TextField()
    prev_hash = models.BinaryField(null=True)
    hash = models.BinaryField()

    class Meta:
        managed = False
        db_table = "audit_events"
