"""WSGI entrypoint.

Kept only for tooling that expects it. The application is served over ASGI —
see config/asgi.py.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_wsgi_application()
