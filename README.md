# docs-to-overcast

Turn documents, YouTube links and audio/video files into a private podcast feed for [Overcast](https://overcast.fm) (or any podcast app), running on your own Apple Silicon Mac.

Drop a file in a folder. A few minutes later it shows up in your podcast app, read aloud in a natural voice.

## What it does

| You drop in the inbox | You get |
|---|---|
| Markdown, text, HTML or Word (`.md` `.txt` `.html` `.docx`) | The document read aloud by [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M), a local text-to-speech model. Markup, links, tables and code blocks are cleaned up for listening. |
| A YouTube link (a `.txt` or `.url` file, or a link on the command line) | The video's audio as an MP3, with no speech generated |
| Video or audio (`.mp4` `.mov` `.mkv` `.webm` `.m4a` `.mp3` `.wav` ...) | The audio track as an MP3 |

Everything runs on your machine: no cloud text-to-speech, no subscriptions, no per-document cost.

## How it works

```
 inbox/  --->  build_episode.py  --->  public/<token>/*.mp3  --->  Podcastify  --->  Caddy allowlist  --->  Tailscale Funnel
 (files,       clean text, speak        + podcasts/<token>        builds the        serves only the        public HTTPS
  links)       with Kokoro, or          -podcast.yaml             RSS feed          feed and audio         address
               extract audio, encode                                                                           |
               MP3, add to feed                                                                                v
                                                                                                  Overcast fetches the feed
```

- **Text to speech:** [mlx-audio](https://github.com/Blaizzy/mlx-audio) running Kokoro-82M on Apple Silicon
- **Audio:** ffmpeg (MP3) and yt-dlp (YouTube)
- **Feed server:** [Podcastify](https://github.com/fnayou/podcastify) in a container (Colima, so you don't need Docker Desktop)
- **Public access:** Tailscale Funnel (or a Cloudflare Tunnel) behind a Caddy proxy that only exposes the feed and audio
- **Automation:** a launchd agent that watches the inbox

## Requirements

- A Mac with Apple Silicon (M1 or later). It runs fine on 8 GB of memory.
- [Homebrew](https://brew.sh)
- A free [Tailscale](https://tailscale.com) account (or a domain on Cloudflare) for the public feed address
- Overcast on your phone

## Quick start

```bash
git clone https://github.com/YOUR-USERNAME/docs-to-overcast.git ~/podcast
cd ~/podcast
./scripts/setup.sh            # installs tools, creates your private token and settings, starts the feed server
cp examples/sample.md inbox/
./publish.sh                  # builds your first episode (the first run downloads a ~350 MB voice model)
```

Then make the feed reachable from the internet and subscribe in Overcast. The full walkthrough is in [docs/setup.md](docs/setup.md). Once you've done that:

```bash
scripts/install-launchd.sh    # from now on, anything dropped in inbox/ is published automatically
```

## Documentation

| Guide | What's in it |
|---|---|
| [docs/setup.md](docs/setup.md) | Install, first episode, public access, subscribing in Overcast |
| [docs/configuration.md](docs/configuration.md) | Every setting in `.env` and the feed YAML, voices, audio quality |
| [docs/ingestion.md](docs/ingestion.md) | Ways to get files and links into the inbox from iPhone, Mac and browser; YouTube; audio/video |
| [docs/security.md](docs/security.md) | How the feed is protected, what it does not protect, rotating the token |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Common errors and fixes |

## Your private files are not in this repo

These are created on your machine and are git-ignored, so you can fork and pull updates safely:

- `.env` (your feed token and settings)
- `podcasts/<token>-podcast.yaml` (your feed title, author and episode list)
- `public/` (generated audio and the feed), `inbox/`, `processed/`, `work/`
- the generated Caddyfile and launchd plist

Templates for each live in [`examples/`](examples/) and [`.env.example`](.env.example).

## Limitations

- Apple Silicon only (the voice model runs on MLX).
- The feed is **unlisted, not private**: anyone with the URL can subscribe. See [docs/security.md](docs/security.md).
- Downloading from YouTube is against YouTube's terms for most content. Use it for videos you own or have permission to save, and keep your feed URL to yourself. yt-dlp needs regular updates (`brew upgrade yt-dlp`).
- English voices are the default; other Kokoro languages need extra setup (see [docs/configuration.md](docs/configuration.md)).

## Contributing

Issues and pull requests are welcome. A quick way to test changes without the voice model:

```bash
./venv/bin/python build_episode.py --stub --no-feed examples/sample.md
```

`--stub` writes a short tone instead of speech, so you can check the plumbing in seconds.

## License

MIT. See [LICENSE](LICENSE). Kokoro, mlx-audio, Podcastify, yt-dlp and ffmpeg have their own licenses.
