#!/usr/bin/env python3
"""Turn documents into podcast episodes.

Pipeline: read file -> clean markup for speech -> chunk -> speak with Kokoro (mlx-audio)
-> encode MP3 with ffmpeg -> add the episode to the Podcastify YAML -> regenerate the feed.

Audio and video files (.mp4 .m4v .mov .mkv .webm .m4a .mp3 .wav .flac ...) are not read aloud:
the audio track is extracted to MP3 and added to the same feed.

YouTube links (no speech): a short inbox file holding a YouTube URL (.txt, .md, .url or
.webloc), or a URL on the command line, is downloaded as MP3 audio with yt-dlp and added to
the same feed.

Usage:
  build_episode.py doc.md [more files]     build specific files
  build_episode.py https://youtu.be/ID     add a YouTube video's audio
  build_episode.py --inbox                 build everything waiting in the inbox folder
  build_episode.py --stub doc.md           fake voice (a tone) to test the plumbing fast
"""
import argparse
import datetime as dt
import fcntl
import html
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import numpy as np
import soundfile as sf

os.environ["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + os.environ.get("PATH", "")

ROOT = Path(os.environ.get("PODCAST_ROOT") or Path(__file__).resolve().parent).expanduser()
INBOX, PROCESSED, WORK = ROOT / "inbox", ROOT / "processed", ROOT / "work"
MEDIA_EXTS = {".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".m4a", ".mp3", ".wav", ".aac", ".flac", ".ogg", ".opus"}
EXTS = {".md", ".markdown", ".txt", ".docx", ".html", ".htm", ".url", ".webloc"} | MEDIA_EXTS
SR = 24000  # Kokoro output sample rate
FENCE = "`" * 3  # markdown code fence


def load_env(path):
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


ENV = {**load_env(ROOT / ".env"), **os.environ}
TOKEN = ENV.get("FEED_TOKEN", "")
MODEL = ENV.get("PODCAST_MODEL", "mlx-community/Kokoro-82M-bf16")
VOICE = ENV.get("PODCAST_VOICE", "af_heart")
LANG = ENV.get("PODCAST_LANG", "a")
SPEED = float(ENV.get("PODCAST_SPEED", "1.0"))
CONTAINER = ENV.get("PODCAST_CONTAINER", "podcastify")
YTDLP = ENV.get("YTDLP_BIN", "yt-dlp")
YT_QUALITY = ENV.get("YT_AUDIO_QUALITY", "96K")  # MP3 bitrate for YouTube audio


def log(msg):
    print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)


# ---------- text cleanup ----------

def end_sentence(s):
    s = s.strip()
    return s if not s or s[-1] in ".!?:;…\"')]" else s + "."


def strip_inline(s):
    s = re.sub(r"(\*\*|__)(.+?)\1", r"\2", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", s)
    s = re.sub(r"~~(.+?)~~", r"\1", s)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = s.replace(" & ", " and ").replace("→", " to ")
    s = re.sub(r"\s*—\s*", ", ", s)
    return re.sub(r"\s+", " ", s).strip()


def clean_for_speech(text):
    text = text.replace("\r\n", "\n")
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(rf"^({FENCE}|~~~).*?^\1[ \t]*$", "\n\nCode block omitted.\n\n", text, flags=re.S | re.M)
    text = html.unescape(re.sub(r"<[^>]+>", "", text))
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"^\[[^\]]+\]:\s+\S+.*$", "", text, flags=re.M)
    text = re.sub(r"\[\^[^\]]+\]", "", text)
    text = re.sub(r"https?://\S+", "a link", text)

    out, para, in_table = [], [], False

    def flush():
        nonlocal para
        if para:
            out.append(" ".join(para))
            para = []

    for raw in text.split("\n"):
        line = raw.strip()
        if not line or re.fullmatch(r"[-*_=]{3,}", line):
            flush()
            in_table = False
            continue
        if line.startswith("|"):
            if not in_table:
                flush()
                out.append("Table omitted.")
                in_table = True
            continue
        in_table = False
        m = re.match(r"#{1,6}\s+(.*)", line)
        if m:
            flush()
            out.append(end_sentence(strip_inline(m.group(1))))
            continue
        line = re.sub(r"^>\s?", "", line)
        item = re.match(r"(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?(.*)", line)
        if item:
            flush()
            out.append(end_sentence(strip_inline(item.group(1))))
            continue
        para.append(line)
    flush()
    return [strip_inline(p) for p in out if re.search(r"\w", p)]


def find_title(raw, fallback):
    body = re.sub(r"\A---\n.*?\n---\n", "", raw, flags=re.S)
    m = re.search(r"^#\s+(.+)$", body, flags=re.M)
    if m:
        return strip_inline(m.group(1))[:120]
    for line in body.splitlines():
        if line.strip():
            return strip_inline(re.sub(r"^[#>*\-\s]+", "", line))[:120] or fallback
    return fallback


def make_description(paragraphs, limit=280):
    text = " ".join(paragraphs[1:4] if len(paragraphs) > 1 else paragraphs)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
    return cut[: end + 1] if end > 80 else cut.rsplit(" ", 1)[0] + "…"


def slugify(s, n=60):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:n] or "episode"


def new_mp3_path(title):
    media = ROOT / "public" / TOKEN
    media.mkdir(parents=True, exist_ok=True)
    stem = f"{dt.date.today():%Y-%m-%d}-{slugify(title)}"
    mp3, n = media / f"{stem}.mp3", 2
    while mp3.exists():
        mp3, n = media / f"{stem}-{n}.mp3", n + 1
    return mp3


# ---------- chunking and speech ----------

SENT = re.compile(r"(?<=[.!?])\s+")


def split_long(s, limit):
    if len(s) <= limit:
        return [s]
    parts, cur = [], ""
    for w in s.split(" "):
        if cur and len(cur) + 1 + len(w) > limit:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    parts.append(cur)
    return parts


def chunks(par, limit=350):
    out, cur = [], ""
    for s in SENT.split(par):
        for piece in split_long(s, limit):
            if cur and len(cur) + 1 + len(piece) > limit:
                out.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip()
    if cur:
        out.append(cur)
    return out


class StubTTS:
    """A quiet tone about as long as the text would take to read. For plumbing tests."""

    def speak(self, text):
        n = int(SR * max(0.4, len(text) * 0.055))
        t = np.arange(n) / SR
        return (0.08 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


class KokoroTTS:
    def __init__(self, model_id, voice, speed, lang):
        from mlx_audio.tts.utils import load_model

        log(f"loading {model_id}")
        self.model, self.voice, self.speed, self.lang = load_model(model_id), voice, speed, lang

    def speak(self, text):
        parts = [
            np.array(r.audio, dtype=np.float32).reshape(-1)
            for r in self.model.generate(text=text, voice=self.voice, speed=self.speed, lang_code=self.lang)
        ]
        return np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)


def render(paragraphs, tts, wav_path):
    gap_s = np.zeros(int(SR * 0.15), dtype=np.float32)
    gap_p = np.zeros(int(SR * 0.7), dtype=np.float32)
    total, done, t0, last = sum(len(p) for p in paragraphs), 0, time.time(), -1
    with sf.SoundFile(str(wav_path), "w", samplerate=SR, channels=1, subtype="PCM_16") as f:
        for par in paragraphs:
            for i, ch in enumerate(chunks(par)):
                if i:
                    f.write(gap_s)
                f.write(tts.speak(ch))
            f.write(gap_p)
            done += len(par)
            pct = done * 100 // total
            if pct // 10 != last // 10:
                log(f"  speaking {pct}% ({time.time() - t0:.0f}s elapsed)")
                last = pct


def encode_mp3(wav, mp3, title, album):
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "1", "-ar", "44100",
         "-codec:a", "libmp3lame", "-b:a", "64k", "-id3v2_version", "3",
         "-metadata", f"title={title}", "-metadata", f"album={album}", str(mp3)],
        check=True,
    )


# ---------- feed ----------

def add_episode(cfg_path, mp3_name, title, desc):
    import yaml

    cfg = yaml.safe_load(cfg_path.read_text()) or {}
    cfg["episodes"] = (cfg.get("episodes") or []) + [{
        "file": mp3_name,
        "title": title,
        "description": desc,
        "pub_date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "episode_type": "full",
    }]
    tmp = cfg_path.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(cfg, sort_keys=False, allow_unicode=True, width=1000))
    tmp.replace(cfg_path)


def feed_title(cfg_path):
    import yaml

    return (yaml.safe_load(cfg_path.read_text()) or {}).get("title", "Podcast")


def regenerate_feed():
    for cmd in (["docker", "exec", CONTAINER, "python", "/app/app.py", "generate"],
                ["docker", "restart", CONTAINER]):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
        except FileNotFoundError:
            break
        if r.returncode == 0:
            log("feed regenerated")
            return True
        log(f"  '{' '.join(cmd[:3])}' failed: {r.stderr.strip()[:200]}")
    log("WARNING: feed not regenerated. Run: docker restart " + CONTAINER)
    return False


# ---------- driver ----------

def read_source(path):
    if path.suffix.lower() in {".docx", ".html", ".htm"}:
        if not shutil.which("pandoc"):
            raise RuntimeError(f"pandoc is needed for {path.suffix} files: brew install pandoc")
        return subprocess.run(["pandoc", str(path), "-t", "gfm", "--wrap=none"],
                              capture_output=True, text=True, check=True).stdout
    return path.read_text(encoding="utf-8", errors="replace")


# ---------- YouTube ----------

YT_RE = re.compile(
    r"https?://(?:www\.|m\.|music\.)?(?:youtube\.com/(?:watch\?\S*?v=|shorts/|live/|embed/)"
    r"|youtu\.be/)[\w-]{11}[^\s<>\"']*"
)


def find_youtube_url(text):
    m = YT_RE.search(text)
    return m.group(0).rstrip(".,;:)") if m else None


def youtube_url_from_file(path):
    """A small inbox file that is just a YouTube link: shared text, .url or .webloc."""
    suffix = path.suffix.lower()
    if suffix not in {".txt", ".md", ".markdown", ".url", ".webloc"} or path.stat().st_size > 4000:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if suffix in {".url", ".webloc"} or len(text.strip()) < 300:
        return find_youtube_url(text)
    return None


def process_youtube(url, args):
    log(f"downloading audio: {url}")
    if not shutil.which(YTDLP):
        raise RuntimeError("yt-dlp is needed for YouTube links: brew install yt-dlp deno")
    cfg_path = ROOT / "podcasts" / f"{TOKEN}-podcast.yaml"
    if not cfg_path.exists():
        raise RuntimeError(f"missing {cfg_path}")

    r = subprocess.run(
        [YTDLP, "--no-playlist", "-x", "--audio-format", "mp3", "--audio-quality", YT_QUALITY,
         "--no-warnings", "--print-json", "-o", str(WORK / "yt-%(id)s.%(ext)s"), url],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError("yt-dlp failed: " + (r.stderr.strip()[-600:] or "no error output"))
    lines = [ln for ln in r.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        raise RuntimeError("yt-dlp printed no video information")
    info = json.loads(lines[-1])
    audio = WORK / f"yt-{info['id']}.mp3"
    if not audio.exists():
        raise RuntimeError(f"expected {audio.name} after the download")

    title = args.title or info.get("title") or f"YouTube {info['id']}"
    log(f"  title: {title} ({int(info.get('duration') or 0) // 60} min)")
    mp3 = new_mp3_path(title)
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(audio), "-vn", "-codec:a", "copy",
         "-id3v2_version", "3", "-metadata", f"title={title}",
         "-metadata", f"album={feed_title(cfg_path)}",
         "-metadata", f"artist={info.get('uploader') or ''}", str(mp3)],
        check=True,
    )
    audio.unlink(missing_ok=True)

    body = " ".join((info.get("description") or "").split())
    desc = make_description([body]) if body else ""
    who = info.get("uploader") or "YouTube"
    desc = f"{who}. {desc} Source: {info.get('webpage_url') or url}".replace(".. ", ". ")
    add_episode(cfg_path, mp3.name, title, desc)
    log(f"  wrote {mp3.name} ({mp3.stat().st_size / 1e6:.1f} MB)")


# ---------- audio and video files ----------

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "format=duration:format_tags=title,artist,comment,description:stream=codec_type,codec_name",
         "-of", "json", str(path)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        raise RuntimeError("could not read this media file: " + (r.stderr.strip()[-300:] or "ffprobe failed"))
    return json.loads(r.stdout or "{}")


def process_media(path, args):
    log(f"extracting audio: {path.name}")
    cfg_path = ROOT / "podcasts" / f"{TOKEN}-podcast.yaml"
    if not cfg_path.exists():
        raise RuntimeError(f"missing {cfg_path}")
    info = probe(path)
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio:
        raise RuntimeError("this file has no audio track")
    tags = {k.lower(): v for k, v in (info.get("format", {}).get("tags") or {}).items()}
    title = args.title or tags.get("title") or re.sub(r"[_\s]+", " ", path.stem).strip() or "Recording"
    minutes = int(float(info.get("format", {}).get("duration") or 0) // 60)
    log(f"  title: {title} ({minutes} min)")

    mp3 = new_mp3_path(title)
    already_mp3 = audio[0].get("codec_name") == "mp3"
    codec = ["-codec:a", "copy"] if already_mp3 else ["-codec:a", "libmp3lame", "-b:a", YT_QUALITY]
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-vn", "-map", "0:a:0", "-map_metadata", "-1",
         *codec, "-id3v2_version", "3", "-metadata", f"title={title}",
         "-metadata", f"album={feed_title(cfg_path)}", "-metadata", f"artist={tags.get('artist', '')}", str(mp3)],
        check=True,
    )
    note = " ".join((tags.get("description") or tags.get("comment") or "").split())
    add_episode(cfg_path, mp3.name, title, make_description([note]) if note else f"Audio from {path.name}.")
    log(f"  wrote {mp3.name} ({mp3.stat().st_size / 1e6:.1f} MB)")


# ---------- documents ----------

def process(path, tts, args):
    url = youtube_url_from_file(path)
    if path.suffix.lower() in MEDIA_EXTS:
        process_media(path, args)
    elif url:
        process_youtube(url, args)
    elif path.suffix.lower() in {".url", ".webloc"}:
        raise RuntimeError("no YouTube link found in this shortcut file")
    else:
        process_text(path, tts, args)
    if path.parent == INBOX:  # only tidy up files that came from the inbox
        shutil.move(str(path), PROCESSED / f"{dt.datetime.now():%Y%m%d-%H%M%S}-{path.name}")


def process_text(path, tts, args):
    log(f"building: {path.name}")
    raw = read_source(path)
    title = args.title or find_title(raw, path.stem)
    paragraphs = clean_for_speech(raw)
    if not paragraphs:
        raise RuntimeError("nothing speakable in this file")
    if title.rstrip(".").lower() not in paragraphs[0].lower():
        paragraphs.insert(0, end_sentence(title))
    log(f"  title: {title} ({sum(len(p) for p in paragraphs)} characters)")

    mp3 = new_mp3_path(title)
    wav = WORK / f"{mp3.stem}.wav"

    cfg_path = ROOT / "podcasts" / f"{TOKEN}-podcast.yaml"
    if not cfg_path.exists():
        raise RuntimeError(f"missing {cfg_path}")

    render(paragraphs, tts(), wav)
    encode_mp3(wav, mp3, title, feed_title(cfg_path))
    wav.unlink(missing_ok=True)
    add_episode(cfg_path, mp3.name, title, make_description(paragraphs))
    log(f"  wrote {mp3.name} ({mp3.stat().st_size / 1e6:.1f} MB)")


def inbox_files(settle):
    now, ready, waiting = time.time(), [], False
    for p in sorted(INBOX.iterdir()):
        if p.name.startswith(".") or not p.is_file() or p.suffix.lower() not in EXTS:
            continue
        if now - p.stat().st_mtime < settle:
            waiting = True
        else:
            ready.append(p)
    return ready, waiting


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="document files and/or YouTube URLs")
    ap.add_argument("--inbox", action="store_true", help="process everything in the inbox folder")
    ap.add_argument("--stub", action="store_true", help="use a fake voice (tone) to test the plumbing")
    ap.add_argument("--title", help="override the episode title (single file)")
    ap.add_argument("--no-feed", action="store_true", help="skip regenerating the feed")
    ap.add_argument("--settle", type=int, default=5, help="seconds a file must be unchanged (inbox mode)")
    args = ap.parse_args()

    if not TOKEN:
        sys.exit(f"FEED_TOKEN is not set. Add FEED_TOKEN=... to {ROOT / '.env'}")
    for d in (INBOX, PROCESSED, WORK):
        d.mkdir(parents=True, exist_ok=True)
    lock = open(WORK / ".lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("another build is running; it will pick up new files")
        return

    engine = None

    def tts():
        nonlocal engine
        if engine is None:
            engine = StubTTS() if args.stub else KokoroTTS(MODEL, VOICE, SPEED, LANG)
        return engine

    def run(item):
        is_url = isinstance(item, str)
        try:
            if is_url:
                url = find_youtube_url(item)
                if not url:
                    raise RuntimeError("only YouTube links are supported as URLs")
                process_youtube(url, args)
            else:
                process(item, tts, args)
            return True
        except Exception:
            log(f"FAILED: {item if is_url else item.name}\n{traceback.format_exc()}")
            if not is_url and item.parent == INBOX:
                (PROCESSED / "failed").mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), PROCESSED / "failed" / item.name)
            return False

    built = False
    for f in args.files:
        built |= run(f if f.startswith(("http://", "https://")) else Path(f).expanduser().resolve())
    if args.inbox:
        waits = 0
        while True:
            ready, waiting = inbox_files(args.settle)
            if ready:
                for f in ready:
                    built |= run(f)
                waits = 0
            elif waiting and waits < 20:
                time.sleep(3)
                waits += 1
            else:
                break
    if built and not args.no_feed:
        regenerate_feed()


if __name__ == "__main__":
    main()
