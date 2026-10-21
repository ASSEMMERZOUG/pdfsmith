#!/usr/bin/env python3
"""Tests for the JSON command-line builder.

    python3 -m unittest discover -s tests -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfsmith.build import (  # noqa: E402
    SpecError, build_file, main, report_from_spec,
)
from pdfsmith.check import text_of  # noqa: E402


MINIMAL = {
    "title": "Minimal",
    "output": "out.pdf",
    "cover": {"kicker": "Test", "title": ["Minimal"]},
    "toc": True,
    "blocks": [
        {"section": {"num": "1", "title": "Summary"}},
        {"para": "One paragraph is enough to prove the pipeline works."},
        {"bullets": ["first", "second"]},
        {"table": {"headers": ["A", "B"], "rows": [["1", "2"]]}},
        {"finding": {"id": "F-01", "severity": "LOW", "title": "A finding",
                     "what": "Body text.", "fix": ["Fix it."]}},
    ],
}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="pdfsmith-cli-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def spec_path(self, spec):
        path = os.path.join(self.tmp, "report.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(spec, fh)
        return path


class BuildTest(Base):
    def test_minimal_spec_builds(self):
        path = self.spec_path(MINIMAL)
        out, pages = build_file(path)
        self.assertTrue(os.path.exists(out))
        self.assertGreaterEqual(pages, 2)
        self.assertIn("One paragraph is enough", text_of(out))

    def test_relative_output_goes_next_to_the_spec(self):
        path = self.spec_path(MINIMAL)
        out, _ = build_file(path)
        self.assertEqual(os.path.dirname(out), self.tmp)

    def test_cli_main_writes_the_file(self):
        path = self.spec_path(MINIMAL)
        target = os.path.join(self.tmp, "explicit.pdf")
        self.assertEqual(main([path, "-o", target, "-q"]), 0)
        self.assertTrue(os.path.exists(target))

    def test_cli_reports_a_bad_spec_with_exit_code(self):
        path = self.spec_path({"title": "x", "blocks": [{"nope": 1}],
                               "output": "out.pdf"})
        self.assertEqual(main([path, "-q"]), 1)


class SpecErrorTest(Base):
    def test_unknown_top_level_key(self):
        with self.assertRaises(SpecError) as ctx:
            report_from_spec({"titel": "typo", "output": "x.pdf",
                              "blocks": []}, self.tmp)
        self.assertIn("titel", str(ctx.exception))

    def test_unknown_block_names_the_index(self):
        with self.assertRaises(SpecError) as ctx:
            report_from_spec({"output": "x.pdf",
                              "blocks": [{"para": "ok"}, {"paragraf": "x"}]},
                             self.tmp)
        self.assertIn("blocks[1]", str(ctx.exception))
        self.assertIn("paragraf", str(ctx.exception))

    def test_table_row_must_match_headers(self):
        with self.assertRaises(SpecError) as ctx:
            report_from_spec({
                "output": "x.pdf",
                "blocks": [{"table": {"headers": ["A", "B"],
                                      "rows": [["only one cell"]]}}],
            }, self.tmp)
        self.assertIn("rows[0]", str(ctx.exception))

    def test_missing_output_is_an_error(self):
        with self.assertRaises(SpecError) as ctx:
            report_from_spec({"blocks": []}, self.tmp)
        self.assertIn("output", str(ctx.exception))

    def test_finding_requires_an_id(self):
        with self.assertRaises(SpecError) as ctx:
            report_from_spec({
                "output": "x.pdf",
                "blocks": [{"finding": {"severity": "LOW", "title": "t"}}],
            }, self.tmp)
        self.assertIn("id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
