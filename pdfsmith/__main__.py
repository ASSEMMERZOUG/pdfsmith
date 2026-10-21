"""`python3 -m pdfsmith report.json -o report.pdf`"""
import sys

from .build import main

sys.exit(main())
