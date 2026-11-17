# Security and privacy

The feed is public on the internet but unlisted. Its protection is a long random token in the URL plus an allowlist that exposes nothing else. That is fine for reading material you wouldn't mind a stranger seeing if the link leaked. It is not suitable for confidential documents.

## What protects you

- **Unguessable path.** The feed and audio live only under `/<token>.xml` and `/<token>/`. The token is 64 bits of randomness (`docs-` plus 16 hex characters).
- **Allowlist proxy.** Caddy answers 404 for everything except the feed, MP3 files and the cover image, so the feed server's directory listing is never reachable. See [`examples/Caddyfile.example`](../examples/Caddyfile.example).
- **Localhost binding.** The feed server listens on 127.0.0.1 only. Funnel or the tunnel connects through the proxy.
- **No new privileges** for the container.
- **Upload endpoint (optional).** If you run `scripts/install-upload.sh`, `POST /upload` is also reachable. It needs `Authorization: Bearer <UPLOAD_TOKEN>` (192 random bits, compared in constant time), only writes into the inbox, accepts only the file types the inbox builds, sanitizes filenames, and caps the size. Anyone with that token can add episodes to your feed, so rotate it (delete the line from `.env` and re-run the script) if it leaks.

## Check it

From a device not on your network:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://YOUR-HOST/            # expect 404
curl -s -o /dev/null -w '%{http_code}\n' https://YOUR-HOST/TOKEN/      # expect 404 (no listing)
curl -s -o /dev/null -w '%{http_code}\n' https://YOUR-HOST/TOKEN.xml   # expect 200
```

## What to know

- Anyone with the feed URL can subscribe and hear every episode. Don't paste it into chats, screenshots or public notes. Don't commit `.env` or your feed YAML (they're git-ignored).
- Episodes are plain files on your Mac. Don't put documents in the inbox that you wouldn't want a third party to hear.
- Choose a long token. Short or guessable ones (for example `my-podcast`) defeat the protection.

## Rotating the token

1. Generate a new one: `echo "docs-$(openssl rand -hex 8)"`.
2. Rename `podcasts/<old>-podcast.yaml` and `public/<old>/`, delete `public/<old>.xml`, and update `name:` in the YAML.
3. Update `FEED_TOKEN` in `.env`. If your shell still has the old value exported, run `unset FEED_TOKEN`.
4. Run `scripts/make-caddyfile.sh`, then `docker restart podcastify`.
5. Re-subscribe in Overcast with the new URL. The old one stops working.

## Optional: password protection

Add `basic_auth` inside the `handle @feed` block of the Caddyfile (`caddy hash-password` generates the hash), then subscribe in Overcast with the username and password. Test with a short episode first.
