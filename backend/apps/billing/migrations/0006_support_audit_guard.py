from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_supportoperation_alter_order_options_and_more")]
    operations = [migrations.RunSQL(
        """CREATE TRIGGER billing_support_append_only
        BEFORE UPDATE OR DELETE ON billing_supportoperation
        FOR EACH ROW EXECUTE FUNCTION billing_guard_ledger();""",
        "DROP TRIGGER IF EXISTS billing_support_append_only ON billing_supportoperation;",
    )]
