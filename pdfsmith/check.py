#!/usr/bin/env python3
"""Structural checker for the PDFs pdfsmith writes.

It resolves the file the way a viewer does - xref -> catalog -> page tree ->
contents streams - and fails loudly if anything is off. Useful as a build step:

    python3 -m pdfsmith.check report.pdf

Exit status 0 means: every reference resolves, every page has a real content
stream, every font used is declared, and every page carries text.
"""
import re
import sys
import zlib


class CheckError(Exception):
    pass


def _read(path):
    with open(path, "rb") as fh:
        return fh.read()


def _objects(data):
    sx = data.rindex(b"startxref")
    offset = int(data[sx:].split()[1])
    if data[offset:offset + 4] != b"xref":
        raise CheckError("startxref does not point at an xref table")
    rows = data[offset:].split(b"\n")
    count = int(rows[1].split()[1])
    offsets = {}
    for i in range(1, count):
        parts = rows[2 + i].split()
        if len(parts) >= 3 and parts[2] == b"n":
            offsets[i] = int(parts[0])
    objects = {}
    for num, off in offsets.items():
        if not re.match(rb"%d 0 obj\n" % num, data[off:off + 24]):
            raise CheckError("object %d does not start at its xref offset" % num)
        end = data.index(b"endobj", off)
        objects[num] = data[off:end]
    return objects


def _stream(obj):
    m = re.search(rb"stream\n(.*?)\nendstream", obj, re.S)
    if not m:
        raise CheckError("object is not a stream")
    return zlib.decompress(m.group(1)) if b"/FlateDecode" in obj[:m.start()] \
        else m.group(1)


def check(path, min_chars=40, verbose=True):
    """Return a dict of findings; raise CheckError on a structural break."""
    say = print if verbose else (lambda *a, **k: None)
    data = _read(path)
    if not data.startswith(b"%PDF-"):
        raise CheckError("not a PDF file")
    if not data.rstrip().endswith(b"%%EOF"):
        raise CheckError("file does not end with %%EOF")

    objects = _objects(data)
    say("objects in xref: %d" % len(objects))

    for num, body in objects.items():
        for ref in re.findall(rb"(\d+) 0 R", body):
            if int(ref) not in objects:
                raise CheckError("object %d references missing object %s"
                                 % (num, ref.decode()))
    say("all internal references resolve: OK")

    cat_id = min(objects)
    if b"/Type /Catalog" not in objects[cat_id]:
        raise CheckError("lowest object is not the catalog")
    pages_id = int(re.search(rb"/Pages (\d+) 0 R", objects[cat_id]).group(1))
    kids = [int(k) for k in re.findall(rb"(\d+) 0 R", objects[pages_id])]
    declared = int(re.search(rb"/Count (\d+)", objects[pages_id]).group(1))
    if len(kids) != declared:
        raise CheckError("page tree says /Count %d but has %d kids"
                         % (declared, len(kids)))
    say("catalog -> page tree: %d pages" % len(kids))

    thin, total = [], 0
    for i, kid in enumerate(kids, 1):
        page = objects[kid]
        if b"/Type /Page" not in page:
            raise CheckError("page %d: kid is not a page" % i)
        fonts = {}
        for name, ref in re.findall(rb"/(F\d+) (\d+) 0 R", page):
            if b"/Type /Font" not in objects[int(ref)]:
                raise CheckError("page %d: %s does not point at a font"
                                 % (i, name.decode()))
            fonts[name] = int(ref)
        cref = re.search(rb"/Contents (\d+) 0 R", page)
        if not cref:
            raise CheckError("page %d: no /Contents" % i)
        stream = _stream(objects[int(cref.group(1))])
        for used in set(re.findall(rb"/(F\d+) [\d.]+ Tf", stream)):
            if used not in fonts:
                raise CheckError("page %d: stream uses undeclared font %s"
                                 % (i, used.decode()))
        chars = sum(len(t) for t in re.findall(rb"\((.*?)\) Tj", stream))
        total += chars
        # page 1 is often a cover with little text; every later page should
        # carry real content, which is where a broken layout shows up
        if chars < (5 if i == 1 else min_chars):
            thin.append((i, chars))

    say("drawable text: %d characters over %d pages" % (total, len(kids)))
    if thin:
        raise CheckError("pages with almost no text: %s"
                         % ", ".join("page %d (%d chars)" % p for p in thin))
    say("RESULT: OK")
    return {"pages": len(kids), "characters": total}


def _pages(objects):
    cat_id = min(objects)
    pages_id = int(re.search(rb"/Pages (\d+) 0 R", objects[cat_id]).group(1))
    return [int(k) for k in re.findall(rb"(\d+) 0 R", objects[pages_id])]


def _unescape(s):
    out, i = [], 0
    while i < len(s):
        ch = s[i:i + 1]
        if ch == b"\\" and i + 1 < len(s):
            nxt = s[i + 1:i + 2]
            if nxt in b"()\\":
                out.append(nxt)
                i += 2
                continue
            octal = re.match(rb"[0-7]{1,3}", s[i + 1:i + 4])
            if octal:
                out.append(bytes([int(octal.group(0), 8) & 0xFF]))
                i += 1 + len(octal.group(0))
                continue
        out.append(ch)
        i += 1
    return b"".join(out).decode("cp1252", "replace")


_TEXT_OP = re.compile(
    rb"BT\s+[\d.]+ [\d.]+ [\d.]+ rg\s+/\w+ [\d.]+ Tf\s+"
    rb"(-?[\d.]+) (-?[\d.]+) Td\s+\((.*?)\) Tj\s+ET", re.S)


def text_of(path):
    """The text the PDF draws, in page order, with lines rebuilt.

    Each Tj is one fragment; fragments that share a baseline are joined, so
    a paragraph comes back as a readable line instead of one word per row.
    """
    objects = _objects(_read(path))
    pages = []
    for kid in _pages(objects):
        page = objects[kid]
        cref = re.search(rb"/Contents (\d+) 0 R", page)
        if not cref:
            pages.append("")
            continue
        stream = _stream(objects[int(cref.group(1))])
        lines, current, baseline = [], [], None
        for _x, y, text in _TEXT_OP.findall(stream):
            if baseline is not None and y != baseline:
                lines.append("".join(current).strip())
                current = []
            baseline = y
            current.append(_unescape(text))
        if current:
            lines.append("".join(current).strip())
        pages.append("\n".join(ln for ln in lines if ln))
    return "\n".join(pages)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    as_text = bool(argv) and argv[0] == "--text"
    if as_text:
        argv = argv[1:]
    if len(argv) != 1:
        sys.exit("usage: python3 -m pdfsmith.check [--text] file.pdf")
    try:
        if as_text:
            print(text_of(argv[0]))
        else:
            check(argv[0])
    except (CheckError, ValueError, KeyError, IndexError, zlib.error) as exc:
        sys.exit("FAILED: %s" % exc)
    return 0


if __name__ == "__main__":
    main()
