"""Centralised logging.

Logs go to stderr. The whole point of the rewrite is that nothing should ever
crash the process silently, so we log loudly instead of dying.
"""

import logging
import sys

_CONFIGURED = False


def setup() -> None:
    """Configure root logging once. Safe to call multiple times."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    # Make sure the console can render unicode without blowing up.
    try:
        if sys.stdout and sys.stdout.encoding and \
                sys.stdout.encoding.lower() != "utf-8":
            sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("  [%(levelname)s] %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    _CONFIGURED = True


def get(name: str) -> logging.Logger:
    """Return a named logger. Call :func:`setup` once at startup first."""
    return logging.getLogger(name)
