from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.errors import DomainError


def exception_handler(exc, context):
    """Turn domain errors into the same shape the WebSocket sends.

    `{"code": ..., "detail": ...}` over HTTP mirrors the socket's
    `error` event, so the client has one way to read a rejection regardless of
    which transport produced it.
    """
    if isinstance(exc, DomainError):
        return Response({"code": exc.code, "detail": exc.message}, status=exc.status)
    return drf_exception_handler(exc, context)
