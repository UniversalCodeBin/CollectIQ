"""MATCH_REVIEW: a case the system opens when a confirmed payment overpaid an invoice (FR-057)."""

from django.db import migrations

UP = """
ALTER TABLE cases DROP CONSTRAINT cases_type_check;
ALTER TABLE cases ADD CONSTRAINT cases_type_check
    CHECK (type IN ('DISPUTE', 'MISSING_DOCUMENT', 'QUESTION', 'PROPOSAL', 'MATCH_REVIEW'));
-- One open review per invoice: a second overpayment while it is open adds nothing.
CREATE UNIQUE INDEX cases_one_open_match_review ON cases (invoice_id)
    WHERE type = 'MATCH_REVIEW' AND status <> 'RESOLVED';
"""

DOWN = """
DROP INDEX cases_one_open_match_review;
ALTER TABLE cases DROP CONSTRAINT cases_type_check;
ALTER TABLE cases ADD CONSTRAINT cases_type_check
    CHECK (type IN ('DISPUTE', 'MISSING_DOCUMENT', 'QUESTION', 'PROPOSAL'));
"""


class Migration(migrations.Migration):
    dependencies = [("cases", "0001_cases")]
    operations = [migrations.RunSQL(UP, reverse_sql=DOWN)]
