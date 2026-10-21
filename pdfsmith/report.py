"""High-level report builder on top of the Doc engine.

    from pdfsmith import Report

    r = Report(title="Acme - web assessment", header="ACME | Page %d")
    r.cover(kicker="Penetration Test Report", title=["Acme", "Web assessment"],
            facts=[("Client", "Acme Ltd"), ("Date", "2026-10-21")])
    r.toc()
    r.section("1", "Summary")
    r.para("One page your manager can read.")
    r.build("acme.pdf")

Every call records a block; build() renders the document twice, so the table
of contents can carry real page numbers.
"""
from . import style
from .doc import Doc, PAGE_W, PAGE_H, width_of, inline_tokens, esc


class Report:
    def __init__(self, title="", author="", footer="", header="", watermark="",
                 margin=56, top=64, bottom=58):
        # header may contain a single %d, substituted with the page number
        self.title = title
        self.author = author
        self.footer = footer
        self.header = header
        self.watermark = watermark
        self.margin = margin
        self.top = top
        self.bottom = bottom
        self._blocks = []
        self._sections = []        # (num, title) in call order

    # -- recording ---------------------------------------------------------
    def _add(self, fn):
        self._blocks.append(fn)
        return self

    # -- structure ---------------------------------------------------------
    def cover(self, kicker, title, subtitle=None, facts=None, blurb=None,
              badge=None, org=None):
        """Full-bleed first page. `title` is a list of lines."""
        facts = facts or []
        blurb = blurb or []

        def draw(d, ctx):
            ml, iw = d.ml, PAGE_W - 2 * d.ml
            sub_lines = d.wrap(inline_tokens(subtitle), 12.5, iw) if subtitle else []
            band_h = (150 + 36 * len(title)
                      + (17 * len(sub_lines) + 8 if sub_lines else 18))
            d.rect(0, PAGE_H - band_h, PAGE_W, band_h, fill=style.NAVY)
            d.rect(0, PAGE_H - band_h - 6, PAGE_W, 6, fill=style.ACCENT)
            d.text(ml, PAGE_H - 74, kicker.upper(), "bold", 10, (0.62, 0.76, 0.95))
            if org:
                d.text(ml, PAGE_H - 100, org.upper(), "regular", 9, (0.45, 0.60, 0.82))
                d.line(ml, PAGE_H - 112,
                       ml + width_of(org.upper(), "regular", 9),
                       PAGE_H - 112, (0.35, 0.50, 0.78), 1.2)
            ty = PAGE_H - 150
            for line in title:
                d.text(ml, ty, line, "bold", 30, style.WHITE)
                ty -= 36
            if sub_lines:
                ty -= 4
                for tokens, _w in sub_lines:
                    d.rich_line(ml, ty, tokens, 12.5, (0.72, 0.82, 0.96))
                    ty -= 17
            d.y = ty

            y = min(d.y, PAGE_H - band_h - 50)
            if badge:
                colour = style.severity_color(badge)
                d.rect(ml, y - 20, width_of(badge, "bold", 10) + 22, 22, fill=colour)
                d.text(ml + 11, y - 14, badge, "bold", 10, style.WHITE)
                y -= 44
            d.y = y
            for para in blurb:
                d.para(para, size=11, leading=1.5, color=style.INK, space_after=9)

            if facts:
                box_h = 58 + 22 * (len(facts) - 1)
                y = d.y - 26
                if y - box_h < 70:
                    y = 70 + box_h
                d.rect(ml, y - box_h, iw, box_h,
                       fill=style.PAPER, stroke=(0.86, 0.89, 0.93))
                d.text(ml + 16, y - 22, "DETAILS", "bold", 8.5, style.NAVY_SOFT)
                yy = y - 42
                for k, v in facts:
                    d.text(ml + 16, yy, k, "bold", 9.5, style.GREY)
                    d.text(ml + 144, yy, v, "regular", 9.5, style.INK)
                    yy -= 22
                d.y = y - box_h - 24

        return self._add(draw)

    def toc(self, heading="Contents"):
        """Table of contents. Page numbers are filled in on the second pass."""

        def draw(d, ctx):
            if d.pages[-1]:
                d.new_page()
            self._band(d, heading.upper())
            size, indent = 10.5, 28
            for num, sect_title in self._sections:
                page = str(ctx["page_of"].get(num, "-"))
                d.text(d.ml, d.y - 11, "%s." % num, "bold", size, style.ACCENT)
                d.text(d.ml + indent, d.y - 11, sect_title, "regular", size,
                       style.INK)
                pw = width_of(page, "bold", size)
                d.text(PAGE_W - d.mr - pw, d.y - 11, page, "bold", size,
                       style.NAVY_SOFT)
                lead_x = d.ml + indent + width_of(sect_title, "regular", size) + 8
                d.line(lead_x, d.y - 9, PAGE_W - d.mr - pw - 8, d.y - 9,
                       (0.84, 0.87, 0.91), 0.6)
                d.y -= 19

        return self._add(draw)

    def section(self, num, title, new_page="auto"):
        """Section opener; registers its page for the contents list.

        new_page=True   always start a new page (a navy band)
        new_page=False  keep flowing, draw an inline heading
        new_page="auto" band a fresh page when the current one is more than
                        half used, otherwise an inline heading (the default -
                        it avoids half-empty pages without ever orphaning a
                        heading at the bottom of a page)
        """
        self._sections.append((num, title))

        def draw(d, ctx):
            inline = False
            if new_page is False:
                inline = True
            elif new_page == "auto":
                inline = bool(d.pages[-1]) and d.y >= PAGE_H * 0.5
            if not inline and d.pages[-1]:
                d.new_page()
            ctx["found"][num] = len(d.pages)
            if inline and d.pages[-1]:
                d.y -= 18
                d.text(d.ml, d.y - 15, "%s  %s" % (num, title.upper()),
                       "bold", 14, style.NAVY)
                d.y -= 21
                d.rect(d.ml, d.y, 60, 2.5, fill=style.ACCENT)
                d.y -= 16
            else:
                self._band(d, "%s  %s" % (num, title.upper()))

        return self._add(draw)

    def pagebreak(self):
        return self._add(lambda d, ctx: d.new_page())

    def spacer(self, h=12):
        return self._add(lambda d, ctx: setattr(d, "y", d.y - h))

    # -- text --------------------------------------------------------------
    def h2(self, text):
        return self._add(lambda d, ctx: self._rule_heading(d, text, 13, style.NAVY))

    def h3(self, text):
        return self._add(lambda d, ctx: self._rule_heading(d, text, 11,
                                                          style.NAVY_SOFT, rule=False))

    def para(self, text, size=10, space_after=7, color=style.INK):
        """Markdown-ish: **bold**, `code`, and blank-line-free flow."""
        return self._add(lambda d, ctx: d.para(text, size=size,
                                               space_after=space_after, color=color))

    def bullets(self, items, size=9.8):
        return self._add(lambda d, ctx: d.bullets(items, size=size))

    def numbered(self, items, size=9.8):
        return self._add(lambda d, ctx: d.numbered(items, size=size))

    def quote(self, text):
        def draw(d, ctx):
            d.need(40)
            y0 = d.y
            d.para(text, size=11.5, color=style.NAVY_SOFT, space_after=10,
                   indent=14)
            d.line(d.ml, y0 + 2, d.ml, d.y + 6, style.ACCENT, 2.4)
        return self._add(draw)

    def callout(self, title, text, fill=(0.98, 0.95, 0.88),
                border=(0.90, 0.82, 0.62)):
        return self._add(lambda d, ctx: d.callout(title, text, fill=fill,
                                                  border=border))

    # -- blocks ------------------------------------------------------------
    def code(self, lines, size=8.2):
        return self._add(lambda d, ctx: d.code(lines, size=size))

    def table(self, headers, rows, widths=None, size=8.6):
        widths = widths or [1] * len(headers)
        return self._add(lambda d, ctx: d.table(headers, rows, widths, size=size))

    def figure(self, path, caption=None, max_h=300):
        return self._add(lambda d, ctx: d.figure(path, caption=caption,
                                                 max_h=max_h))

    def kv(self, pairs, size=9.4):
        def draw(d, ctx):
            for k, v in pairs:
                # keep the label with the first lines of its value
                d.need(size * 5.2)
                d.text(d.ml, d.y - size, k, "bold", size, style.NAVY_SOFT)
                d.y -= size * 1.45
                if isinstance(v, (list, tuple)):
                    d.bullets(list(v), size=size, indent=16)
                else:
                    d.para(v, size=size, space_after=3)
                d.y -= 4
        return self._add(draw)

    def finding(self, id, severity, title, where=None, what=None, impact=None,
                fix=None, proof=None):
        """One pentest finding, from the chip down to the fix."""
        def draw(d, ctx):
            d.need(110)
            colour = style.severity_color(severity)
            label = "%s  %s" % (id, severity)
            w = width_of(label, "bold", 8.0) + 14
            d.rect(d.ml, d.y - 13, w, 13, fill=colour)
            d.text(d.ml + 7, d.y - 10, label, "bold", 8.0, style.WHITE)
            d.y -= 22
            d.para("**%s**" % title, size=12, color=style.NAVY, space_after=3)
            if where:
                d.para(where, size=8.4, color=style.GREY, space_after=5)
            if what:
                d.para(what, size=9.4, space_after=4)
            if proof:
                d.code(proof, size=8.0)
            if impact:
                d.para("**Impact.** " + impact, size=9.4, space_after=4)
            if fix:
                d.text(d.ml, d.y - 9, "Fix", "bold", 9.0, style.NAVY_SOFT)
                d.y -= 15
                d.bullets(list(fix), size=9.0, indent=14)
            d.y -= 6
            d.line(d.ml, d.y, PAGE_W - d.mr, d.y, (0.88, 0.90, 0.93), 0.6)
            d.y -= 16
        return self._add(draw)

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _band(d, text):
        d.rect(0, PAGE_H - 74, PAGE_W, 48, fill=style.NAVY)
        d.text(56, PAGE_H - 58, text, "bold", 13.5, style.WHITE)
        d.y = PAGE_H - 100

    @staticmethod
    def _rule_heading(d, text, size, color, rule=True):
        d.heading(text, size=size, color=color, space_before=13, space_after=5,
                  rule=rule)

    def _decorate(self, d):
        for i, page in enumerate(d.pages, 1):
            if self.watermark:
                page.insert(0,
                            "q 0.930 0.930 0.935 rg BT /F2 58 Tf "
                            "0.7071 0.7071 -0.7071 0.7071 95 250 Tm "
                            "(%s) Tj ET Q" % esc(self.watermark))
            if self.header:
                page.append("%.3f %.3f %.3f rg 0 %.2f %.2f 26 re f"
                            % (style.NAVY[0], style.NAVY[1], style.NAVY[2],
                               PAGE_H - 26, PAGE_W))
                page.append("BT 0.800 0.870 0.960 rg /F1 7.2 Tf %.2f %.2f Td "
                            "(%s) Tj ET"
                            % (d.ml, PAGE_H - 17, esc(self.header % i)))

    def _render(self, page_of):
        d = Doc(title=self.title, footer=self.footer, author=self.author,
                margin=self.margin, top=self.top, bottom=self.bottom,
                page_label=False)
        ctx = {"page_of": page_of, "found": {}}
        for block in self._blocks:
            block(d, ctx)
        return d, ctx["found"]

    def build(self, path):
        """Render to `path`. Returns the number of pages."""
        _, found = self._render({})
        d, _ = self._render(found)
        self._decorate(d)
        return d.build(path)
