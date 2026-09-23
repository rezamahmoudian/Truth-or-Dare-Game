#!/usr/bin/env bash
# Checks the production stack the way a phone and a store reviewer would see it.
#
#   bash scripts/verify_prod.sh                    # against http://localhost
#   bash scripts/verify_prod.sh https://your.domain
#
# What this cannot check is service worker registration: that needs a real
# browser. Open the site in Chrome, then DevTools → Application → Service
# Workers should show sw.js as "activated and running".
set -u
B=${1:-http://localhost}
pass=0; fail=0
ok()  { echo "PASS  $1${2:+  — $2}"; pass=$((pass+1)); }
bad() { echo "FAIL  $1${2:+  — $2}"; fail=$((fail+1)); }

header() { curl -s -D - -o /dev/null "$B$1" | tr -d '\r' | grep -i "^$2:" | head -1 | cut -d' ' -f2-; }
status() { curl -s -o /dev/null -w "%{http_code}" "$B$1"; }

# --- the app is served ------------------------------------------------------
[ "$(status /)" = "200" ] && ok "the app shell is served" || bad "the app shell is served" "$(status /)"
curl -s "$B/" | grep -q 'lang="fa" dir="rtl"' && ok "the shell is the RTL Persian build" || bad "the shell is the RTL Persian build"

# Client-side routes must survive a hard refresh.
[ "$(status /chats)" = "200" ] && ok "a deep link to /chats serves the shell" || bad "a deep link to /chats serves the shell"
[ "$(status /c/some-room-id)" = "200" ] && ok "a deep link to a room serves the shell" || bad "a deep link to a room serves the shell"

# --- PWA ---------------------------------------------------------------------
[ "$(status /manifest.webmanifest)" = "200" ] && ok "manifest is served" || bad "manifest is served"
M=$(curl -s "$B/manifest.webmanifest")
echo "$M" | grep -q '"display":"standalone"' && ok "manifest declares standalone display" || bad "manifest declares standalone display"
echo "$M" | grep -q '"dir":"rtl"' && ok "manifest is RTL" || bad "manifest is RTL"
echo "$M" | grep -q '"purpose":"maskable"' && ok "manifest has a maskable icon" || bad "manifest has a maskable icon"

for icon in icon-192.png icon-512.png maskable-512.png apple-touch-icon.png; do
  [ "$(status /icons/$icon)" = "200" ] && ok "icon $icon reachable" || bad "icon $icon reachable"
done

[ "$(status /sw.js)" = "200" ] && ok "service worker is served" || bad "service worker is served"
[ "$(header /sw.js Content-Type | cut -d';' -f1)" = "text/javascript" ] || [ "$(header /sw.js Content-Type | cut -d';' -f1)" = "application/javascript" ] \
  && ok "service worker has a script content type" "$(header /sw.js Content-Type)" \
  || bad "service worker has a script content type" "$(header /sw.js Content-Type)"

# --- caching: the part that decides whether updates ever reach anyone -----------
[ "$(header /sw.js Cache-Control)" = "no-cache" ] && ok "sw.js is never cached — updates can reach installed apps" || bad "sw.js is never cached" "$(header /sw.js Cache-Control)"
[ "$(header /index.html Cache-Control)" = "no-cache" ] && ok "index.html is never cached" || bad "index.html is never cached" "$(header /index.html Cache-Control)"
ASSET=$(curl -s "$B/" | grep -oE '/assets/index-[^"]+\.js' | head -1)
[ -n "$ASSET" ] && echo "$(header "$ASSET" Cache-Control)" | grep -q immutable \
  && ok "hashed assets are cached forever" "$ASSET" \
  || bad "hashed assets are cached forever" "$ASSET"

[ "$(status '/fonts/Vazirmatn%5Bwght%5D.woff2')" = "200" ] && ok "the font is self-hosted and reachable" || bad "the font is self-hosted and reachable"

# --- backend through the proxy --------------------------------------------------
[ "$(status /api/health/)" = "200" ] && ok "API is reachable through Caddy" || bad "API is reachable through Caddy"
[ "$(status /static/admin/css/base.css)" = "200" ] && ok "Django static files are served by Caddy" || bad "Django static files are served by Caddy" "$(status /static/admin/css/base.css)"

# --- TWA -------------------------------------------------------------------------
[ "$(status /.well-known/assetlinks.json)" = "200" ] && ok "assetlinks.json is at the path Android checks" || bad "assetlinks.json is at the path Android checks"
[ "$(header /.well-known/assetlinks.json Content-Type)" = "application/json" ] && ok "assetlinks.json is served as JSON" || bad "assetlinks.json is served as JSON" "$(header /.well-known/assetlinks.json Content-Type)"

# --- security headers -------------------------------------------------------------
[ -n "$(header / X-Content-Type-Options)" ] && ok "nosniff header present" || bad "nosniff header present"
[ "$(header / X-Frame-Options)" = "DENY" ] && ok "the app cannot be framed" || bad "the app cannot be framed"
[ -z "$(header / Server)" ] && ok "server banner is hidden" || bad "server banner is hidden" "$(header / Server)"

# --- nothing but Caddy is exposed -------------------------------------------------
# Checked on the containers' own port mappings, not by probing host sockets: a
# developer machine can have its own Postgres on 5432, which says nothing about
# what this deployment publishes.
for svc in db redis backend frontend worker beat; do
  published=$(docker port "ft-$svc-1" 2>/dev/null)
  if [ -z "$published" ]; then
    ok "$svc publishes no ports"
  else
    bad "$svc publishes no ports" "$published"
  fi
done
caddy_ports=$(docker port ft-caddy-1 2>/dev/null | cut -d' ' -f1 | sort -u | tr '
' ' ')
echo "$caddy_ports" | grep -q "80/tcp" && ok "only Caddy is published" "$caddy_ports" || bad "only Caddy is published" "$caddy_ports"

# --- Django is really in production mode ------------------------------------------
BODY=$(curl -s "$B/api/does-not-exist/")
echo "$BODY" | grep -qi "traceback\|DEBUG = True\|URLconf" && bad "no debug pages leak" || ok "no debug pages leak"

echo
echo "$pass passed, $fail failed"
