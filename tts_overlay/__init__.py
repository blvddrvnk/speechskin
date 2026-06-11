"""SpeechSkin package.

A floating text input that appears on a global hotkey, speaks typed text
through ElevenLabs, and routes audio to a virtual audio cable.
"""

from . import config

__all__ = ["config", "run"]


def run() -> None:
    """Entry point — start the overlay application."""
    from .app import main

    main()
