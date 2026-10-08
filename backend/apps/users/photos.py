"""Bounded, re-encoded profile images; original files and EXIF are never served."""
import logging
import uuid
import warnings
from io import BytesIO

from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, Http404
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat.attachments import private_storage
from apps.core.errors import DomainError
from apps.users.models import User
from apps.users.serializers import MeSerializer

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000
logger = logging.getLogger(__name__)


def encode_photo(upload):
    from PIL import Image, ImageOps, UnidentifiedImageError
    if not upload or not upload.size or upload.size > MAX_BYTES:
        raise DomainError("invalid_photo", "یک عکس با حجم حداکثر ۵ مگابایت انتخاب کن.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in ("JPEG", "PNG", "WEBP") or source.width * source.height > MAX_PIXELS:
                    raise ValueError("unsupported image")
                source.load()
                oriented = ImageOps.exif_transpose(source)
                thumb = ImageOps.fit(oriented.convert("RGBA"), (512, 512), method=Image.Resampling.LANCZOS)
                clean = Image.new("RGB", (512, 512), "#24212f")
                clean.paste(thumb, mask=thumb.getchannel("A"))
                output = BytesIO()
                clean.save(output, "JPEG", quality=88, optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise DomainError("invalid_photo", "عکس معتبر JPG، PNG یا WebP انتخاب کن (حداکثر ۲۰ مگاپیکسل).")


def delete_photo(name):
    if name:
        try:
            private_storage().delete(f"avatars/{name}")
        except OSError:
            logger.exception("Could not remove old profile photo")


class ProfilePhotoView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]
    throttle_scope = "profile"

    def post(self, request):
        data = encode_photo(request.FILES.get("photo"))
        storage = private_storage()
        saved = storage.save(f"avatars/{uuid.uuid4().hex}.jpg", ContentFile(data))
        name = saved.removeprefix("avatars/")
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=request.user.pk)
                previous = user.profile_photo
                user.profile_photo = name
                user.save(update_fields=["profile_photo"])
                transaction.on_commit(lambda: delete_photo(previous))
        except Exception:
            storage.delete(saved)
            raise
        return Response(MeSerializer(user).data)

    def delete(self, request):
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=request.user.pk)
            previous = user.profile_photo
            user.profile_photo = ""
            user.save(update_fields=["profile_photo"])
            transaction.on_commit(lambda: delete_photo(previous))
        return Response(MeSerializer(user).data)


class ProfilePhotoFileView(APIView):
    # Public profile photos use opaque URLs, never private chat attachment paths.
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, filename):
        if not User.objects.filter(profile_photo=filename, is_active=True).exists():
            raise Http404
        try:
            file = private_storage().open(f"avatars/{filename}", "rb")
        except FileNotFoundError:
            raise Http404
        response = FileResponse(file, content_type="image/jpeg")
        response["Cache-Control"] = "no-cache"
        response["X-Content-Type-Options"] = "nosniff"
        return response
