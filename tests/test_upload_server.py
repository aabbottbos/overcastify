"""Tests for upload_server.py against a real server on a random local port.

Run: ./venv/bin/python -m unittest discover tests
"""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import upload_server as u

TOKEN = "t" * 48


class UploadServer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.inbox, work = root / "inbox", root / "work"
        self.inbox.mkdir()
        self.patches = [mock.patch.object(u, "INBOX", self.inbox), mock.patch.object(u, "WORK", work),
                        mock.patch.object(u, "TOKEN", TOKEN), mock.patch.object(u, "MAX_BYTES", 1000),
                        mock.patch.object(u, "log", lambda msg: None)]
        for p in self.patches:
            p.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), u.Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def post(self, body, path="/upload", token=TOKEN, ctype="application/octet-stream", headers=None):
        req = urllib.request.Request(self.base + path, data=body, method="POST",
                                     headers={"Content-Type": ctype, **(headers or {})})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def files(self):
        return sorted(p.name for p in self.inbox.iterdir())

    def test_rejects_bad_token_and_paths(self):
        self.assertEqual(self.post(b"x", token=None)[0], 401)
        self.assertEqual(self.post(b"x", token="wrong")[0], 401)
        self.assertEqual(self.post(b"x", path="/other")[0], 404)
        self.assertEqual(self.files(), [])

    def test_file_upload_with_name(self):
        code, body = self.post(b"# Hi\n\nText.", path="/upload?name=My%20Notes.md", ctype="text/markdown")
        self.assertEqual(code, 200)
        (name,) = self.files()
        self.assertTrue(name.endswith("-My Notes.md"))
        self.assertEqual(body["saved"], name)

    def test_extension_from_content_type(self):
        self.assertEqual(self.post(b"%PDF-1.4", ctype="application/pdf")[0], 200)
        self.assertTrue(self.files()[0].endswith("-upload.pdf"))

    def test_path_tricks_are_neutralised(self):
        self.post(b"x", headers={"X-Filename": "../../etc/evil.md"})
        (name,) = self.files()
        self.assertTrue(name.endswith("-evil.md"))

    def test_unsupported_type(self):
        code, _ = self.post(b"MZ", path="/upload?name=setup.exe")
        self.assertEqual(code, 415)
        self.assertEqual(self.files(), [])

    def test_links_become_link_files(self):
        self.assertEqual(self.post(json.dumps({"url": "https://example.com/a"}).encode(),
                                   ctype="application/json")[0], 200)
        self.assertEqual(self.post(b"Look https://youtu.be/dQw4w9WgXcQ", ctype="text/plain")[0], 200)
        texts = [(self.inbox / f).read_text().strip() for f in self.files()]
        self.assertEqual(sorted(texts), ["https://example.com/a", "https://youtu.be/dQw4w9WgXcQ"])

    def test_long_text_is_a_document(self):
        self.assertEqual(self.post(b"word " * 100, ctype="text/plain")[0], 200)
        self.assertTrue(self.files()[0].endswith("-upload.txt"))

    def test_too_large(self):
        self.assertEqual(self.post(b"x" * 2000, path="/upload?name=a.md")[0], 413)
        self.assertEqual(self.files(), [])


if __name__ == "__main__":
    unittest.main()
