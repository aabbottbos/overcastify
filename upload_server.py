#!/usr/bin/env python3
"""Accept files and links over HTTPS and drop them in the inbox, for a one-tap iOS Shortcut.

  POST /upload   Authorization: Bearer <UPLOAD_TOKEN>

The request body is one of:
  - a file (any type the inbox accepts), named by ?name=<filename> or an X-Filename header
  - JSON {"url": "https://..."} or a short text/plain body holding a link
  - longer text/plain, saved as a .txt document to be read aloud

Listens on 127.0.0.1 only; Caddy forwards /upload to it (scripts/make-caddyfile.sh).
Install as a login agent with scripts/install-upload.sh.
"""
import datetime as dt
import hmac
import json
import mimetypes
import re
import shutil
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from build_episode import ENV, EXTS, INBOX, WORK, find_url, log

TOKEN = ENV.get("UPLOAD_TOKEN", "")
PORT = int(ENV.get("UPLOAD_PORT") or 8082)
MAX_BYTES = int(ENV.get("UPLOAD_MAX_MB") or 500) * 1024 * 1024
# Types iOS sends that mimetypes doesn't map to the extension we want
TYPE_EXTS = {"text/markdown": ".md", "text/plain": ".txt", "video/quicktime": ".mov", "audio/x-m4a": ".m4a",
             "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "text/html": ".html", "application/pdf": ".pdf",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx"}


def safe_name(name, content_type):
    """A filesystem-safe inbox filename with an accepted extension, or None."""
    name = Path(unquote(name or "")).name
    name = re.sub(r"[^\w.\- ]+", "_", name).strip(" .")[:120]
    ctype = (content_type or "").split(";")[0].strip().lower()
    ext = Path(name).suffix.lower()
    if ext not in EXTS:
        guessed = TYPE_EXTS.get(ctype) or mimetypes.guess_extension(ctype) or ""
        if guessed not in EXTS:
            return None
        name, ext = f"{name or 'upload'}{guessed}", guessed
    stamp = f"{dt.datetime.now():%Y%m%d-%H%M%S}"
    return f"{stamp}-{name}" if name else None


def deliver(data_path, name):
    """Move a finished upload into the inbox in one step, so the watcher never sees half a file."""
    dest = INBOX / name
    n = 2
    while dest.exists():
        dest = INBOX / f"{Path(name).stem}-{n}{Path(name).suffix}"
        n += 1
    shutil.move(str(data_path), dest)
    return dest


class Handler(BaseHTTPRequestHandler):
    server_version = "overcastify-upload"

    def reply(self, code, **body):
        data = json.dumps({"ok": code == 200, **body}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):  # one line per request, without the client address
        log("upload: " + fmt % args)

    def do_GET(self):
        self.reply(404, error="not found")

    def do_POST(self):
        url = urlparse(self.path)
        if url.path.rstrip("/") != "/upload":
            return self.reply(404, error="not found")
        auth = self.headers.get("Authorization", "")
        if not TOKEN or not hmac.compare_digest(auth.encode(), f"Bearer {TOKEN}".encode()):
            return self.reply(401, error="bad or missing token")
        try:
            length = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            length = -1
        if length < 1:
            return self.reply(411, error="empty body or no Content-Length")
        if length > MAX_BYTES:
            return self.reply(413, error=f"larger than {MAX_BYTES // 1024 // 1024} MB")

        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        name = (parse_qs(url.query).get("name") or [None])[0] or self.headers.get("X-Filename")

        WORK.mkdir(parents=True, exist_ok=True)
        tmp = WORK / f"upload-{dt.datetime.now():%H%M%S%f}.part"
        try:
            with open(tmp, "wb") as f:
                left = length
                while left:
                    chunk = self.rfile.read(min(left, 1 << 20))
                    if not chunk:
                        return self.reply(400, error="upload ended early")
                    f.write(chunk)
                    left -= len(chunk)

            if ctype in {"application/json", "text/plain", "application/x-www-form-urlencoded"} and length < 20000:
                text = tmp.read_text(encoding="utf-8", errors="replace")
                if ctype == "application/json":
                    try:
                        text = str(json.loads(text).get("url") or "")
                    except (ValueError, AttributeError):
                        return self.reply(400, error='expected JSON like {"url": "https://..."}')
                link = find_url(text) if len(text.strip()) < 300 else None
                if link:
                    tmp.write_text(link + "\n")
                    dest = deliver(tmp, f"{dt.datetime.now():%Y%m%d-%H%M%S}-link.txt")
                    return self.reply(200, saved=dest.name, url=link)
                if ctype == "application/json":
                    return self.reply(400, error="no link in the JSON body")

            final = safe_name(name, ctype)
            if not final:
                return self.reply(415, error=f"unsupported file type ({name or ctype or 'unknown'})")
            dest = deliver(tmp, final)
            return self.reply(200, saved=dest.name)
        finally:
            tmp.unlink(missing_ok=True)


def main():
    if not TOKEN or len(TOKEN) < 24:
        sys.exit("UPLOAD_TOKEN is missing or too short in .env. Run scripts/install-upload.sh")
    INBOX.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log(f"upload server on 127.0.0.1:{PORT}, saving to {INBOX}")
    server.serve_forever()


if __name__ == "__main__":
    main()
