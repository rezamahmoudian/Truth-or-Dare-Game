#!/bin/sh
set -eu
cd /app
python deploy/liara/preflight.py
python manage.py migrate --noinput
python manage.py collectstatic --noinput
# A mounted Liara disk may initially belong to root.
mkdir -p /app/private_media /tmp/nginx
chown app:app /app/private_media /tmp/nginx
# Supervisor opens Docker's root-owned log pipes; application children drop uid.
exec supervisord -c /app/deploy/liara/supervisord.conf
