# Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mlx_audio` | Using system Python, not the venv | Run `./venv/bin/python ...` from the repo folder |
| `pip: command not found` | The venv isn't active | Use `./venv/bin/pip` |
| Kokoro says `misaki` is missing | Missing text front end | `./venv/bin/pip install "misaki[en]"`; if it asks for espeak-ng, `brew install espeak-ng` |
| `no such file or directory: /venv/bin/python` | Missing the leading `./` | `./venv/bin/python` from inside the repo |
| `RuntimeError: missing .../<token>-podcast.yaml` | Feed settings file is missing, or a stale `FEED_TOKEN` is exported in your shell | Check `ls podcasts` and `grep FEED_TOKEN .env`; run `unset FEED_TOKEN` |
| Only a single tone, no words | The `--stub` test voice | Run without `--stub` |
| `docker: error getting credentials ... docker-credential-desktop` | Leftover Docker Desktop setting | Remove the `"credsStore"` line from `~/.docker/config.json` |
| `no configuration file provided: not found` | Not in the repo folder | `cd` into the repo; it contains `compose.yaml` |
| `No such container: podcastify` | Container not started | `docker-compose up -d` |
| `docker: command not found` or cannot connect | Colima isn't running | `colima start`, or `brew services restart colima` |
| Feed works locally, 502 from the public URL | Caddy isn't running or can't reach the container | `scripts/make-caddyfile.sh`; check `tailscale funnel status` and `docker ps` |
| Overcast loads the feed but shows no episodes | Audio links still say `localhost`, or Overcast cached an empty feed | `scripts/set-public-url.sh https://your-host`; then remove and re-add the podcast |
| Episode shows but won't play | `PUBLIC_BASE_URL` is wrong | Same as above; check `<enclosure>` URLs with `curl` |
| New episode is slow to appear | Overcast caches feeds | Pull to refresh; wait a few minutes |
| File sits in the inbox | launchd agent not loaded, or file still changing | `launchctl print gui/$(id -u)/com.overcastify.inbox`; `tail work/builder.log` |
| File moved to `processed/failed/` | The build raised an error | Read `work/builder.log`, fix the cause, move the file back to `inbox/` |
| YouTube download fails | yt-dlp is out of date or needs a JavaScript runtime | `brew upgrade yt-dlp`; `brew install deno` |
| Mac slows down during a build | 8 GB is tight | Build one file at a time, keep Colima at 1 GB (`COLIMA_MEMORY`), close other apps |
