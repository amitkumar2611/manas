"""Perception & actuation layer: screen (OCR), voice, browser, calendar.

Everything here is backend-pluggable. Capabilities degrade gracefully and
HONESTLY: a missing backend (no display, no mic, no Playwright browsers)
raises a clear ManasError naming exactly what to install — never a fake result.
"""
from manas.perception import browser, calendar_i, desktop, screen, voice  # noqa: F401
