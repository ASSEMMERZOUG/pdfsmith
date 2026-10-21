# pdfsmith

A small PDF report builder, written for pentest reports. Standard library only.

Every other option wanted something from me first. LaTeX needs a TeX install.
HTML to PDF needs a browser engine. reportlab works but it is another package
to install on a box I might not control. A report is a list of blocks placed
on a page, and a PDF is a text file with an object graph, so this is about
600 lines of Python that I can read in one sitting and copy into a script.

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

That produces a cover, a contents page, two sections and a finding with a
severity chip. Findings can come from a loop, a CSV or a JSON file, so a
report per host is a `for` loop.

## Install

```
pip install git+https://github.com/ASSEMMERZOUG/pdfsmith
```

Or copy the `pdfsmith/` folder next to your script. Python 3.8 or newer,
nothing else.

## What you get

- Cover page, contents, section banners, tables, code blocks, callouts,
  captioned PNG figures, severity chips for findings.
- Contents page numbers that are actually right. The document renders twice
  and the second pass fills them in.
- Running header, footer and watermark.
- A checker that resolves the PDF object graph the way a viewer does, so a
  broken build fails in CI instead of in a client's inbox:

```
python3 -m pdfsmith.check report.pdf
```

## What it does not do

Base-14 fonts only (Helvetica, Helvetica-Bold, Courier), so no custom
typefaces and no Unicode past cp1252. A4 only. PNG figures, 8-bit and
non-interlaced. No reflow: you place blocks and the engine decides when one
needs a new page, but there are no columns or floats.

For those, use reportlab or WeasyPrint. This is for the report you have to
write this afternoon on a machine where you cannot install anything.

## Docs

- `docs/GUIDE.md` - install, first report, every block, styling, gotchas
- `docs/API.md` - method reference
- `examples/minimal.py` - two pages
- `examples/pentest_report.py` - a full client report with a generated chart

```
python3 examples/pentest_report.py pentest.pdf
python3 -m pdfsmith.check pentest.pdf
python3 -m unittest discover -s tests -v
```

MIT.
