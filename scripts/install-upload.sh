#!/bin/bash
# Install the upload server (for the iOS Shortcut) as a login agent and route /upload to it.
# Creates UPLOAD_TOKEN in .env if there isn't one. See docs/ingestion.md ("iOS Shortcut").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.overcastify.upload"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
cd "$ROOT"

if ! grep -q '^UPLOAD_TOKEN=' .env; then
  printf '\n# Secret for the upload endpoint (iOS Shortcut). Not the feed token.\nUPLOAD_TOKEN=%s\n' "$(openssl rand -hex 24)" >> .env
  echo "==> Created UPLOAD_TOKEN in .env"
fi
set -a; source .env; set +a

mkdir -p "$HOME/Library/LaunchAgents" work
sed "s#__ROOT__#$ROOT#g" examples/upload.example.plist > "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed $DEST (log: work/upload.log)"

scripts/make-caddyfile.sh
sleep 1
echo "upload via proxy without token: HTTP $(curl -s -o /dev/null -w '%{http_code}' -X POST -d x "http://127.0.0.1:8081/upload") (expect 401)"

cat <<MSG

Set up the iOS Shortcut with (docs/ingestion.md, "iOS Shortcut"):
  URL:    ${PUBLIC_BASE_URL%/}/upload
  Header: Authorization = Bearer <UPLOAD_TOKEN from .env>
Remove the server with: launchctl bootout gui/$(id -u)/$LABEL
MSG
