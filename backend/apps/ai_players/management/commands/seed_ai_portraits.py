"""Install bundled fictional portraits through the regular profile photo storage."""
import uuid
from pathlib import Path

from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.ai_players.models import Persona
from apps.chat.attachments import private_storage
from apps.users.models import User
from apps.users.photos import encode_photo


PORTRAITS = [
    ("رها", "نیک‌منش", "raha.png"),
    ("نیلا", "مهرآیین", "nila.png"),
    ("تارا", "رادفر", "tara.png"),
]


class Command(BaseCommand):
    help = "Add bundled AI portraits to existing seed personas without replacing their current photos."

    def handle(self, *args, **options):
        folder = Path(__file__).resolve().parents[2] / "assets" / "portraits"
        added = 0
        for first_name, last_name, filename in PORTRAITS:
            personas = Persona.objects.filter(first_name=first_name, last_name=last_name)
            if personas.count() != 1:
                self.stdout.write(f"Skipped {first_name}: expected exactly one matching persona.")
                continue
            persona = personas.get()
            storage = private_storage()
            saved = None
            try:
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=persona.user_id)
                    if user.profile_photo:
                        self.stdout.write(f"Kept existing photo: {first_name}")
                        continue
                    with (folder / filename).open("rb") as source:
                        data = encode_photo(File(source, name=filename))
                    saved = storage.save(f"avatars/{uuid.uuid4().hex}.jpg", ContentFile(data))
                    user.profile_photo = saved.removeprefix("avatars/")
                    user.save(update_fields=["profile_photo"])
            except Exception:
                if saved:
                    storage.delete(saved)
                raise
            added += 1
            self.stdout.write(f"Photo added: {first_name}")
        self.stdout.write(self.style.SUCCESS(f"{added} portraits installed."))
