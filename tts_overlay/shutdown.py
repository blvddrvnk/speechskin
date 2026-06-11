"""Process-wide shutdown / event coordination.

A small set of threading.Event objects used to communicate between the
keyboard listener, TTS worker threads, and the Tk main loop without ever
touching Tk from a non-Tk thread.
"""

import threading

from . import logutil

log = logutil.get(__name__)

# Set when the program should exit at the next opportunity.
shutdown_event = threading.Event()

# Set by the hotkey to ask the overlay to toggle visibility.
toggle_event = threading.Event()

# Set by a TTS worker right before speaking so the overlay hides itself.
hide_event = threading.Event()

# Set by a TTS worker after speaking so the overlay re-enables the entry.
post_speak_event = threading.Event()


def request_shutdown(*_args) -> None:
    """Signal the program to exit. Idempotent and crash-proof."""
    if not shutdown_event.is_set():
        log.info("Shutting down...")
        shutdown_event.set()
