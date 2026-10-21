"""Classic report palette. Override any name before calling Report()."""

NAVY = (0.06, 0.12, 0.26)
NAVY_SOFT = (0.15, 0.24, 0.44)
ACCENT = (0.13, 0.42, 0.78)
GREY = (0.42, 0.46, 0.53)
INK = (0.12, 0.14, 0.18)
RULE = (0.80, 0.84, 0.90)
PAPER = (0.965, 0.972, 0.985)
WHITE = (1, 1, 1)

SEV = {
    "CRITICAL": (0.72, 0.11, 0.11),
    "HIGH": (0.84, 0.36, 0.05),
    "MEDIUM": (0.80, 0.62, 0.05),
    "LOW": (0.20, 0.52, 0.35),
    "INFO": (0.32, 0.40, 0.55),
}


ALIASES = {"CRIT": "CRITICAL", "SEVERE": "CRITICAL", "IMPORTANT": "HIGH",
           "MODERATE": "MEDIUM", "INFORMATIONAL": "INFO", "NONE": "INFO"}


def severity_color(label, default=(0.32, 0.40, 0.55)):
    """Colour for a severity label, lenient about the exact wording.

    "HIGH", "high", "High - CWE-79" and "CRIT" all resolve; anything
    unrecognised falls back to the INFO grey.
    """
    text = str(label).upper()
    for word in text.replace("-", " ").replace("/", " ").split():
        word = ALIASES.get(word.strip(".,:;()[]"), word.strip(".,:;()[]"))
        if word in SEV:
            return SEV[word]
    return default
