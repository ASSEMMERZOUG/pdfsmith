#!/usr/bin/env python3
"""The smallest useful report: cover, contents, two sections, one table.

Run it:
    python3 examples/minimal.py minimal.pdf
"""
import os
import sys

# run straight from a checkout, no install needed
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pdfsmith import Report  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "minimal.pdf"

r = Report(
    title="Q3 platform review",
    header="ACME PLATFORM | Q3 REVIEW | Page %d",
    footer="Prepared for the platform team - internal",
    watermark="ACME",
)

r.cover(
    kicker="Status report",
    title=["Q3 platform", "review"],
    subtitle="What shipped, what it cost, and what comes next.",
    facts=[
        ("Owner", "Platform team"),
        ("Period", "July - September 2026"),
        ("Status", "On track"),
        ("Next review", "15 January 2027"),
    ],
    blurb=[
        "Three of the four roadmap items shipped. The database migration "
        "slipped by two weeks and is now the only open item.",
    ],
)

r.toc()

r.section("1", "Outcomes")
r.para("The quarter had four planned outcomes. **Three shipped**, one moved "
       "to Q4 with a revised estimate.")
r.bullets([
    "Search now answers in **under 300 ms** at p95 (was 1.4 s).",
    "Billing moved to the new provider; the old integration is removed.",
    "On-call runbooks rewritten and tested in two game days.",
])
r.para("The database migration is the outstanding item; it needs a longer "
       "maintenance window than the team can get before December.")

r.section("2", "Cost")
r.para("Spend tracked within 4% of plan. `Search` is the only line over "
       "budget, from the extra read replicas.")
r.table(
    ["Line", "Plan (EUR)", "Actual (EUR)", "Delta"],
    [["Compute", "4,200", "4,110", "-90"],
     ["Storage", "900", "870", "-30"],
     ["Search reads", "1,500", "1,890", "+390"],
     ["Monitoring", "400", "400", "0"]],
    widths=[2.2, 1.1, 1.1, 0.8],
)
r.callout("Decision needed",
          "Approve **EUR 390** of overage, or cap search concurrency and "
          "accept slower queries during peaks.")

pages = r.build(out)
print("%s: %d pages" % (out, pages))
