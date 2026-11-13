#!/bin/bash
# Install the inbox watcher: any file dropped in inbox/ is built and published automatically.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.overcastify.inbox"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents" "$ROOT/work"
sed "s#__ROOT__#$ROOT#g" "$ROOT/examples/launchd.example.plist" > "$DEST"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed $DEST"
echo "Watch it with: tail -f $ROOT/work/builder.log"
echo "Remove it with: launchctl bootout gui/$(id -u)/$LABEL"
