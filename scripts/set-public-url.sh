#!/bin/bash
# Point the feed at your public address, then recreate the container and rebuild the feed.
# Usage: scripts/set-public-url.sh https://my-mac.my-tailnet.ts.net
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
URL="${1:?usage: scripts/set-public-url.sh https://your-public-host}"
case "$URL" in https://*) ;; *) echo "The public URL must start with https://"; exit 1;; esac
URL="${URL%/}"

if grep -q '^PUBLIC_BASE_URL=' .env; then
  sed -i '' "s#^PUBLIC_BASE_URL=.*#PUBLIC_BASE_URL=$URL#" .env
else
  echo "PUBLIC_BASE_URL=$URL" >> .env
fi
set -a; source .env; set +a
docker-compose up -d --force-recreate
docker exec podcastify python /app/app.py generate
echo
echo "Subscribe in Overcast (+ > Add URL) with:"
echo "  $URL/$FEED_TOKEN.xml"
