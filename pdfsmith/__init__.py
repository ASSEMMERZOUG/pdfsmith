"""pdfsmith - build clean PDF reports with nothing but the Python standard
library.

Two layers, use whichever you need:

    from pdfsmith import Report   # high level: cover, contents, sections
    from pdfsmith import Doc      # low level: place text and shapes yourself

    r = Report(title="Acme - web assessment", header="ACME | Page %d")
    r.cover(kicker="Penetration Test Report", title=["Acme"],
            facts=[("Client", "Acme Ltd")])
    r.section("1", "Summary")
    r.para("Findings **first**, evidence after.")
    r.build("acme.pdf")
"""
from .doc import Doc, PAGE_W, PAGE_H
from .report import Report
from . import style

__version__ = "1.0.0"
__all__ = ["Doc", "Report", "style", "PAGE_W", "PAGE_H"]
