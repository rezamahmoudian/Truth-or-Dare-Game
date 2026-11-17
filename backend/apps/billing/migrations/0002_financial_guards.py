from django.db import migrations


SQL = """
CREATE FUNCTION billing_guard_ledger() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'billing ledger is append-only' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER billing_ledger_append_only BEFORE UPDATE OR DELETE ON billing_walletledger
FOR EACH ROW EXECUTE FUNCTION billing_guard_ledger();

CREATE FUNCTION billing_guard_order_quote() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.user_id IS DISTINCT FROM OLD.user_id
       OR NEW.offer_id IS DISTINCT FROM OLD.offer_id
       OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
       OR NEW.amount IS DISTINCT FROM OLD.amount
       OR NEW.currency IS DISTINCT FROM OLD.currency
       OR NEW.product_snapshot IS DISTINCT FROM OLD.product_snapshot
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at THEN
        RAISE EXCEPTION 'billing order quote is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER billing_order_quote_immutable BEFORE UPDATE ON billing_order
FOR EACH ROW EXECUTE FUNCTION billing_guard_order_quote();

CREATE FUNCTION billing_guard_verified_payment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status = 'VERIFIED' AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'verified payment evidence is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER billing_payment_evidence_immutable BEFORE UPDATE ON billing_paymentattempt
FOR EACH ROW EXECUTE FUNCTION billing_guard_verified_payment();
"""

REVERSE = """
DROP TRIGGER IF EXISTS billing_payment_evidence_immutable ON billing_paymentattempt;
DROP FUNCTION IF EXISTS billing_guard_verified_payment();
DROP TRIGGER IF EXISTS billing_order_quote_immutable ON billing_order;
DROP FUNCTION IF EXISTS billing_guard_order_quote();
DROP TRIGGER IF EXISTS billing_ledger_append_only ON billing_walletledger;
DROP FUNCTION IF EXISTS billing_guard_ledger();
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]
    # PostgreSQL is the project's production and test database. SQL protection is
    # intentional: QuerySet.update/raw SQL must not bypass financial immutability.
    operations = [migrations.RunSQL(SQL, REVERSE)]
