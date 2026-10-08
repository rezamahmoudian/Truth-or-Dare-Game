"""Read-only verification; run via manage.py shell with exec(open(...).read())."""
from io import BytesIO

from PIL import Image
from rest_framework.test import APIRequestFactory

from apps.ai_players.models import Persona
from apps.chat.models import Message
from apps.chat.payloads import message_payload
from apps.users.payloads import person_payload
from apps.users.photos import ProfilePhotoFileView

factory = APIRequestFactory()
for persona in Persona.objects.select_related("user"):
    user = persona.user
    assert user.avatar_url and person_payload(user)["avatar_url"] == user.avatar_url
    response = ProfilePhotoFileView.as_view()(factory.get(user.avatar_url), filename=user.profile_photo)
    assert response.status_code == 200
    data = b"".join(response.streaming_content)
    with Image.open(BytesIO(data)) as image:
        assert image.size == (512, 512) and image.format == "JPEG"
    response.close()
    message = Message.objects.filter(sender=user).first()
    if message:
        assert message_payload(message)["sender"]["avatar_url"] == user.avatar_url
    print(persona.first_name, len(data), "bytes; photo endpoint and profile/chat payload OK")
