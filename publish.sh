#!/bin/bash
# Build episodes from the inbox and regenerate the feed.
# Run by hand, or automatically by launchd (scripts/install-launchd.sh).
set -uo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
cd "$(cd "$(dirname "$0")" && pwd)" || exit 1
set -a; source .env; set +a

echo "$(date '+%H:%M:%S') publish start"

# make sure the feed server is running
docker ps --format '{{.Names}}' | grep -qx podcastify || docker-compose up -d

# turn every file in the inbox into an episode
./venv/bin/python build_episode.py --inbox --settle 5

# always regenerate the feed, even if nothing new was built
docker exec podcastify python /app/app.py generate || docker restart podcastify

code=$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${HOST_PORT:-18080}/$FEED_TOKEN.xml")
echo "$(date '+%H:%M:%S') local feed: HTTP $code"
