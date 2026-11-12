"""Allow PAYPAL as a transaction source type in payment_transactions."""

from django.db import migrations

CREATE = """
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_source_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_source_type_check
    CHECK (source_type IN ('BANK_CSV', 'UPI_CSV', 'CASH_LOG', 'MANUAL', 'PAYPAL'));
"""

REVERSE = """
DELETE FROM payment_transactions WHERE source_type = 'PAYPAL';
ALTER TABLE payment_transactions DROP CONSTRAINT payment_transactions_source_type_check;
ALTER TABLE payment_transactions ADD CONSTRAINT payment_transactions_source_type_check
    CHECK (source_type IN ('BANK_CSV', 'UPI_CSV', 'CASH_LOG', 'MANUAL'));
"""


class Migration(migrations.Migration):
    dependencies = [("evidence", "0005_payment_attachment")]
    operations = [
        migrations.RunSQL(CREATE, reverse_sql=REVERSE),
    ]
