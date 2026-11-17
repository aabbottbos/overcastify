"""Tests for the parts of build_episode.py that don't need the voice model, Docker or the network.

Run: ./venv/bin/python -m unittest discover tests
"""
import datetime as dt
import errno
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import yaml

import build_episode as b

FENCE = "`" * 3


class CleanForSpeech(unittest.TestCase):
    def test_markup_is_removed(self):
        text = "# Title\n\nSome **bold** and [a link](https://x.y) and `code`.\n"
        self.assertEqual(b.clean_for_speech(text), ["Title.", "Some bold and a link and code."])

    def test_code_blocks_and_tables_are_announced(self):
        text = f"Intro.\n\n{FENCE}python\nprint(1)\n{FENCE}\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\nOutro."
        self.assertEqual(b.clean_for_speech(text), ["Intro.", "Code block omitted.", "Table omitted.", "Outro."])

    def test_list_items_become_sentences(self):
        self.assertEqual(b.clean_for_speech("- one\n- two\n1. three"), ["one.", "two.", "three."])

    def test_front_matter_and_bare_urls(self):
        text = "---\ntitle: x\n---\nSee https://example.com/page now."
        self.assertEqual(b.clean_for_speech(text), ["See a link now."])


class TitlesAndChunks(unittest.TestCase):
    def test_find_title_prefers_h1(self):
        self.assertEqual(b.find_title("intro\n# Real *Title*\n", "fallback"), "Real Title")
        self.assertEqual(b.find_title("\n\nFirst line\n", "fallback"), "First line")
        self.assertEqual(b.find_title("", "fallback"), "fallback")

    def test_chunks_respect_limit(self):
        par = " ".join(["word"] * 400) + ". Short sentence."
        parts = b.chunks(par, limit=100)
        self.assertTrue(all(len(p) <= 100 for p in parts))
        self.assertEqual(" ".join(parts), par)


class Links(unittest.TestCase):
    def test_youtube_wins_over_other_links(self):
        text = "see https://example.com and https://youtu.be/dQw4w9WgXcQ."
        self.assertEqual(b.find_url(text), "https://youtu.be/dQw4w9WgXcQ")

    def test_article_link(self):
        self.assertEqual(b.find_url("Good read: https://example.com/a/b?c=1)."), "https://example.com/a/b?c=1")
        self.assertIsNone(b.find_url("no links here"))

    def test_url_from_file(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "a.webloc").write_text('<plist><dict><key>URL</key><string>https://example.com/x</string></dict></plist>')
            (d / "b.txt").write_text("Title https://example.com/y")
            (d / "c.txt").write_text("long document " * 40 + " https://example.com/z")
            self.assertEqual(b.url_from_file(d / "a.webloc"), "https://example.com/x")
            self.assertEqual(b.url_from_file(d / "b.txt"), "https://example.com/y")
            self.assertIsNone(b.url_from_file(d / "c.txt"))  # a document that mentions a link

    def test_article_byline(self):
        self.assertEqual(
            b.article_byline("https://en.wikipedia.org/wiki/X", "X - Wikipedia", "Wikimedia Foundation, Inc.",
                             "Authority control databases International GND FAST National United States"),
            ("X", "Wikipedia", None))
        self.assertEqual(b.article_byline("https://www.theverge.com/a", "Thing | The Verge", "The Verge", "Jane Doe"),
                         ("Thing", "The Verge", "Jane Doe"))
        # a dash that isn't a site suffix stays
        self.assertEqual(b.article_byline("https://blog.example.com/p", "Python - A guide", None, None)[0],
                         "Python - A guide")


class Pdf(unittest.TestCase):
    def test_clean_pdf_text(self):
        raw = "A para-\ngraph here.\n\n12\n\fNext page\nvii\ncivil\n"
        out = b.clean_pdf_text(raw)
        self.assertIn("paragraph here.", out)
        self.assertNotIn("12", out)
        self.assertNotIn("vii", out)
        self.assertIn("civil", out)
        self.assertNotIn("\f", out)


class Inbox(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = Path(self.tmp.name)
        self.patch = mock.patch.object(b, "INBOX", self.inbox)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_synced_file_with_old_mtime_still_settles(self):
        f = self.inbox / "video.mp4"
        f.write_bytes(b"x")
        old = time.time() - 86400
        os.utime(f, (old, old))  # like a file synced from a phone: old mtime, fresh ctime
        self.assertEqual(b.inbox_files(settle=30), ([], True))
        self.assertEqual(b.inbox_files(settle=0), ([f], False))

    def test_skips_hidden_unknown_dirs_and_pending(self):
        for name in (".hidden.md", "notes.xyz", "doc.md"):
            (self.inbox / name).write_text("x")
        (self.inbox / "Failed").mkdir()
        doc = self.inbox / "doc.md"
        self.assertEqual(b.inbox_files(settle=0), ([doc], False))
        self.assertEqual(b.inbox_files(settle=0, skip={doc}), ([], True))

    def test_not_downloaded(self):
        self.assertTrue(b.not_downloaded(OSError(errno.EDEADLK, "Resource deadlock avoided")))
        try:
            try:
                raise OSError(errno.EDEADLK, "x")
            except OSError as e:
                raise RuntimeError("could not read this media file") from e
        except RuntimeError as e:
            self.assertTrue(b.not_downloaded(e))
        self.assertTrue(b.not_downloaded(RuntimeError("ffprobe: Resource deadlock avoided")))
        self.assertFalse(b.not_downloaded(RuntimeError("nothing speakable")))


class Failures(unittest.TestCase):
    def test_record_failure_moves_file_and_writes_reason(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            src = d / "bad.md"
            src.write_text("x")
            with mock.patch.object(b, "FAILED", d / "failed"), mock.patch.object(b, "notify") as note:
                reason = b.record_failure("bad.md", "Traceback...\nRuntimeError: nothing speakable", src)
            self.assertEqual(reason, "nothing speakable")
            self.assertFalse(src.exists())
            moved = sorted(p.name for p in (d / "failed").iterdir())
            self.assertEqual(len(moved), 2)
            self.assertTrue(moved[0].endswith("-bad.md") and moved[1].endswith("-bad.md.error.txt"))
            note.assert_called_once()

    def test_record_failure_for_url_has_safe_filename(self):
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(b, "FAILED", Path(d)), mock.patch.object(b, "notify"):
                b.record_failure("https://example.com/a/b", "RuntimeError: nope")
            (note,) = Path(d).iterdir()
            self.assertNotIn("/", note.name)
            self.assertTrue(note.name.endswith(".error.txt"))


class Pruning(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.media = self.d / "media"
        self.media.mkdir()
        self.cfg = self.d / "feed.yaml"
        eps = []
        for i, day in enumerate((1, 5, 10, 20)):
            name = f"ep{i}.mp3"
            (self.media / name).write_bytes(b"x")
            eps.append({"file": name, "title": f"ep{i}", "pub_date": f"2026-11-{day:02d}T12:00:00Z"})
        (self.media / "cover.jpg").write_bytes(b"x")
        self.cfg.write_text(yaml.safe_dump({"title": "T", "episodes": eps}))
        self.now = dt.datetime(2026, 11, 21, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.tmp.cleanup()

    def kept(self):
        return [e["title"] for e in yaml.safe_load(self.cfg.read_text())["episodes"]]

    def test_off_by_default(self):
        self.assertEqual(b.prune_episodes(self.cfg, self.media), [])
        self.assertEqual(len(self.kept()), 4)

    def test_keep_newest(self):
        removed = b.prune_episodes(self.cfg, self.media, keep=2, now=self.now)
        self.assertEqual([e["title"] for e in removed], ["ep0", "ep1"])
        self.assertEqual(self.kept(), ["ep2", "ep3"])
        self.assertEqual(sorted(p.name for p in self.media.iterdir()), ["cover.jpg", "ep2.mp3", "ep3.mp3"])

    def test_keep_days(self):
        b.prune_episodes(self.cfg, self.media, days=12, now=self.now)
        self.assertEqual(self.kept(), ["ep2", "ep3"])

    def test_prune_processed_uses_name_timestamp(self):
        folder = self.d / "processed"
        folder.mkdir()
        old, new = folder / "20261101-090000-a.mp4", folder / "20261120-090000-b.md"
        for p in (old, new, folder / ".gitkeep"):
            p.write_text("x")
        os.utime(new, (0, 0))  # mtime doesn't matter, the name does
        (folder / "failed").mkdir()
        b.prune_processed(folder, days=7, now=dt.datetime(2026, 11, 21))
        self.assertEqual(sorted(p.name for p in folder.iterdir()), [".gitkeep", new.name, "failed"])


if __name__ == "__main__":
    unittest.main()
