# API reference

Two classes, one palette module, one checker. Everything is in points
(72 per inch), origin at the bottom-left of the page.

```python
from pdfsmith import Report, Doc, style, PAGE_W, PAGE_H
```

---

## `Report`

High level: records blocks, renders twice, writes the file.

```python
Report(title="", author="", footer="", header="", watermark="",
       margin=56, top=64, bottom=58)
```

| Argument | Meaning |
|---|---|
| `title` | PDF `/Title`, shown in the viewer's properties |
| `author` | PDF `/Author` |
| `footer` | grey line at the bottom of every page |
| `header` | navy strip at the top of every page; `%d` becomes the page number, `%%` a literal percent |
| `watermark` | large grey diagonal text behind the content |
| `margin` | left and right margin |
| `top`, `bottom` | separate, because the header and footer need room |

All blocks return `self`, so calls chain:
`Report().section("1", "Summary").para("...").build("out.pdf")`.

### Structure

#### `cover(kicker, title, subtitle=None, facts=None, blurb=None, badge=None, org=None)`

First page. `title` is a **list of lines**. `facts` is a list of
`(label, value)` pairs. `badge` draws a severity chip whose colour comes from
`style.severity_color()`.

#### `toc(heading="Contents")`

Starts a page and lists every `section()` in call order with leaders and page
numbers. Correct because the document is rendered twice.

#### `section(num, title, new_page="auto")`

Draws the section opener and records its page for `toc()`.

- `new_page=True` - always a fresh page with a navy band
- `new_page=False` - inline heading
- `new_page="auto"` - fresh page unless the current page is less than half used

`num` is a string (`"1"`, `"A"`).

#### `pagebreak()`

Starts a new page unconditionally (blank page if the current one is empty).

#### `spacer(h=12)`

Moves the cursor down `h` points.

### Text

| Method | Signature | Notes |
|---|---|---|
| `h2` | `h2(text)` | heading with a rule |
| `h3` | `h3(text)` | smaller heading |
| `para` | `para(text, size=10, space_after=7, color=style.INK)` | wraps and paginates |
| `bullets` | `bullets(items, size=9.8)` | `items` is a list of strings |
| `numbered` | `numbered(items, size=9.8)` | 1. 2. 3. |
| `quote` | `quote(text)` | accent bar on the left |
| `callout` | `callout(title, text, fill=(0.98,0.95,0.88), border=(0.90,0.82,0.62))` | tinted box |
| `kv` | `kv(pairs, size=9.4)` | label above value; a list value becomes bullets |

`**bold**` and `` `code` `` work in every text argument.

### Blocks

#### `table(headers, rows, widths=None, size=8.6)`

`widths` are relative weights, not points; `None` means equal columns. Cells
wrap and accept inline markup. Rows alternate tint; the header is navy.

#### `code(lines, size=8.2)`

`lines` is a list of strings. Long lines are wrapped with a hanging indent.
A block taller than a page is clipped to one page - split it yourself.

#### `figure(path, caption=None, max_h=300)`

PNG, 8-bit, non-interlaced, RGB/RGBA/grey/palette. Scales down to the content
width or `max_h`, never up. Centred, thin border, caption underneath.

#### `finding(id, severity, title, where=None, what=None, impact=None, fix=None, proof=None)`

| Argument | Rendered as |
|---|---|
| `id`, `severity` | a coloured chip, e.g. `F-01  CRITICAL` |
| `title` | bold navy line |
| `where` | small grey line (endpoint, file, host) |
| `what` | body paragraph |
| `proof` | code block (list of lines) |
| `impact` | body paragraph prefixed with bold "Impact." |
| `fix` | bold "Fix" label + bullets |

#### `build(path)`

Renders twice and writes `path`. Returns the page count.

---

## `build` - JSON specs

```python
from pdfsmith.build import build_file, report_from_spec, SpecError, main

path, pages = build_file("report.json", out_path=None, run_check=True)
report, target = report_from_spec(spec_dict, base_dir=".")
main(["report.json", "-o", "out.pdf"])      # the CLI, callable
```

`report_from_spec()` returns a configured `Report` without building it, which
is the seam for a web form or a generated spec. `build_file()` builds and, by
default, runs `check()` on the result. `SpecError` names the offending block,
e.g. `blocks[3]: table.rows[0]: expected 2 cells, one per header`.

Schema: `docs/GUIDE.md#command-line`.

---

## `Doc`

Low level: you place every element yourself against a vertical cursor.

```python
Doc(title="", footer="", author="", margin=56, top=64, bottom=58,
    page_label=True)
```

| Attribute | Meaning |
|---|---|
| `ml`, `mr`, `mt`, `mb` | margins |
| `width` | content width (`PAGE_W - ml - mr`) |
| `y` | current vertical cursor; blocks draw down from it |
| `pages` | list of pages, each a list of content-stream strings |
| `images` | embedded images, in draw order |

### Drawing

| Method | Purpose |
|---|---|
| `new_page()` | start a page, reset `y` |
| `need(h)` | `new_page()` if `h` points do not fit; returns whether it broke |
| `text(x, y, s, font="regular", size=10, color=(0,0,0))` | one line, absolute position |
| `line(x1, y1, x2, y2, color=..., w=0.6)` | |
| `rect(x, y, w, h, fill=None, stroke=None, lw=0.6)` | `y` is the **bottom** edge |
| `figure(path, caption=None, max_h=300)` | PNG at the cursor |
| `rich_line(x, y, tokens, size, color)` | draw pre-wrapped tokens |
| `wrap(tokens, size, max_w)` | `[(tokens, width), ...]` |
| `raw(operator_string)` | append a content-stream operator |

### Flow blocks (advance `y` and paginate)

`para(text, size=10, leading=1.42, color=..., space_after=7, indent=0,
max_w=None)`
`heading(text, size=15, color=..., space_before=10, space_after=6, rule=False)`
`bullets(items, size=10, indent=16, marker="-" / color=...)`
`numbered(items, size=10, indent=20)`
`code(lines, size=8.2)`
`table(headers, rows, widths, size=8.6)`
`callout(title, text, fill=..., border=..., size=9.6)`
`severity_badge(label, color, x=None) -> x after the badge`

### `build(path, start_page=1)`

Writes the PDF, including a `/Info` dictionary (title, author, producer,
creation date). Returns the page count. `start_page` sets the number printed
in the footer page label.

---

## `style`

Module-level palette, read at draw time - assign before `build()`:

```python
style.NAVY = (0.06, 0.12, 0.26)
style.NAVY_SOFT = (0.15, 0.24, 0.44)
style.ACCENT = (0.13, 0.42, 0.78)
style.GREY = (0.42, 0.46, 0.53)
style.INK = (0.12, 0.14, 0.18)
style.RULE = (0.80, 0.84, 0.90)
style.PAPER = (0.965, 0.972, 0.985)
style.WHITE = (1, 1, 1)

style.SEV = {"CRITICAL": (...), "HIGH": (...), "MEDIUM": (...),
             "LOW": (...), "INFO": (...)}

style.severity_color(label, default=(0.32, 0.40, 0.55)) -> (r, g, b)
```

`severity_color` is lenient: it upper-cases, splits on spaces, dashes and
slashes, maps `CRIT`/`SEVERE`, `MODERATE`, `INFORMATIONAL`/`NONE`, and returns
`default` when nothing matches. `"HIGH - CWE-79"` resolves to `HIGH`.

---

## `check`

```python
from pdfsmith.check import check, text_of, CheckError

check("report.pdf")            # prints a report, raises CheckError on failure
info = check("report.pdf", verbose=False)   # -> {"pages": n, "characters": n}
text_of("report.pdf")          # readable text, one line per drawn line
```

CLI:

```bash
python3 -m pdfsmith.check report.pdf
python3 -m pdfsmith.check --text report.pdf
```

`check()` verifies, in order: the `%PDF` header and `%%EOF` trailer, the xref
table, that every `N 0 R` reference exists, the catalog -> pages -> kids
chain, that each page's `/Contents` is a real stream, that every font used in
a stream is declared by that page, and that pages carry text (page 1 only
needs something; later pages need 40+ characters by default).

`text_of()` also rebuilds lines by grouping fragments that share a baseline,
so a paragraph comes back as one line instead of one word per row.

---

## Module helpers

```python
from pdfsmith.doc import PAGE_W, PAGE_H, width_of, esc, inline_tokens, load_png

width_of("Hello", "bold", 12)      # -> points
esc("a (b)")                       # -> "a \\(b\\)"  (PDF string escaping)
inline_tokens("**b**, `c`")        # -> [("b","bold"), (", ","regular"), ...]
load_png("shot.png")               # -> dict(w, h, colours, space, samples, smask)
```

`load_png` raises `ValueError` for 16-bit, interlaced, or unreadable PNGs.
