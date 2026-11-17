# Configuration

All settings live in `.env` (copied from [`.env.example`](../.env.example) by `scripts/setup.sh`). Real environment variables override `.env`.

| Setting | Default | Meaning |
|---|---|---|
| `FEED_TOKEN` | generated | Secret path part of your feed URL. Keep it long and random. |
| `HOST_PORT` | `18080` | Local port the feed server listens on (127.0.0.1 only) |
| `PORT` | `8080` | Port inside the container |
| `PUBLIC_BASE_URL` | `http://localhost:18080` | Address used inside the feed for audio links. Set to your public https URL (`scripts/set-public-url.sh`). |
| `RUN_ON_START` / `PUBLISH_XML` | `true` | Podcastify behavior; leave as is |
| `PODCAST_VOICE` | `af_heart` | Kokoro voice |
| `PODCAST_LANG` | `a` | Kokoro language code (`a` American English, `b` British English) |
| `PODCAST_SPEED` | `1.0` | Speaking speed (0.8 slower to 1.3 faster) |
| `PODCAST_MODEL` | `mlx-community/Kokoro-82M-bf16` | Model repository |
| `YT_AUDIO_QUALITY` | `96K` | MP3 bitrate for YouTube and audio/video files (about 43 MB per hour at 96K) |
| `PODCAST_ROOT` | the repo folder | Where inbox, public and podcasts live |
| `PODCAST_FAILED` | `processed/failed/` | Where failed files and their `.error.txt` notes go. A folder inside an iCloud inbox (for example `.../Overcastify Inbox/Failed`) lets you see failures on your phone. |
| `PODCAST_NOTIFY` | `true` | macOS notification when a file fails. `false` to turn off. |
| `PODCAST_KEEP_EPISODES` | `0` (keep all) | Keep only the newest N episodes. Older ones leave the feed and their MP3s are deleted. |
| `PODCAST_KEEP_DAYS` | `0` (keep all) | Remove episodes older than N days, the same way |
| `PROCESSED_KEEP_DAYS` | `0` (keep all) | Delete source files in `processed/` (documents, videos) N days after they were built. Failed files are kept. |
| `UPLOAD_TOKEN` | created by `scripts/install-upload.sh` | Secret for the upload endpoint (iOS Shortcut). Separate from `FEED_TOKEN`. |
| `UPLOAD_PORT` | `8082` | Local port of the upload server |
| `UPLOAD_MAX_MB` | `500` | Largest upload accepted. Re-run `scripts/make-caddyfile.sh` after changing it. |
| `PODCAST_INBOX` | `inbox/` in the repo | Folder to watch for new files, e.g. one in iCloud Drive. Use a full path in double quotes and re-run `scripts/install-launchd.sh` after changing it. |
| `YTDLP_BIN` | `yt-dlp` | Path to yt-dlp |
| `PODCAST_CONTAINER` | `podcastify` | Container name used for feed regeneration |

Documents are encoded at 64 kbps mono, about 29 MB per hour, which is plenty for speech.

## Voices

American English voices include `af_heart`, `af_bella`, `af_nicole`, `am_michael` and `am_fenrir`; British English (`PODCAST_LANG=b`) include `bf_emma` and `bm_george`. Try a few with the command-line test in [setup.md](setup.md) and keep the one you like. Other languages need extra Kokoro dependencies; see the [mlx-audio](https://github.com/Blaizzy/mlx-audio) documentation.

## Feed settings

Edit `podcasts/<token>-podcast.yaml` (template: [`examples/podcast.example.yaml`](../examples/podcast.example.yaml)): `title`, `author-name`, `author-email`, `description`, `language`, `explicit`, `image`, `categories`. Don't add an `episodes:` list by hand; `build_episode.py` adds one entry per episode. Once the list exists, Podcastify publishes only the episodes in it.

To remove an episode, delete its entry from `episodes:`, delete its MP3 from `public/<token>/`, then run `docker restart podcastify`.

## Episode titles and descriptions

- **Documents:** the first `# Heading` is the title. Without one, the first line is used. `--title "..."` overrides it for a single file.
- **Audio/video files:** the file's title tag if present, otherwise the file name (`voice_memo_2026.m4a` becomes "voice memo 2026").
- **YouTube:** the video title, with the channel and source link in the description.

## Updating

```bash
git pull
./venv/bin/pip install -U -r requirements.txt
brew upgrade yt-dlp
```

To change the Podcastify version, edit the image tag in `compose.yaml`, then `docker-compose pull && docker-compose up -d`.
