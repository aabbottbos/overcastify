# Setup

## 1. Install

```bash
git clone https://github.com/YOUR-USERNAME/docs-to-overcast.git ~/podcast
cd ~/podcast
./scripts/setup.sh
```

The script installs the tools with Homebrew, creates a Python environment, generates your private feed token in `.env`, writes your feed settings from [`examples/podcast.example.yaml`](../examples/podcast.example.yaml), makes a placeholder cover image, and starts the feed server in a container. It never overwrites an existing `.env` or feed file.

Afterwards, open `podcasts/<token>-podcast.yaml` and set your feed title, author and description. Replace `public/<token>/cover.jpg` with a square JPEG between 1400 and 3000 pixels.

If image pulls fail with `docker-credential-desktop: executable file not found`, remove the `"credsStore"` line from `~/.docker/config.json` (left over from Docker Desktop).

## 2. Test the voice

```bash
./venv/bin/python -m mlx_audio.tts.generate --text "This is a test." --voice af_heart --model mlx-community/Kokoro-82M-bf16
```

The first run downloads about 350 MB. If it says `misaki` is missing, run `./venv/bin/pip install "misaki[en]"`.

## 3. Build a first episode

```bash
cp examples/sample.md inbox/
./publish.sh
```

Then check the local feed:

```bash
set -a; source .env; set +a
curl -s http://127.0.0.1:18080/$FEED_TOKEN.xml | grep -E '<title>|<enclosure'
```

You should see your episode with an `<enclosure>` line. To test the plumbing without speech, use `./venv/bin/python build_episode.py --stub examples/sample.md`.

## 4. Public access

Overcast fetches your feed from its own servers, so the feed needs a public HTTPS address. Only the feed and the audio should be reachable, so a small Caddy proxy sits in front and answers 404 to everything else.

**Allowlist proxy:**

```bash
scripts/make-caddyfile.sh
```

This writes a Caddyfile containing your token (see [`examples/Caddyfile.example`](../examples/Caddyfile.example)), restarts Caddy, and tests it. You should see `HTTP 200` for the feed and `HTTP 404` for the root.

**Tailscale Funnel (recommended):**

1. In the Tailscale admin console, enable MagicDNS and HTTPS certificates, and allow Funnel for this machine.
2. Run `tailscale funnel --bg 8081`, then `tailscale funnel status` to see your public address (`https://<machine>.<tailnet>.ts.net`).
3. Point the feed at it:
   ```bash
   scripts/set-public-url.sh https://<machine>.<tailnet>.ts.net
   ```
4. Open the printed URL in Safari on cellular. You should see XML.

Funnel serves TLS on ports 443, 8443 and 10000 only and applies bandwidth limits you can't change. Check Tailscale's [Funnel docs](https://tailscale.com/kb/1223/funnel) for how your Tailscale build exposes the CLI.

**Alternative: Cloudflare Tunnel** (if you own a domain on Cloudflare):

```bash
brew install cloudflared
cloudflared tunnel login
cloudflared tunnel create podcast-feed
cloudflared tunnel route dns podcast-feed podcast.example.com
```

Create `~/.cloudflared/config.yml` pointing at the proxy, not the container:

```yaml
tunnel: podcast-feed
credentials-file: /Users/YOU/.cloudflared/<tunnel-id>.json
ingress:
  - hostname: podcast.example.com
    service: http://127.0.0.1:8081
  - service: http_status:404
```

Then `cloudflared tunnel run podcast-feed` to test and `cloudflared service install` to run it at login. Finish with `scripts/set-public-url.sh https://podcast.example.com`.

## 5. Subscribe in Overcast

On your iPhone: **+** > **Add URL** > paste `https://<your-host>/<token>.xml`.

A tap-to-subscribe link also works: `overcast://x-callback-url/add?url=<your feed URL>`.

New episodes can take a few minutes to appear. Pull to refresh the podcast to speed it up.

## 6. Automate the inbox

```bash
scripts/install-launchd.sh
```

From then on, anything dropped in `inbox/` is built and published. Watch progress with `tail -f work/builder.log`. The agent runs in your login session, so enable automatic login if this is a headless machine. Colima and Caddy come back after a reboot because they run under `brew services`:

```bash
brew services start colima
brew services start caddy
```
