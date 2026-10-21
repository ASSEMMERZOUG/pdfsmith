#!/usr/bin/env python3
"""Smoke tests: build real PDFs, then read them back the way a viewer would.

    python3 -m unittest discover -s tests -v
"""
import os
import shutil
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfsmith import Doc, Report, PAGE_H  # noqa: E402
from pdfsmith.check import check, text_of, CheckError  # noqa: E402


def write_png(path, w, h, rows, colour_type=2):
    def chunk(kind, body):
        return (struct.pack(">I", len(body)) + kind + body
                + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    with open(path, "wb") as fh:
        fh.write(b"\x89PNG\r\n\x1a\n"
                 + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, colour_type,
                                              0, 0, 0))
                 + chunk(b"IDAT", zlib.compress(raw, 9))
                 + chunk(b"IEND", b""))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdfsmith-test-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def path(self, name):
        return os.path.join(self.tmp, name)


class TestBuilds(Base):
    def test_minimal_document(self):
        r = Report(title="t", header="HEAD | Page %d", footer="foot")
        r.cover(kicker="Report", title=["One", "Two"],
                subtitle="A subtitle long enough to wrap onto a second line "
                         "when the page is narrow, which it is.",
                facts=[("Client", "Acme"), ("Date", "2026-10-21")],
                blurb=["Body text for the cover page."])
        r.section("1", "First")
        r.para("Hello **world** and `code`.")
        out = self.path("minimal.pdf")
        pages = r.build(out)
        self.assertGreaterEqual(pages, 2)
        info = check(out, verbose=False)
        self.assertEqual(info["pages"], pages)
        text = text_of(out)
        self.assertIn("Hello world and code.", text)
        self.assertIn("HEAD | Page 1", text)

    def test_inline_markup_keeps_spacing(self):
        r = Report()
        r.para("Do **this**, then `that`.")
        out = self.path("spacing.pdf")
        r.build(out)
        text = text_of(out)
        self.assertIn("Do this, then that.", text)
        self.assertNotIn("this ,", text)

    def test_toc_page_numbers(self):
        r = Report()
        r.cover(kicker="k", title=["Cover"])
        r.toc()
        for i in range(1, 4):
            r.section(str(i), "Section %d" % i, new_page=True)
            r.para("Body of section %d." % i)
        out = self.path("toc.pdf")
        pages = r.build(out)
        text = text_of(out)
        # cover, contents, then one page per section
        self.assertEqual(pages, 5)
        self.assertIn("Section 3", text)
        contents = text.split("3. Section 3")[0].split("1. Section 1")[-1]
        self.assertTrue(contents, "contents list should list every section")

    def test_long_content_paginates(self):
        r = Report(header="LONG | Page %d")
        r.section("1", "Long")
        for i in range(120):
            r.para("Paragraph %d with enough words to take up space on the "
                   "page and force the flow layout to start a new page, "
                   "again and again, until several pages have been filled "
                   "from top to bottom." % i)
        out = self.path("long.pdf")
        pages = r.build(out)
        self.assertGreater(pages, 4)
        check(out, verbose=False)

    def test_figure_rgb_and_rgba(self):
        rows_rgb = [bytearray([(x * 3) % 256 for x in range(64 * 3)])
                    for _ in range(40)]
        rows_rgba = [bytearray([(x * 2) % 256 for x in range(64 * 4)])
                     for _ in range(40)]
        rgb, rgba = self.path("a.png"), self.path("b.png")
        write_png(rgb, 64, 40, rows_rgb, colour_type=2)
        write_png(rgba, 64, 40, rows_rgba, colour_type=6)
        r = Report()
        r.para("Before the pictures.")
        r.figure(rgb, caption="RGB figure")
        r.figure(rgba, caption="RGBA figure")
        out = self.path("figures.pdf")
        r.build(out)
        info = check(out, verbose=False)
        self.assertIn("RGBA figure", text_of(out))
        self.assertGreater(info["characters"], 0)

    def test_low_level_doc(self):
        d = Doc(title="raw", footer="raw footer")
        d.rect(0, PAGE_H - 200, 595, 200, fill=(0.1, 0.2, 0.4))
        d.heading("Hand placed", size=18, rule=True)
        d.para("One paragraph, placed by hand.")
        d.table(["A", "B"], [["1", "2"]], widths=[1, 1])
        d.code(["python3 -V"])
        d.callout("Note", "Callouts wrap text inside a box.")
        out = self.path("raw.pdf")
        pages = d.build(out)
        self.assertEqual(pages, 1)
        check(out, verbose=False)

    def test_check_rejects_non_pdf(self):
        bad = self.path("bad.pdf")
        with open(bad, "wb") as fh:
            fh.write(b"this is not a pdf\n")
        with self.assertRaises(CheckError):
            check(bad, verbose=False)

    def test_header_percent_is_literal(self):
        r = Report(header="100%% done | Page %d")
        r.para("Percent sign in the header must survive.")
        out = self.path("pct.pdf")
        r.build(out)
        self.assertIn("100% done | Page 1", text_of(out))


if __name__ == "__main__":
    unittest.main(verbosity=2)
