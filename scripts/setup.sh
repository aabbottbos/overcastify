#!/bin/bash
# One-time setup on macOS (Apple Silicon): dependencies, Python venv, folders, token, feed settings,
# cover image, container runtime. Safe to re-run: it never overwrites an existing .env or feed file.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

[ "$(uname -s)" = "Darwin" ] && [ "$(uname -m)" = "arm64" ] || { echo "This project needs an Apple Silicon Mac."; exit 1; }
command -v brew >/dev/null || { echo "Install Homebrew first: https://brew.sh"; exit 1; }

echo "==> Installing tools with Homebrew"
brew install python@3.12 ffmpeg colima docker docker-compose caddy yt-dlp deno pandoc

echo "==> Creating the Python environment"
[ -d venv ] || "$(brew --prefix python@3.12)/bin/python3.12" -m venv venv
./venv/bin/pip install --upgrade pip >/dev/null
./venv/bin/pip install -r requirements.txt

echo "==> Creating folders"
mkdir -p inbox processed work public podcasts

if [ ! -f .env ]; then
  TOKEN="docs-$(openssl rand -hex 8)"
  sed "s/^FEED_TOKEN=.*/FEED_TOKEN=$TOKEN/" .env.example > .env
  echo "==> Created .env with a new feed token"
fi
set -a; source .env; set +a

FEED_YAML="podcasts/$FEED_TOKEN-podcast.yaml"
if [ ! -f "$FEED_YAML" ]; then
  sed "s/^name: .*/name: \"$FEED_TOKEN\"/" examples/podcast.example.yaml > "$FEED_YAML"
  echo "==> Created $FEED_YAML (edit the title, author and description)"
fi

mkdir -p "public/$FEED_TOKEN"
if [ ! -f "public/$FEED_TOKEN/cover.jpg" ]; then
  ffmpeg -y -loglevel error -f lavfi -i color=c=0x2c5d8f:s=1400x1400 -frames:v 1 "public/$FEED_TOKEN/cover.jpg"
  echo "==> Created a placeholder cover (replace public/$FEED_TOKEN/cover.jpg with your own square JPEG)"
fi

if grep -q '"credsStore"' "$HOME/.docker/config.json" 2>/dev/null && ! command -v docker-credential-desktop >/dev/null; then
  echo "NOTE: ~/.docker/config.json references Docker Desktop's credential helper, which is not installed."
  echo "      Remove the \"credsStore\" line from that file or image pulls will fail."
fi

echo "==> Starting the container runtime"
colima status >/dev/null 2>&1 || colima start --cpu 2 --memory "${COLIMA_MEMORY:-1}" --disk 10 --vm-type vz
docker-compose up -d

cat <<MSG

Setup finished. Next:
  1. Test the voice:       ./venv/bin/python -m mlx_audio.tts.generate --text "Hello" --voice af_heart --model mlx-community/Kokoro-82M-bf16
  2. Try an episode:       cp examples/sample.md inbox/ && ./publish.sh
  3. Make the feed public: see docs/setup.md ("Public access")
  4. Automate the inbox:   scripts/install-launchd.sh

Your feed token is stored in .env. Treat the feed URL like a password.
MSG
