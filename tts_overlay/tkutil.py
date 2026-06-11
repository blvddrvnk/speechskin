"""Shared Tk utilities for the SpeechSkin UI modules.

Small helpers used by both the overlay and the settings window, extracted here
so the same code isn't duplicated across modules.
"""

from __future__ import annotations

import functools
import tkinter as tk

from . import logutil

log = logutil.get(__name__)


def safe(method):
    """Decorator: never let a Tk callback raise into the event loop.

    Every Tk callback in SpeechSkin is wrapped with this so a transient
    ``TclError`` (very common while alt-tabbing on Windows) is logged and
    swallowed instead of bubbling up and killing the process.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except tk.TclError as exc:
            log.debug("Tk error in %s (ignored): %s", method.__name__, exc)
        except Exception as exc:  # noqa: BLE001
            log.warning("Error in %s (ignored): %s", method.__name__, exc)
        return None

    return wrapper


def device_label(index: int | None, name: str) -> str:
    """Render a dropdown label for an audio device."""
    if index is None:
        return name
    return f"[{index}] {name}"
