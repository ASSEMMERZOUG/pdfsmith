#!/usr/bin/env python3
"""Minimal PDF generator using only the standard library.

Renders a block-based document model to a PDF using the base-14 fonts
(no embedding, no external dependencies).
"""
import re
import struct
import time
import zlib

PAGE_W, PAGE_H = 595, 842  # A4 in points

# --- Helvetica / Helvetica-Bold AFM widths (units per 1000) -----------------
HELV = {
    " ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667,
    "'": 191, "(": 333, ")": 333, "*": 389, "+": 584, ",": 278, "-": 333,
    ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584, ">": 584,
    "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556,
    "`": 333, "{": 334, "|": 260, "}": 334, "~": 584,
}
HELV.update({chr(c): 556 for c in range(ord("0"), ord("9") + 1)})
HELV.update({
    "A": 667, "B": 667, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 500, "K": 667, "L": 556, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 556, "c": 500, "d": 556, "e": 556, "f": 278, "g": 556,
    "h": 556, "i": 222, "j": 222, "k": 500, "l": 222, "m": 833, "n": 556,
    "o": 556, "p": 556, "q": 556, "r": 333, "s": 500, "t": 278, "u": 556,
    "v": 500, "w": 722, "x": 500, "y": 500, "z": 500,
})
HELV_B = dict(HELV)
HELV_B.update({
    "!": 333, '"': 474, "&": 722, "'": 238, "?": 611, "@": 975,
    "A": 722, "B": 722, "C": 722, "D": 722, "E": 667, "F": 611, "G": 778,
    "H": 722, "I": 278, "J": 556, "K": 722, "L": 611, "M": 833, "N": 722,
    "O": 778, "P": 667, "Q": 778, "R": 722, "S": 667, "T": 611, "U": 722,
    "V": 667, "W": 944, "X": 667, "Y": 667, "Z": 611,
    "a": 556, "b": 611, "c": 556, "d": 611, "e": 556, "f": 333, "g": 611,
    "h": 611, "i": 278, "j": 278, "k": 556, "l": 278, "m": 889, "n": 611,
    "o": 611, "p": 611, "q": 611, "r": 389, "s": 556, "t": 333, "u": 611,
    "v": 556, "w": 778, "x": 556, "y": 556, "z": 500,
    "[": 333, "]": 333, "^": 584, "`": 333, "{": 389, "|": 280, "}": 389,
})
FONTS = {"regular": ("F1", HELV), "bold": ("F2", HELV_B),
         "mono": ("F3", None), "mono_bold": ("F4", None)}


def width_of(text, font_key, size):
    table = FONTS[font_key][1]
    if table is None:  # Courier: fixed 600/1000
        return 0.6 * size * len(text)
    return sum(table.get(ch, 556) for ch in text) * size / 1000.0


def esc(text):
    out = []
    for ch in text:
        if ch in "()\\":
            out.append("\\" + ch)
        else:
            code = ord(ch)
            if 32 <= code <= 126:
                out.append(ch)
            else:
                try:
                    out.append("\\%03o" % ch.encode("cp1252")[0])
                except UnicodeEncodeError:
                    out.append("?")
    return "".join(out)


def inline_tokens(text, base_font="regular", code_font="mono"):
    """Split **bold** and `code` markers into (text, font_key) tokens."""
    tokens = []
    for part in re.split(r"(\*\*.+?\*\*|`[^`]+`)", text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            key = "bold" if base_font == "regular" else base_font
            tokens.append((part[2:-2], key))
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            tokens.append((part[1:-1], code_font))
        else:
            tokens.append((part, base_font))
    return tokens


# --- PNG images -------------------------------------------------------------
# Screenshots arrive as PNG. PDF's FlateDecode predictor 15 expects exactly the
# same layout as a PNG's filtered scanlines, so a decoded (human-readable) PNG
# row block can be re-deflated straight into an image XObject. The only real
# work is undoing the per-row filters, which is what makes the alpha channel
# separable from the colour data.

_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}
_PNG_SPACE = {0: "DeviceGray", 2: "DeviceRGB", 3: "DeviceRGB",
              4: "DeviceGray", 6: "DeviceRGB"}


def _paeth(a, b, c):
    p = a + b - c
    pa = p - a if p >= a else a - p
    pb = p - b if p >= b else b - p
    pc = p - c if p >= c else c - p
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def load_png(path):
    """Decode an 8-bit non-interlaced PNG to PDF-ready sample streams.

    Returns a dict with w, h, colours (component count), space (PDF colour
    space name), samples (the colour bytes) and smask (alpha bytes, or None).
    Both byte strings are uncompressed; the caller deflates them.
    """
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG: %s" % path)

    pos, idat, plte = 8, bytearray(), None
    w = h = depth = ctype = interlace = None
    while pos + 8 <= len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        typ, body = data[pos + 4:pos + 8], data[pos + 8:pos + 8 + n]
        pos += 12 + n
        if typ == b"IHDR":
            w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            plte = body
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break

    if depth != 8:
        raise ValueError("%s: only 8-bit PNGs are supported (got %d)" % (path, depth))
    if interlace:
        raise ValueError("%s: interlaced PNGs are not supported" % path)
    ch = _PNG_CHANNELS.get(ctype)
    if ch is None:
        raise ValueError("%s: unsupported PNG colour type %d" % (path, ctype))

    raw = zlib.decompress(bytes(idat))
    stride = w * ch
    prev = bytearray(stride)
    rows, p = [], 0
    for _y in range(h):
        ft = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if ft == 1:                       # Sub
            for i in range(ch, stride):
                line[i] = (line[i] + line[i - ch]) & 0xFF
        elif ft == 2:                     # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ft == 3:                     # Average
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ft == 4:                     # Paeth
            for i in range(stride):
                a = line[i - ch] if i >= ch else 0
                c = prev[i - ch] if i >= ch else 0
                line[i] = (line[i] + _paeth(a, prev[i], c)) & 0xFF
        elif ft != 0:
            raise ValueError("%s: unknown PNG row filter %d" % (path, ft))
        rows.append(bytes(line))
        prev = line

    flat = b"".join(rows)
    smask = None
    if ctype == 6:                        # RGBA -> interleaved RGB + alpha
        rgb = bytearray(len(flat) // 4 * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = flat[0::4], flat[1::4], flat[2::4]
        flat, smask, colours = bytes(rgb), flat[3::4], 3
    elif ctype == 4:                      # grey + alpha
        smask, colours = flat[1::2], 1
        flat = flat[0::2]
    elif ctype == 3:                      # palette
        colours = 3
        flat = bytes(bytearray(
            v for i in flat for v in plte[i * 3:i * 3 + 3]))
    else:                                 # 0 = grey, 2 = RGB
        colours = ch

    return dict(w=w, h=h, colours=colours, space=_PNG_SPACE[ctype],
                samples=flat, smask=smask)


class Doc:
    def __init__(self, title="", footer="", margin=56, top=64, bottom=58,
                 page_label=True, author=""):
        # page_label=False suppresses the right-aligned footer page number, for
        # documents that carry the page number in their running header instead.
        self.title, self.footer, self.author = title, footer, author
        self.page_label = page_label
        self.ml = self.mr = margin
        self.mt, self.mb = top, bottom
        self.width = PAGE_W - self.ml - self.mr
        self.pages = []
        self.images = {}        # resource name -> decoded PNG, in draw order
        self.new_page()

    def new_page(self):
        self.pages.append([])
        self.y = PAGE_H - self.mt

    # --- primitives ------------------------------------------------------
    def raw(self, s):
        self.pages[-1].append(s)

    def text(self, x, y, s, font="regular", size=10, color=(0, 0, 0)):
        name = FONTS[font][0]
        self.raw("BT %.3f %.3f %.3f rg /%s %.2f Tf %.2f %.2f Td (%s) Tj ET"
                 % (color[0], color[1], color[2], name, size, x, y, esc(s)))

    def line(self, x1, y1, x2, y2, color=(0.8, 0.8, 0.8), w=0.6):
        self.raw("%.3f %.3f %.3f RG %.2f w %.2f %.2f m %.2f %.2f l S"
                 % (color[0], color[1], color[2], w, x1, y1, x2, y2))

    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.6):
        ops = []
        if fill:
            ops.append("%.3f %.3f %.3f rg" % fill)
        if stroke:
            ops.append("%.3f %.3f %.3f RG" % stroke)
        ops.append("%.2f %.2f %.2f %.2f re" % (x, y, w, h))
        ops.append("B" if (fill and stroke) else ("f" if fill else "S"))
        self.raw(" ".join(ops))

    def figure(self, path, caption=None, max_h=300, gap=6, pad=1.5):
        """Place a PNG at full content width, captioned, centred.

        Scales down to fit `max_h`; never scales up, so a narrow screenshot
        keeps its native size instead of being blown up to page width.
        """
        img = load_png(path)
        name = "Im%d" % (len(self.images) + 1)
        self.images[name] = img

        cap_h = 11 if caption else 0
        scale = min(self.width / img["w"], max_h / img["h"], 1.0)
        dw, dh = img["w"] * scale, img["h"] * scale
        self.need(dh + cap_h + gap + pad * 2)
        x = self.ml + (self.width - dw) / 2
        top = self.y - pad
        self.rect(x - pad, top - dh - pad, dw + pad * 2, dh + pad * 2,
                  fill=None, stroke=(0.82, 0.85, 0.89), lw=0.5)
        self.raw("q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q"
                 % (dw, dh, x, top - dh, name))
        self.y = top - dh - pad
        if caption:
            self.y -= 10
            self.text(self.ml, self.y, caption, "regular", 7.8,
                      (0.42, 0.45, 0.52))
        self.y -= gap

    # --- flow layout -----------------------------------------------------
    def need(self, h):
        if self.y - h < self.mb:
            self.new_page()
            return True
        return False

    def rich_line(self, x, y, tokens, size, color=(0, 0, 0)):
        cx = x
        for text, key in tokens:
            self.text(cx, y, text, key, size, color)
            cx += width_of(text, key, size)

    def wrap(self, tokens, size, max_w):
        """Wrap (text, font) tokens into lines of (tokens, width).

        Spaces are kept exactly where the source had them, so ``**bold**,``
        joins as "bold," and not "bold ,".
        """
        words, pending = [], False
        for text, key in tokens:
            for i, word in enumerate(text.split(" ")):
                if i:
                    pending = True
                if word:
                    words.append((word, key, pending))
                    pending = False
        lines, cur, cur_w = [], [], 0.0
        space_w = width_of(" ", "regular", size)
        for word, key, space_before in words:
            ww = width_of(word, key, size)
            add = space_w + ww if (cur and space_before) else ww
            if cur and cur_w + add > max_w:
                lines.append((cur, cur_w))
                cur, cur_w = [(word, key)], ww
            else:
                if cur and space_before:
                    cur.append((" ", "regular"))
                cur.append((word, key))
                cur_w += add
        if cur:
            lines.append((cur, cur_w))
        return lines

    def para(self, text, size=10, leading=1.42, color=(0.13, 0.15, 0.19),
             space_after=7, indent=0.0, max_w=None, base_font="regular",
             code_font="mono"):
        tokens = inline_tokens(text, base_font, code_font)
        max_w = max_w or (self.width - indent)
        lines = self.wrap(tokens, size, max_w)
        lh = size * leading
        for line_tokens, _w in lines:
            self.need(lh)
            self.rich_line(self.ml + indent, self.y - size, line_tokens, size, color)
            self.y -= lh
        self.y -= space_after

    def heading(self, text, size=15, color=(0.06, 0.13, 0.28), space_before=10,
                space_after=6, rule=False, number=None):
        self.need(size * 2.2 + space_before)
        self.y -= space_before
        self.text(self.ml, self.y - size, text, "bold", size, color)
        self.y -= size * 1.25
        if rule:
            self.line(self.ml, self.y + 2, PAGE_W - self.mr, self.y + 2,
                      (0.80, 0.84, 0.90), 0.8)
            self.y -= 5
        self.y -= space_after

    def bullets(self, items, size=10, indent=16, marker="-", color=(0.13, 0.15, 0.19)):
        for item in items:
            self.need(size * 1.5)
            self.text(self.ml + 3, self.y - size, marker, "bold", size, (0.20, 0.35, 0.65))
            self.para(item, size=size, indent=indent, space_after=3, color=color)

    def numbered(self, items, size=10, indent=20):
        for i, item in enumerate(items, 1):
            self.need(size * 1.5)
            self.text(self.ml + 3, self.y - size, "%d." % i, "bold", size,
                      (0.20, 0.35, 0.65))
            self.para(item, size=size, indent=indent, space_after=3)

    def code(self, lines, size=8.2, pad=7, fill=(0.96, 0.97, 0.99),
             border=(0.85, 0.88, 0.93), color=(0.10, 0.13, 0.20)):
        # hard-wrap any line that would spill past the right edge
        max_chars = max(20, int((self.width - pad * 2) / (0.6 * size)))
        wrapped = []
        for ln in lines:
            if len(ln) <= max_chars:
                wrapped.append(ln)
                continue
            indent = len(ln) - len(ln.lstrip()) + 4
            rest = ln
            first = True
            while rest:
                cut = max_chars if first else max_chars - indent
                wrapped.append(rest[:cut] if first else " " * indent + rest[:cut])
                rest = rest[cut:]
                first = False
        lines = wrapped
        lh = size * 1.32
        block_h = len(lines) * lh + pad * 2
        self.need(min(block_h, PAGE_H - self.mt - self.mb))
        if block_h > PAGE_H - self.mt - self.mb:  # split long listings
            block_h = PAGE_H - self.mt - self.mb
        self.rect(self.ml, self.y - block_h, self.width, block_h, fill=fill,
                  stroke=border)
        ty = self.y - pad - size
        for ln in lines:
            self.text(self.ml + pad, ty, ln[:150], "mono", size, color)
            ty -= lh
        self.y -= block_h + 8

    def table(self, headers, rows, widths, size=8.6, header_fill=(0.10, 0.17, 0.33),
              row_alt=(0.965, 0.972, 0.985), pad=5):
        total = sum(widths)
        widths = [w / total * self.width for w in widths]
        lh = size * 1.30

        def row_height(cells, bold):
            h = 0
            for cell, w in zip(cells, widths):
                lines = self.wrap(inline_tokens(str(cell), "bold" if bold else "regular"),
                                  size, w - pad * 2)
                h = max(h, len(lines) * lh)
            return h + pad * 1.6

        self.need(row_height(headers, True))
        h = row_height(headers, True)
        self.rect(self.ml, self.y - h, self.width, h, fill=header_fill)
        x = self.ml
        for cell, w in zip(headers, widths):
            self.text(x + pad, self.y - pad - size * 0.95, str(cell), "bold", size,
                      (1, 1, 1))
            x += w
        self.y -= h
        for i, row in enumerate(rows):
            h = row_height(row, False)
            self.need(h)
            if i % 2 == 1:
                self.rect(self.ml, self.y - h, self.width, h, fill=row_alt)
            x = self.ml
            for cell, w in zip(row, widths):
                lines = self.wrap(inline_tokens(str(cell)), size, w - pad * 2)
                ty = self.y - pad - size * 0.95
                for line_tokens, _ in lines:
                    self.rich_line(x + pad, ty, line_tokens, size, (0.15, 0.17, 0.21))
                    ty -= lh
                x += w
            self.y -= h
            self.line(self.ml, self.y, PAGE_W - self.mr, self.y, (0.88, 0.90, 0.93), 0.5)
        self.y -= 10

    def callout(self, title, text, fill=(0.98, 0.95, 0.88),
                border=(0.85, 0.68, 0.32), title_color=(0.45, 0.28, 0.02),
                size=9.6):
        tokens = inline_tokens(text)
        inner_w = self.width - 26
        lines = self.wrap(tokens, size, inner_w)
        title_h = size * 1.5 if title else 0
        h = title_h + len(lines) * size * 1.38 + 22
        self.need(min(h, PAGE_H - self.mt - self.mb))
        self.rect(self.ml, self.y - h, self.width, h, fill=fill, stroke=border)
        self.rect(self.ml, self.y - h, 3.5, h, fill=border)
        ty = self.y - 11
        if title:
            self.text(self.ml + 14, ty - size, title, "bold", size, title_color)
            ty -= title_h
        for line_tokens, _ in lines:
            self.rich_line(self.ml + 14, ty - size, line_tokens, size, (0.22, 0.20, 0.14))
            ty -= size * 1.38
        self.y -= h + 9

    def severity_badge(self, label, color, x=None):
        w = width_of(label, "bold", 8.6) + 16
        x = self.ml if x is None else x
        self.rect(x, self.y - 13, w, 14, fill=color)
        self.text(x + 8, self.y - 9.5, label, "bold", 8.6, (1, 1, 1))
        return x + w + 6

    def _info(self):
        """Viewer metadata: title, author, producer, creation date."""
        parts = []
        if self.title:
            parts.append("/Title (%s)" % esc(self.title))
        if self.author:
            parts.append("/Author (%s)" % esc(self.author))
        parts.append("/Producer (pdfsmith)")
        parts.append("/CreationDate (D:%sZ)"
                     % time.strftime("%Y%m%d%H%M%S", time.gmtime()))
        return parts

    # --- output ----------------------------------------------------------
    def build(self, path, start_page=1):
        objects = {}

        def add(obj):
            # ids 1 and 2 are reserved for the catalog and page tree, so every
            # other object starts at 3 and can be referenced by its final id
            # directly - no renumbering pass that could desynchronise refs.
            idx = len(objects) + 3
            objects[idx] = obj
            return idx

        font_ids = {}
        for key, (name, _t) in FONTS.items():
            kind = "Courier" if name.startswith("F3") or name.startswith("F4") else "Helvetica"
            if name == "F2":
                kind = "Helvetica-Bold"
            if name == "F4":
                kind = "Courier-Bold"
            font_ids[key] = add("<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                                "/Encoding /WinAnsiEncoding >>" % kind)

        # Images next, so their ids exist before any page references them.
        # The sample bytes are stored already unfiltered, so these carry NO
        # predictor - declaring /Predictor 15 here would tell the reader to
        # un-filter data that has already been un-filtered, and it would render
        # as noise. (Predictor 15 is only for passing a PNG's raw IDAT through
        # untouched, which is impossible once alpha has to be split out.)
        xobject_ids = {}
        for name, img in self.images.items():
            smask_ref = ""
            if img["smask"] is not None:
                comp = zlib.compress(img["smask"], 9)
                sid = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                          b"/ColorSpace /DeviceGray /BitsPerComponent 8 "
                          b"/Filter /FlateDecode /Length %d >>\nstream\n"
                          % (img["w"], img["h"], len(comp)) + comp + b"\nendstream")
                smask_ref = " /SMask %d 0 R" % sid
            comp = zlib.compress(img["samples"], 9)
            head = ("<< /Type /XObject /Subtype /Image /Width %d /Height %d "
                    "/ColorSpace /%s /BitsPerComponent 8 /Filter /FlateDecode"
                    "%s /Length %d >>\nstream\n"
                    % (img["w"], img["h"], img["space"], smask_ref, len(comp)))
            xobject_ids[name] = add(head.encode("latin-1") + comp + b"\nendstream")

        xres = ""
        if xobject_ids:
            xres = "/XObject << %s >> " % " ".join(
                "/%s %d 0 R" % (n, i) for n, i in sorted(xobject_ids.items()))

        page_ids = []
        for pno, content in enumerate(self.pages, start=start_page):
            body = list(content)
            # footer
            body.append("0.45 0.48 0.55 rg")
            body.append("BT /F1 7.6 Tf %.2f %.2f Td (%s) Tj ET"
                        % (self.ml, 34, esc(self.footer)))
            if self.page_label:
                label = "Page %d" % pno
                lw = width_of(label, "regular", 7.6)
                body.append("BT /F1 7.6 Tf %.2f %.2f Td (%s) Tj ET"
                            % (PAGE_W - self.mr - lw, 34, esc(label)))
            body.append("%.2f 0.6 m %.2f 0.6 l S" % (self.ml, PAGE_W - self.mr)
                        ) if False else None
            stream = "\n".join(str(b) for b in body if b).encode("latin-1")
            comp = zlib.compress(stream, 9)
            cid = add(b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(comp)
                      + comp + b"\nendstream")
            pid = add("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] "
                      "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R /F3 %d 0 R "
                      "/F4 %d 0 R >> %s>> /Contents %d 0 R >>"
                      % (PAGE_W, PAGE_H, font_ids["regular"], font_ids["bold"],
                         font_ids["mono"], font_ids["mono_bold"], xres, cid))
            page_ids.append(pid)

        kids = " ".join("%d 0 R" % p for p in page_ids)
        final = dict(objects)
        final[1] = "<< /Type /Catalog /Pages 2 0 R >>"
        final[2] = "<< /Type /Pages /Kids [%s] /Count %d >>" % (kids, len(page_ids))

        # document properties, shown in the viewer's "File > Properties"
        info = self._info()
        info_id = 0
        if info:
            info_id = max(final) + 1
            final[info_id] = "<< %s >>" % " ".join(info)

        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for idx in sorted(final):
            offsets[idx] = len(out)
            obj = final[idx]
            if isinstance(obj, bytes):
                out += b"%d 0 obj\n" % idx + obj + b"\nendobj\n"
            else:
                out += ("%d 0 obj\n%s\nendobj\n" % (idx, obj)).encode("latin-1")
        xref_at = len(out)
        count = max(final) + 1
        out += ("xref\n0 %d\n" % count).encode()
        out += b"0000000000 65535 f \n"
        for idx in range(1, count):
            if idx in offsets:
                out += ("%010d 00000 n \n" % offsets[idx]).encode()
            else:
                out += b"0000000000 65535 f \n"
        out += ("trailer\n<< /Size %d /Root 1 0 R%s >>\nstartxref\n%d\n%%%%EOF\n"
                % (count, "" if not info_id else " /Info %d 0 R" % info_id,
                   xref_at)).encode()
        with open(path, "wb") as fh:
            fh.write(out)
        return len(self.pages)
