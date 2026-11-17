#!/bin/bash
# Generate the allowlist Caddyfile for your token and (re)start Caddy.
# Output path defaults to Homebrew's location; override with CADDYFILE=/path.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
set -a; source "$ROOT/.env"; set +a
OUT="${CADDYFILE:-/opt/homebrew/etc/Caddyfile}"
: "${FEED_TOKEN:?FEED_TOKEN is not set in .env}"

# Uploads (iOS Shortcut) only if scripts/install-upload.sh has set a token
UPLOAD_BLOCK=""
if [ -n "${UPLOAD_TOKEN:-}" ]; then
  UPLOAD_BLOCK="    handle /upload {
        request_body {
            max_size ${UPLOAD_MAX_MB:-500}MB
        }
        reverse_proxy 127.0.0.1:${UPLOAD_PORT:-8082}
    }
"
fi

cat > "$OUT" <<CADDY
:8081 {
    bind 127.0.0.1
    @feed path /${FEED_TOKEN}.xml /${FEED_TOKEN}/*.mp3 /${FEED_TOKEN}/cover.jpg
    handle @feed {
        reverse_proxy 127.0.0.1:${HOST_PORT:-18080}
    }
${UPLOAD_BLOCK}    handle {
        respond 404
    }
}
CADDY
echo "Wrote $OUT"

if command -v caddy >/dev/null; then
  caddy validate --config "$OUT" --adapter caddyfile
fi
if command -v brew >/dev/null; then
  brew services restart caddy
  sleep 2
  echo "feed via proxy: HTTP $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8081/$FEED_TOKEN.xml") (expect 200)"
  echo "root via proxy: HTTP $(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:8081/") (expect 404)"
fi
