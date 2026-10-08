import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage

from apps.core.errors import DomainError


def private_storage():
    return FileSystemStorage(location=settings.PRIVATE_MEDIA_ROOT)


def inspect_upload(upload, voice=False):
    if not upload.size or upload.size > settings.CHAT_UPLOAD_MAX_BYTES:
        raise DomainError("invalid_file_size", "فایل باید بین ۱ بایت و ۲۵ مگابایت باشد.")
    head = upload.read(64)
    upload.seek(0)
    kind, mime = "file", "application/octet-stream"
    if head.startswith(b"\xff\xd8\xff"):
        kind, mime = "image", "image/jpeg"
    elif head.startswith(b"\x89PNG\r\n\x1a\n"):
        kind, mime = "image", "image/png"
    elif head.startswith((b"GIF87a", b"GIF89a")):
        kind, mime = "image", "image/gif"
    elif head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        kind, mime = "image", "image/webp"
    elif head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        kind, mime = "audio", "audio/wav"
    elif head.startswith(b"OggS"):
        kind, mime = "audio", "audio/ogg"
    elif head.startswith(b"ID3") or (len(head) > 1 and head[0] == 255 and head[1] & 224 == 224):
        kind, mime = "audio", "audio/mpeg"
    elif head.startswith(b"\x1a\x45\xdf\xa3"):
        kind, mime = ("audio", "audio/webm") if voice else ("video", "video/webm")
    elif head[4:8] == b"ftyp":
        kind, mime = ("audio", "audio/mp4") if voice or Path(upload.name).suffix.lower() == ".m4a" else ("video", "video/mp4")
    if voice:
        if kind != "audio":
            raise DomainError("invalid_voice", "فرمت فایل صوتی قابل قبول نیست.")
        kind = "voice"
    name = Path(upload.name.replace("\\", "/")).name[:180] or "file"
    info = {"name": name, "size": upload.size, "kind": kind, "mime": mime}
    return f"chat/{uuid.uuid4().hex}", info
