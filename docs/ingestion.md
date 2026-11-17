# Getting content into the inbox

The inbox is just the `inbox/` folder. Anything that lands there is picked up (once it has stopped changing for a few seconds), turned into an episode, and moved to `processed/`. Failures go to `processed/failed/` with the reason in `work/builder.log`.

## What the inbox accepts

| Type | Extensions | Result |
|---|---|---|
| Documents | `.md` `.markdown` `.txt` `.html` `.docx` | Read aloud. `.html` and `.docx` need pandoc (`brew install pandoc`; the setup script installs it). |
| YouTube link | a short `.txt`, `.md`, `.url` or `.webloc` containing one link | Audio downloaded as MP3. Share-sheet text such as "Title https://youtu.be/..." works. Files over about 300 characters are treated as documents. |
| Audio and video | `.mp4` `.m4v` `.mov` `.mkv` `.webm` `.avi` `.m4a` `.mp3` `.wav` `.aac` `.flac` `.ogg` `.opus` | Audio track extracted to MP3. Existing MP3s are copied without re-encoding. |

You can also run the builder directly:

```bash
./venv/bin/python build_episode.py path/to/file.md --title "Optional title"
./venv/bin/python build_episode.py "https://youtu.be/VIDEO_ID"
```

## YouTube

Needs `yt-dlp` and a JavaScript runtime (`brew install yt-dlp deno`, done by the setup script). YouTube changes often, so run `brew upgrade yt-dlp` every few weeks. If you see "Sign in to confirm you're not a bot", yt-dlp may need cookies; see the yt-dlp documentation.

Only save videos you own or have permission to download, and keep your feed URL private.

## From your other devices

Pick whichever fits how you work. None of these are required.

**Shared folder over Tailscale (no code).** Turn on File Sharing for this Mac (System Settings > General > Sharing), share the `inbox` folder, and connect to it from your phone or laptop over Tailscale. On iPhone: Files > Browse > ... > Connect to Server > `smb://<machine>.<tailnet>.ts.net`. Then Share > Save to Files > the inbox folder. On a Mac: Finder > Go > Connect to Server.

**iCloud Drive folder.** Share > Save to Files works from iPhone, iPad and any Mac, and nothing extra is exposed on the network.

1. Create a folder in iCloud Drive, for example `Overcastify Inbox`.
2. Add it to `.env` with the full path in double quotes:
   ```bash
   PODCAST_INBOX="/Users/YOU/Library/Mobile Documents/com~apple~CloudDocs/Overcastify Inbox"
   ```
3. Run `scripts/install-launchd.sh` so the watcher follows the new folder.
4. Drop a short `.md` file into the folder. The first time, macOS asks whether Python may access iCloud Drive; click **Allow** (or grant it later in System Settings > Privacy & Security > Files and Folders). Until you do, the build waits. Upgrading Homebrew's Python can reset this permission.

Files that haven't finished downloading show up as hidden `.icloud` placeholders and are skipped until they arrive. On the Mac running the feed, turning off "Optimize Mac Storage" for iCloud Drive avoids that delay.

**Google Docs.** File > Download > Markdown (`.md`) or Plain text, into the inbox. For hands-off syncing, a tool such as `rclone` can export a Drive folder into the inbox on a schedule.

**Taildrop.** Works from iOS, but received files always land in `~/Downloads` and the folder can't be changed, so you'd need to move them into the inbox yourself.

**Claude or other tools.** Save the output as a `.md` file in the inbox.

Ideas welcome: an upload endpoint with an iOS Shortcut (one-tap share) is a good candidate for a pull request.

## Automation

`scripts/install-launchd.sh` installs a launchd agent (template: [`examples/launchd.example.plist`](../examples/launchd.example.plist)) that runs `publish.sh` whenever the inbox changes. `publish.sh` starts the feed server if it has stopped, builds everything in the inbox, and always regenerates the feed.
