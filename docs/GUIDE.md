# pdfsmith guide

Start to finish: install, write a report, style it, check it.

- [Install](#install)
- [Command line](#command-line)
- [Your first report](#your-first-report)
- [How it works](#how-it-works)
- [The cover page](#the-cover-page)
- [Contents](#contents)
- [Sections](#sections)
- [Text](#text)
- [Tables](#tables)
- [Code blocks](#code-blocks)
- [Callouts](#callouts)
- [Figures](#figures)
- [Findings](#findings)
- [Key/value lists](#keyvalue-lists)
- [Running header, footer, watermark](#running-header-footer-watermark)
- [Changing the look](#changing-the-look)
- [Page geometry](#page-geometry)
- [Placing things by hand](#placing-things-by-hand)
- [Checking the output](#checking-the-output)
- [Automating a report per host](#automating-a-report-per-host)
- [Gotchas](#gotchas)
- [FAQ](#faq)

## Install

```bash
pip install git+https://github.com/ASSEMMERZOUG/pdfsmith
```

That puts the `pdfsmith` command on your PATH. From a checkout, no install
needed - `examples/` adds the repo root to
`sys.path` itself:

```bash
git clone https://github.com/ASSEMMERZOUG/pdfsmith
cd pdfsmith
python3 examples/minimal.py /tmp/minimal.pdf
```

Requirements: Python 3.8+, nothing else. No Pillow, no reportlab, no TeX, no
browser.

## Command line

`pdfsmith` builds a report from a JSON file. Installed, it is `pdfsmith`; from
a checkout it is `python3 -m pdfsmith`.

```
python3 -m pdfsmith report.json -o report.pdf
wrote report.pdf (6 pages)
```

`-o` overrides the spec's `output` key. Relative paths - the output and any
figure - resolve against the **spec file's directory**, not the shell's
working directory, so a report folder can be built from anywhere.

After writing, the structural check runs (`--no-check` to skip it). A bad
spec is an error, with the block index:

```
$ python3 -m pdfsmith report.json
pdfsmith: blocks[4]: unknown block 'paragraf'; known blocks: bullets, callout,
code, cover, figure, finding, h2, h3, kv, numbered, pagebreak, para, quote,
section, spacer, table, toc
```

### The spec

Top level, all optional except `blocks` and an output path:

| Key | Type | Meaning |
|---|---|---|
| `title`, `author` | string | PDF metadata |
| `header` | string | running header, `%d` is the page number (`%%` is a literal `%`) |
| `footer` | string | grey line at the bottom |
| `watermark` | string | diagonal text behind the content |
| `margin`, `top`, `bottom` | number | page geometry in points |
| `output` | string | where to write the PDF |
| `cover` | object | see below |
| `toc` | `true` or `{"heading": "Contents"}` | contents page |
| `blocks` | array | the document, in order |

The cover takes the same fields as `Report.cover()`:
`kicker`, `org`, `title` (a list of lines), `subtitle`, `facts`
(`[[label, value], ...]`), `blurb` (list of paragraphs) and `badge`.

Each block is an object with exactly one key:

| Block | JSON |
|---|---|
| `section` | `{"num": "1", "title": "Summary", "new_page": "auto"}` (`new_page`: `true`, `false`, `"auto"`) |
| `h2`, `h3` | a string |
| `para` | a string, or `{"text": "...", "size": 10, "space_after": 7}` |
| `bullets`, `numbered` | a list of strings, or `{"items": [...], "size": 9.8}` |
| `quote` | a string |
| `callout` | `{"title": "...", "text": "..."}` |
| `code` | a list of lines, or `{"lines": [...], "size": 8.2}` |
| `table` | `{"headers": [...], "rows": [[...]], "widths": [...], "size": 8.6}` |
| `figure` | `{"path": "shot.png", "caption": "...", "max_h": 300}` |
| `kv` | `[["Label", "Value"], ["Tools", ["one", "two"]]]` |
| `finding` | `{"id", "severity", "title", "where", "what", "impact", "proof", "fix"}` |
| `spacer` | points, or `{"h": 12}` |
| `pagebreak` | `true` |

Inline `**bold**` and `` `code` `` work in every text field, exactly as they do
in Python. `examples/report.json` is a complete document using most of the
schema; build it with:

```
python3 -m pdfsmith examples/report.json -o /tmp/acme.pdf
```

## Your first report

```python
from pdfsmith import Report

r = Report(
    title="Acme - web assessment",            # PDF metadata
    author="Assem Merzoug",
    header="ACME | WEB ASSESSMENT | Page %d", # %d is the page number
    footer="Client confidential",
)

r.cover(
    kicker="Penetration test report",
    org="Acme Ltd",
    title=["Acme", "web assessment"],
    subtitle="Three findings across the customer portal. One critical.",
    facts=[("Client", "Acme Ltd"),
           ("Scope", "portal.acme.example"),
           ("Engagement", "6 - 10 October 2026"),
           ("Version", "1.0")],
    blurb=["Two paragraphs of context go here, in the reader's language."],
    badge="1 CRITICAL",
)

r.toc()

r.section("1", "Executive summary")
r.para("The portal lets **any customer read any invoice**. That is the only "
       "issue that needs fixing this week.")
r.bullets(["One critical issue, two high, no false positives.",
           "Every issue reproduced twice from a clean account."])

r.section("2", "Findings")
r.finding(
    "F-01", "CRITICAL", "Any customer can read any invoice",
    where="GET /api/invoices/{id}",
    what="The endpoint returns the invoice without checking the owner.",
    proof=["GET /api/invoices/10481", "", "200 OK"],
    impact="Billing data for every other customer.",
    fix=["Scope the query by the session's account.",
         "Return 404, not 403."],
)

pages = r.build("acme.pdf")   # -> 4
```

Result: a cover, a contents page with the right numbers, two sections, a
severity-chipped finding.

## How it works

A `Report` does not write to the PDF as you call it. Each call **records a
block**; `build()` then renders the whole document **twice**:

1. **Pass one** - blocks draw onto pages, and each `section()` remembers which
   page it landed on.
2. **Pass two** - the same blocks draw again, now knowing those page numbers,
   so `toc()` can print them.

You never write page numbers yourself, and the contents list can come before
the sections it describes.

Two things follow from that. Blocks run twice, so they have to be
deterministic: compute a timestamp before you add the block, not inside the
lambda. And `.build()` returns the page count.

Everything is in points, 72 per inch, origin at the bottom-left of the page.

## The cover page

`cover(kicker, title, subtitle=None, facts=None, blurb=None, badge=None, org=None)`

- `kicker` - small caps line at the top, e.g. `"Penetration test report"`.
- `org` - client or project name, printed small under the kicker.
- `title` - **a list of lines**, not a string. Two short lines read better
  than one long one: `["Web application", "assessment"]`.
- `subtitle` - one or two sentences; the navy panel grows to fit it.
- `badge` - a coloured chip, e.g. `"1 CRITICAL"` or `"MEDIUM - CWE-840"`.
  The colour comes from the first severity word found in the string.
- `blurb` - list of paragraphs under the panel.
- `facts` - list of `(label, value)` pairs shown in the details box.

The cover assumes it is the first block and occupies one page.

## Contents

`toc(heading="Contents")` starts a new page and lists every `section()` in
call order with leaders and page numbers. Add it once, right after the cover.

The numbers come from pass one, so a section that moves a page will move its
own entry too. No maintenance.

## Sections

`section(num, title, new_page="auto")`

| `new_page` | Behaviour |
|---|---|
| `"auto"` (default) | starts a new page if the current one is more than half used, otherwise draws an inline heading |
| `True` | always starts a page with a full navy band |
| `False` | always inline |

`"auto"` is the default because it keeps half-empty pages down without
leaving a heading stranded at the bottom. Use `True` for the findings section
and for anything after a long table.

The number is a string: `section("1", "Executive summary")`, or `section("A", ...)`
for appendices.

## Text

| Call | Notes |
|---|---|
| `h2(text)` | heading with a rule under it |
| `h3(text)` | smaller heading, no rule |
| `para(text, size=10, space_after=7, color=...)` | body text |
| `bullets(items, size=9.8)` | hyphen bullets |
| `numbered(items, size=9.8)` | 1. 2. 3. |
| `quote(text)` | indented with an accent bar on the left |
| `spacer(h=12)` | vertical gap |
| `pagebreak()` | force a new page |

Inside every text argument you can use two inline markers:

- `**bold**`
- `` `monospace` ``

```python
r.para("The `session` cookie is missing **Secure**, so it travels over HTTP.")
```

Spacing is preserved exactly: `**bold**, more` renders "bold," with no stray
space, and a marker can end mid-sentence.

Body text is justified to the content width and wraps automatically. If a
paragraph runs out of page, the rest continues on the next page - you never
place individual lines.

## Tables

`table(headers, rows, widths=None, size=8.6)`

```python
r.table(
    ["ID", "Severity", "Finding", "Status"],
    [["F-01", "Critical", "Invoices readable by any account", "Open"],
     ["F-02", "High", "Stored script injection", "Open"]],
    widths=[0.6, 0.9, 3.0, 0.6],    # relative, not points
    size=9,
)
```

- `widths` are relative weights; `[1, 1, 2]` splits the width 25/25/50.
- Cells wrap, so long findings text is fine.
- Inline markup works in cells: `"**Fail**"` prints bold.
- Alternate rows are tinted; the header is navy with white text.
- A table splits across pages row by row, repeating nothing - keep the header
  short and the first column meaningful.

## Code blocks

`code(lines, size=8.2)` takes a **list of lines**:

```python
r.code([
    "GET /api/invoices/10481 HTTP/1.1",
    "Cookie: session=<test account A>",
    "",
    "HTTP/1.1 200 OK",
], size=8.0)
```

Long lines are hard-wrapped to the block width with a hanging indent.
Backticks and asterisks are literal here - no inline markup.

## Callouts

`callout(title, text, fill=..., border=...)`

A tinted box with an accent stripe, for "If you only fix one thing",
"Decision needed", "Re-test included". Use them sparingly: one or two per
report, for the sentence a manager must not miss.

## Figures

`figure(path, caption=None, max_h=300)` embeds a PNG at content width.

```python
r.figure("burp-request.png", caption="The 200 response, redacted.", max_h=260)
```

- Scaled **down** to fit the width or `max_h`, never up - a narrow screenshot
  keeps its size instead of turning into a blurry poster.
- Centred, inside a thin border, with the caption underneath.
- PNG only: 8-bit, non-interlaced. RGBA works; the alpha channel is split into
  a proper `/SMask` so transparent screenshots do not come out with black
  boxes.
- Convert anything else first: `convert shot.jpg shot.png` (ImageMagick) or
  use the tool that produced it.

A 1500 px screenshot at `max_h=300` renders about 4.3 inches tall - right for
half a page. For full-page evidence use `max_h=500`.

## Findings

`finding(id, severity, title, where=None, what=None, impact=None, fix=None, proof=None)`

One call per issue, in the order of the summary table:

```python
r.finding(
    "F-01", "HIGH", "Stored XSS in shipment notes",
    where="POST /api/shipments/{id}/notes",
    what="Notes are stored verbatim and rendered with innerHTML.",
    proof=["POST /api/shipments/88213/notes",
           '{"note":"<img src=x onerror=alert(1)>"}'],
    impact="An attacker with a customer account acts as an operator.",
    fix=["Render notes as text.", "Add a CSP that forbids inline script."],
)
```

- `severity` picks the chip colour: CRITICAL, HIGH, MEDIUM, LOW, INFO.
  Aliases work (`CRIT`, `MODERATE`, `INFORMATIONAL`), and a string like
  `"HIGH - CWE-79"` resolves on the first known word.
- `proof` is a list of lines rendered as a code block - request, response, a
  one-line reproducer.
- `fix` is a list of bullets.
- `impact` is prefixed with a bold "Impact."
- The block reserves room so the chip, title and first paragraph stay
  together; a long finding can still flow onto the next page after that.

## Key/value lists

`kv(pairs, size=9.4)` - a compact label/value stack for methodology sections:

```python
r.kv([
    ("Scope", "portal.acme.example, api.acme.example"),
    ("Window", "6 - 10 October 2026, 09:00 - 18:00"),
    ("Tools", ["Burp Suite Pro", "ffuf", "custom scripts"]),
])
```

A value that is a list becomes bullets.

## Running header, footer, watermark

- `header="ACME | Page %d"` - one navy strip at the top of every page (including
  the cover) with the page number. A literal percent sign must be doubled:
  `"100%% done | Page %d"`.
- `footer="Client confidential"` - grey line at the bottom of every page.
- `watermark="CONFIDENTIAL"` - large grey diagonal text behind the content.

All three are plain text; inline markup is not applied.

## Changing the look

The palette lives in `pdfsmith/style.py` and is read at draw time, so you can
change it programmatically before building:

```python
from pdfsmith import Report, style

style.NAVY = (0.10, 0.10, 0.12)
style.ACCENT = (0.85, 0.35, 0.10)
style.SEV["CRITICAL"] = (0.60, 0.00, 0.00)

r = Report(...)
```

Colours are `(r, g, b)` floats from 0 to 1.

| Name | Used for |
|---|---|
| `NAVY` | cover panel, section bands, header strip |
| `NAVY_SOFT` | secondary headings, details labels |
| `ACCENT` | rules, section numbers, accent bars |
| `INK` / `GREY` | body text / captions |
| `SEV` | severity chip colours |

## Page geometry

A4, 595 x 842 points. Margins are constructor arguments:

```python
Report(margin=56, top=64, bottom=58)
```

`margin` sets both left and right; `top` and `bottom` are separate because the
header and footer need room. All blocks use the content width, which is
`595 - 2 * margin`.

US Letter is not a switch: change `PAGE_W, PAGE_H` at the top of
`pdfsmith/doc.py` to `612, 792`.

## Placing things by hand

`Report` covers most documents. When you need a stamp, a signature block or a
precise diagram, drop to `Doc` - the same engine with a per-op API:

```python
from pdfsmith import Doc, PAGE_W, PAGE_H

d = Doc(title="Certificate", footer="Acme Ltd")
d.rect(0, PAGE_H - 180, PAGE_W, 180, fill=(0.06, 0.12, 0.26))
d.text(56, PAGE_H - 90, "Certificate of testing", "bold", 26, (1, 1, 1))
d.para("This document records the testing performed between ...")
d.figure("seal.png", max_h=80)
d.build("certificate.pdf")
```

`Doc` gives you `text, line, rect, para, heading, bullets, numbered, code,
table, callout, figure, rich_line, wrap, need, new_page, raw`. `d.y` is the
current vertical cursor; `need(h)` starts a new page when `h` would not fit.
`raw()` appends a raw content-stream operator, which is the escape hatch for
anything the helpers do not cover.

You can also mix the two: a `Report` block is just a function of `(doc, ctx)`,
so any custom layout can be added with `r._add(lambda d, ctx: ...)` - though
if you find yourself doing that often, `Doc` is the clearer tool.

## Checking the output

```bash
python3 -m pdfsmith.check report.pdf
```

Walks the file the way a viewer does and fails on the first real problem:
corrupt xref, dangling object reference, a page without contents, a font used
but not declared, a page with no text. Exit status 1 on failure, so it drops
straight into CI:

```bash
python3 build_report.py && python3 -m pdfsmith.check report.pdf
```

```bash
python3 -m pdfsmith.check --text report.pdf
```

prints the text it can read back, one line per drawn line - handy to grep for
"TODO", "XXX", or a flag you meant to redact:

```bash
python3 -m pdfsmith.check --text report.pdf | grep -i -E 'flag|secret|token'
```

For a visual check, render with Ghostscript (no Poppler needed):

```bash
gs -q -dNOPAUSE -dBATCH -sDEVICE=png16m -r110 -sOutputFile=page%d.png report.pdf
```

## Automating a report per host

Blocks are recorded, not executed, so a loop works exactly as you would hope:

```python
import json, sys
from pdfsmith import Report

data = json.load(open(sys.argv[1]))          # one dict per machine
for host in data["hosts"]:
    r = Report(title=host["name"], header="%s | Page %%d" % host["name"].upper())
    r.cover(kicker=host["os"], title=[host["name"]], facts=host["facts"])
    r.toc()
    r.section("1", "Summary")
    r.para(host["summary"])
    for i, f in enumerate(host["findings"], 1):
        r.finding("F-%02d" % i, f["severity"], f["title"],
                  where=f["where"], what=f["what"], proof=f["lines"],
                  impact=f["impact"], fix=f["fix"])
    r.build("%s-report.pdf" % host["name"])
```

Note the `%%d` in the header inside a pre-formatted string - the header is
formatted with the page number at build time.

## Gotchas

**The header is a format string.** `"Page %d"` becomes `"Page 7"`. A literal
percent must be `%%`. The same applies if you build it with `%` elsewhere -
escape the placeholder, as above.

**Text is cp1252, not Unicode.** Curly quotes, en dashes and `€` work; emoji,
CJK, Arabic and Devanagari do not - they come out as `?`. If you need another
script, use a different tool: base-14 fonts cannot carry it.

**`title` on the cover is a list.** `title="Acme"` iterates the string and
draws one letter per line. Use `["Acme"]`.

**Figures do not scale up.** A 300 px icon stays 300 px. That is deliberate;
crop the screenshot instead.

**A finding can split across pages.** The chip, title and first paragraph are
kept together, but a long `proof` block may continue on the next page. If you
want each finding on its own page, `r.pagebreak()` between them.

**`section(..., new_page="auto")` can leave a half-empty page.** That is the
cost of never stranding a heading. For a section that should always start
fresh, pass `True`.

**Nothing renders until `build()`.** Exceptions raised by a block surface at
build time, not at the line that created it.

## FAQ

**Company font?** Not without embedding it, and embedding a TrueType file
means shipping a font parser. Base-14 only.

**Logo on the cover?** `figure()` after the cover text, or place it by hand
with `Doc`.

**Windows?** Works. Pure Python, no shell-outs, backslashes in paths are fine.

**Page number in the footer instead of the header?** `Report` puts it in the
header and turns the footer label off. Build with `Doc(page_label=True)` if
you want the footer one, or both.
