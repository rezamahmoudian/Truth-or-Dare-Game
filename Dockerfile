# Liara builds from the repository root. TLS terminates at Liara's proxy.
FROM node:22-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
# The existing lockfile lacks some platform-specific optional dependencies.
RUN npm install --include=dev --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DEBUG=False \
    UVICORN_WORKERS=2 \
    CELERY_CONCURRENCY=2
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends nginx supervisor gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/ ./
COPY deploy/liara/ ./deploy/liara/
COPY --from=frontend-build /build/frontend/dist/ /srv/frontend/
COPY caddy/site/.well-known/ /srv/frontend/.well-known/
RUN sed -i 's/\r$//' /app/deploy/liara/entrypoint.sh \
    && mkdir -p /app/private_media /app/staticfiles /tmp/nginx \
    && chown app:app /app/private_media /app/staticfiles /tmp/nginx
EXPOSE 3000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=10s --start-period=120s --retries=3 \
    CMD python /app/deploy/liara/healthcheck.py
ENTRYPOINT ["sh", "/app/deploy/liara/entrypoint.sh"]
