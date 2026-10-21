"""Build a report from a JSON file.

    python3 -m pdfsmith.build report.json -o report.pdf

The JSON is a fixed, small schema: document settings, an optional cover, an
optional contents page, then an ordered list of blocks. Unknown keys are an
error rather than being ignored, so a typo cannot silently drop a section from
a client-facing document.

After writing the PDF the structural checker runs; if the file would not open
in a viewer, the command exits non-zero and says why.
"""
import argparse
import json
import os
import sys

from . import __version__
from .check import CheckError, check
from .report import Report


class SpecError(ValueError):
    """The JSON does not match the schema."""


# -- small validators ------------------------------------------------------

def _fail(where, msg):
    raise SpecError("%s: %s" % (where, msg))


def _obj(body, where, allowed):
    if not isinstance(body, dict):
        _fail(where, "expected an object, got %s" % type(body).__name__)
    extra = set(body) - set(allowed)
    if extra:
        _fail(where, "unknown key(s) %s; allowed: %s"
              % (", ".join(sorted(extra)), ", ".join(sorted(allowed))))


def _str(body, key, where, default=None, required=False):
    if key not in body:
        if required:
            _fail(where, "missing required key %r" % key)
        return default
    value = body[key]
    if not isinstance(value, str):
        _fail("%s.%s" % (where, key), "expected a string")
    return value


def _num(body, key, where, default):
    if key not in body:
        return default
    value = body[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _fail("%s.%s" % (where, key), "expected a number")
    return value


def _strings(value, where):
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        _fail(where, "expected a list of strings")
    return value


def _pairs(value, where):
    if not isinstance(value, list):
        _fail(where, "expected a list of [label, value] pairs")
    out = []
    for i, item in enumerate(value):
        if not isinstance(item, list) or len(item) != 2:
            _fail("%s[%d]" % (where, i), "expected [label, value]")
        label, val = item
        if not isinstance(label, str):
            _fail("%s[%d][0]" % (where, i), "label must be a string")
        if isinstance(val, list):
            val = _strings(val, "%s[%d][1]" % (where, i))
        elif not isinstance(val, str):
            _fail("%s[%d][1]" % (where, i), "value must be a string or list")
        out.append((label, val))
    return out


# -- block handlers --------------------------------------------------------

def _block_cover(r, body, where, base):
    _obj(body, where, ("kicker", "org", "title", "subtitle", "facts",
                       "blurb", "badge"))
    title = body.get("title")
    if isinstance(title, str):
        title = [title]
    if not isinstance(title, list) or not title:
        _fail(where + ".title", "expected a non-empty list of lines")
    title = _strings(title, where + ".title")
    facts = _pairs(body.get("facts", []), where + ".facts")
    blurb = _strings(body.get("blurb", []), where + ".blurb")
    r.cover(
        kicker=_str(body, "kicker", where, ""),
        org=_str(body, "org", where),
        title=title,
        subtitle=_str(body, "subtitle", where),
        facts=facts,
        blurb=blurb,
        badge=_str(body, "badge", where),
    )


def _block_toc(r, body, where, base):
    if body is True or body is None:
        r.toc()
        return
    _obj(body, where, ("heading",))
    r.toc(heading=_str(body, "heading", where, "Contents"))


def _block_section(r, body, where, base):
    _obj(body, where, ("num", "title", "new_page"))
    num = _str(body, "num", where, required=True)
    title = _str(body, "title", where, required=True)
    new_page = body.get("new_page", "auto")
    if new_page not in (True, False, "auto"):
        _fail(where + ".new_page", 'expected true, false or "auto"')
    r.section(num, title, new_page=new_page)


def _block_pagebreak(r, body, where, base):
    r.pagebreak()


def _block_spacer(r, body, where, base):
    if isinstance(body, dict):
        _obj(body, where, ("h",))
        body = _num(body, "h", where, 12)
    elif isinstance(body, bool) or not isinstance(body, (int, float)):
        _fail(where, "expected a number of points, or {\"h\": points}")
    r.spacer(body)


def _block_h2(r, body, where, base):
    r.h2(_str({"text": body}, "text", where, required=True))


def _block_h3(r, body, where, base):
    r.h3(_str({"text": body}, "text", where, required=True))


def _block_para(r, body, where, base):
    if isinstance(body, str):
        r.para(body)
        return
    _obj(body, where, ("text", "size", "space_after"))
    r.para(_str(body, "text", where, required=True),
           size=_num(body, "size", where, 10),
           space_after=_num(body, "space_after", where, 7))


def _block_bullets(r, body, where, base):
    if isinstance(body, dict):
        _obj(body, where, ("items", "size"))
        items = _strings(body.get("items"), where + ".items")
        size = _num(body, "size", where, 9.8)
    else:
        items = _strings(body, where)
        size = 9.8
    r.bullets(items, size=size)


def _block_numbered(r, body, where, base):
    if isinstance(body, dict):
        _obj(body, where, ("items", "size"))
        items = _strings(body.get("items"), where + ".items")
        size = _num(body, "size", where, 9.8)
    else:
        items = _strings(body, where)
        size = 9.8
    r.numbered(items, size=size)


def _block_quote(r, body, where, base):
    r.quote(_str({"text": body}, "text", where, required=True))


def _block_callout(r, body, where, base):
    _obj(body, where, ("title", "text"))
    r.callout(_str(body, "title", where, required=True),
              _str(body, "text", where, required=True))


def _block_code(r, body, where, base):
    if isinstance(body, dict):
        _obj(body, where, ("lines", "size"))
        lines = _strings(body.get("lines"), where + ".lines")
        size = _num(body, "size", where, 8.2)
    else:
        lines = _strings(body, where)
        size = 8.2
    r.code(lines, size=size)


def _block_table(r, body, where, base):
    _obj(body, where, ("headers", "rows", "widths", "size"))
    headers = _strings(body.get("headers"), where + ".headers")
    rows = body.get("rows")
    if not isinstance(rows, list):
        _fail(where + ".rows", "expected a list of rows")
    clean = []
    for i, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(headers):
            _fail("%s.rows[%d]" % (where, i),
                  "expected %d cells, one per header" % len(headers))
        clean.append([str(cell) for cell in row])
    widths = body.get("widths")
    if widths is not None:
        if (not isinstance(widths, list) or len(widths) != len(headers)
                or not all(isinstance(w, (int, float)) for w in widths)):
            _fail(where + ".widths",
                  "expected %d numbers, one per column" % len(headers))
    r.table(headers, clean, widths=widths, size=_num(body, "size", where, 8.6))


def _block_figure(r, body, where, base):
    _obj(body, where, ("path", "caption", "max_h"))
    path = _str(body, "path", where, required=True)
    if not os.path.isabs(path):
        path = os.path.join(base, path)
    r.figure(path,
             caption=_str(body, "caption", where),
             max_h=_num(body, "max_h", where, 300))


def _block_kv(r, body, where, base):
    r.kv(_pairs(body, where))


def _block_finding(r, body, where, base):
    _obj(body, where, ("id", "severity", "title", "where", "what", "impact",
                       "fix", "proof"))
    fix = body.get("fix")
    proof = body.get("proof")
    r.finding(
        _str(body, "id", where, required=True),
        _str(body, "severity", where, required=True),
        _str(body, "title", where, required=True),
        where=_str(body, "where", where),
        what=_str(body, "what", where),
        impact=_str(body, "impact", where),
        fix=_strings(fix, where + ".fix") if fix is not None else None,
        proof=_strings(proof, where + ".proof") if proof is not None else None,
    )


BLOCKS = {
    "cover": _block_cover,
    "toc": _block_toc,
    "section": _block_section,
    "pagebreak": _block_pagebreak,
    "spacer": _block_spacer,
    "h2": _block_h2,
    "h3": _block_h3,
    "para": _block_para,
    "bullets": _block_bullets,
    "numbered": _block_numbered,
    "quote": _block_quote,
    "callout": _block_callout,
    "code": _block_code,
    "table": _block_table,
    "figure": _block_figure,
    "kv": _block_kv,
    "finding": _block_finding,
}

TOP_KEYS = ("title", "author", "header", "footer", "watermark", "margin",
            "top", "bottom", "cover", "toc", "blocks", "output")


def report_from_spec(spec, base_dir=None, out_path=None):
    """Turn a parsed JSON spec into a Report. Returns (report, output_path)."""
    if not isinstance(spec, dict):
        _fail("spec", "expected an object at the top level")
    extra = set(spec) - set(TOP_KEYS)
    if extra:
        _fail("spec", "unknown key(s) %s; allowed: %s"
              % (", ".join(sorted(extra)), ", ".join(sorted(TOP_KEYS))))

    r = Report(
        title=_str(spec, "title", "spec", ""),
        author=_str(spec, "author", "spec", ""),
        header=_str(spec, "header", "spec", ""),
        footer=_str(spec, "footer", "spec", ""),
        watermark=_str(spec, "watermark", "spec", ""),
        margin=_num(spec, "margin", "spec", 56),
        top=_num(spec, "top", "spec", 64),
        bottom=_num(spec, "bottom", "spec", 58),
    )

    base = base_dir or os.getcwd()

    if "cover" in spec:
        _block_cover(r, spec["cover"], "cover", base)

    if "toc" in spec:
        _block_toc(r, spec["toc"], "toc", base)

    blocks = spec.get("blocks", [])
    if not isinstance(blocks, list):
        _fail("blocks", "expected a list")
    for i, item in enumerate(blocks):
        where = "blocks[%d]" % i
        if not isinstance(item, dict) or len(item) != 1:
            _fail(where, "each block is an object with exactly one key")
        name, body = next(iter(item.items()))
        handler = BLOCKS.get(name)
        if handler is None:
            _fail(where, "unknown block %r; known blocks: %s"
                  % (name, ", ".join(sorted(BLOCKS))))
        try:
            handler(r, body, where, base)
        except SpecError as exc:
            # keep the block index visible even for errors raised lower down
            if str(exc).startswith(where):
                raise
            raise SpecError("%s: %s" % (where, exc))

    target = out_path or spec.get("output")
    if not target:
        _fail("spec", 'no output path: pass -o, or add an "output" key')
    if not os.path.isabs(target):
        target = os.path.join(base, target)
    return r, target


def build_file(spec_path, out_path=None, run_check=True):
    """Build one report from a JSON file. Returns (path, pages)."""
    with open(spec_path, encoding="utf-8") as fh:
        try:
            spec = json.load(fh)
        except ValueError as exc:
            raise SpecError("%s: not valid JSON - %s" % (spec_path, exc))
    base = os.path.dirname(os.path.abspath(spec_path))
    report, target = report_from_spec(spec, base_dir=base, out_path=out_path)
    pages = report.build(target)
    if run_check:
        check(target, verbose=False)
    return target, pages


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="pdfsmith",
        description="Build a PDF report from a JSON description.")
    parser.add_argument("spec", help="path to the report .json")
    parser.add_argument("-o", "--output", help="output PDF (overrides the spec)")
    parser.add_argument("--no-check", action="store_true",
                        help="skip the structural check after building")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="only print errors")
    parser.add_argument("--version", action="version",
                        version="pdfsmith " + __version__)
    args = parser.parse_args(argv)

    try:
        path, pages = build_file(args.spec, args.output,
                                 run_check=not args.no_check)
    except SpecError as exc:
        print("pdfsmith: %s" % exc, file=sys.stderr)
        return 1
    except (OSError, CheckError) as exc:
        print("pdfsmith: %s" % exc, file=sys.stderr)
        return 1
    if not args.quiet:
        print("wrote %s (%d page%s)" % (path, pages, "" if pages == 1 else "s"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
