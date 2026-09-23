from django.db import migrations


def set_owners(apps, schema_editor):
    """Give every existing room an owner: whoever joined it first.

    Without this, rooms created before ownership existed would have no close
    button at all — they could never be ended.
    """
    Conversation = apps.get_model("chat", "Conversation")
    Participant = apps.get_model("chat", "Participant")

    for conversation in Conversation.objects.filter(type="ROOM", owner__isnull=True):
        first = (
            Participant.objects.filter(conversation=conversation)
            .order_by("joined_at")
            .first()
        )
        if first:
            conversation.owner_id = first.user_id
            conversation.save(update_fields=["owner"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("chat", "0002_conversation_owner")]

    operations = [migrations.RunPython(set_owners, noop)]
