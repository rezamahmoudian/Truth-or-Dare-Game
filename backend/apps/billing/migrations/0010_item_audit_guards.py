from django.db import migrations


SQL = """
CREATE TRIGGER billing_item_use_append_only BEFORE UPDATE OR DELETE ON billing_itemuse
FOR EACH ROW EXECUTE FUNCTION billing_guard_ledger();

CREATE FUNCTION billing_guard_inventory() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'inventory source is immutable' USING ERRCODE = '23514';
    END IF;
    IF NEW.user_id IS DISTINCT FROM OLD.user_id OR NEW.item_id IS DISTINCT FROM OLD.item_id
       OR NEW.order_id IS DISTINCT FROM OLD.order_id OR NEW.reward_key IS DISTINCT FROM OLD.reward_key
       OR NEW.snapshot IS DISTINCT FROM OLD.snapshot OR NEW.quantity IS DISTINCT FROM OLD.quantity
       OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.remaining > OLD.remaining THEN
        RAISE EXCEPTION 'inventory source is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER billing_inventory_source_guard BEFORE UPDATE OR DELETE ON billing_inventorygrant
FOR EACH ROW EXECUTE FUNCTION billing_guard_inventory();

CREATE FUNCTION game_guard_free_prompt() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.pack_id IS NULL AND NEW.pack_id IS NOT NULL THEN
        RAISE EXCEPTION 'existing free prompts cannot become paid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END; $$;
CREATE TRIGGER game_free_prompt_guard BEFORE UPDATE ON game_prompt
FOR EACH ROW EXECUTE FUNCTION game_guard_free_prompt();
"""

REVERSE = """
DROP TRIGGER IF EXISTS game_free_prompt_guard ON game_prompt;
DROP FUNCTION IF EXISTS game_guard_free_prompt();
DROP TRIGGER IF EXISTS billing_inventory_source_guard ON billing_inventorygrant;
DROP FUNCTION IF EXISTS billing_guard_inventory();
DROP TRIGGER IF EXISTS billing_item_use_append_only ON billing_itemuse;
"""


class Migration(migrations.Migration):
    dependencies = [("billing", "0009_rewardsession"), ("game", "0009_gamesession_prompt_pack_prompt_pack")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
