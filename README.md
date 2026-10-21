# pdfsmith

Pentest reports as a list of blocks. JSON in, PDF out.

```
python3 -m pdfsmith report.json -o report.pdf
```

No LaTeX, no browser, no reportlab. Python 3.8 and the standard library.

I write a report per box and per engagement, and the report never starts from a
blank page: cover, contents, findings with severity chips, an appendix of
commands, and a fixing section. Every PDF tool I tried wanted an install I
could not do on the machine I was on - a TeX distribution, a headless browser,
a package that pulls forty others. A report is blocks of text on paper, and a
PDF is an object graph, so this is a few hundred lines of Python I can read in
one sitting and copy into a script.

## Install

```
pip install git+https://github.com/ASSEMMERZOUG/pdfsmith
```

From a checkout, no install needed - run the examples:

```
git clone https://github.com/ASSEMMERZOUG/pdfsmith
cd pdfsmith
python3 examples/pentest_report.py /tmp/pentest.pdf
```

## Command line

Describe the report in JSON:

```json
{
  "title": "Acme - web assessment",
  "header": "ACME | Page %d",
  "footer": "Acme Ltd - confidential",
  "output": "acme.pdf",
  "cover": {
    "kicker": "Penetration test report",
    "title": ["Acme", "web assessment"],
    "subtitle": "One critical finding in the customer portal.",
    "facts": [["Client", "Acme Ltd"], ["Scope", "portal.acme.example"]],
    "badge": "1 CRITICAL"
  },
  "toc": true,
  "blocks": [
    {"section": {"num": "1", "title": "Executive summary"}},
    {"para": "Any customer can read any invoice. That is the one to fix."},
    {"section": {"num": "2", "title": "Findings"}},
    {"finding": {
      "id": "F-01", "severity": "CRITICAL",
      "title": "Any customer can read any invoice",
      "where": "GET /api/invoices/{id}",
      "what": "The endpoint never checks who owns the invoice.",
      "proof": ["GET /api/invoices/10481", "", "200 OK"],
      "impact": "Billing data for every other customer.",
      "fix": ["Scope the query by the session's account."]
    }}
  ]
}
```

```
$ python3 -m pdfsmith report.json
wrote acme.pdf (4 pages)
```

Block types: `section`, `para`, `bullets`, `numbered`, `quote`, `h2`, `h3`,
`table`, `code`, `callout`, `figure`, `kv`, `finding`, `spacer`, `pagebreak`.
The full schema is in [`docs/GUIDE.md`](docs/GUIDE.md#command-line).

The build is checked before the command returns: the PDF is read back the way
a viewer reads it, and a dangling reference, a missing font or an empty page
fails with exit status 1, so it drops into CI. `--no-check` skips it.

## From Python

When the report comes from a loop, a CSV or your own data, skip the JSON:

```python
from pdfsmith import Report

r = Report(title="Acme - web assessment", header="ACME | Page %d",
           footer="Client confidential")

r.cover(kicker="Penetration test report",
        title=["Acme", "web assessment"],
        subtitle="Three findings across the customer portal.",
        facts=[("Client", "Acme Ltd"), ("Date", "21 October 2026")])

r.toc()
r.section("1", "Executive summary")
r.para("One critical issue: **any customer can read any invoice**.")

r.finding("F-01", "CRITICAL", "Any customer can read any invoice",
          where="GET /api/invoices/{id}",
          what="The endpoint never checks who owns the invoice.",
          proof=["GET /api/invoices/10481", "", "200 OK"],
          impact="Billing data for every other customer.",
          fix=["Scope the query by the session's account."])

r.build("acme.pdf")
```

The contents page numbers are not maintained by hand: the document renders
twice, and the second pass fills in where each section landed.

## What it does

- Cover page, contents, section banners, tables, code blocks, callouts,
  captioned PNG figures, severity chips for findings.
- Contents page numbers that are actually right.
- Running header, footer and diagonal watermark.
- Structural checker, usable on its own: `python3 -m pdfsmith.check file.pdf`.
- Text extraction, for grepping a finished report: `--text`.

## What it does not do

Base-14 fonts only (Helvetica, Helvetica-Bold, Courier), so no custom typefaces
and no Unicode past cp1252. A4 only. PNG figures, 8-bit and non-interlaced. No
columns or floats; blocks flow, and the engine decides when one needs a new
page.

For those, use reportlab or WeasyPrint. This is for the report you have to
write this afternoon on a machine where you cannot install anything.

## Docs and tests

- [`docs/GUIDE.md`](docs/GUIDE.md) - the JSON schema, every block, styling,
  page geometry, gotchas
- [`docs/API.md`](docs/API.md) - method reference
- `examples/minimal.py` - two pages
- `examples/pentest_report.py` - a full client report with a generated chart
- `examples/report.json` - the same document through the command line

```
python3 -m unittest discover -s tests -v
```

MIT.
