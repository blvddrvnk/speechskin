"""Global hotkey registration and a watchdog that keeps it alive.

The ``keyboard`` module runs an internal listener thread. If that thread ever
dies (which is the most common cause of "the script just stops working"), the
hotkey silently stops firing. The watchdog detects this and re-registers.
"""

from __future__ import annotations

import threading

import keyboard

from . import config, logutil
from . import shutdown as sd

log = logutil.get(__name__)


def install_hotkey() -> None:
    """Register (or re-register) the global hotkey. Never raises."""
    try:
        keyboard.add_hotkey(
            config.HOTKEY,
            lambda: _on_hotkey_pressed(),
            suppress=True,
        )
        log.info("Hotkey registered: %s", config.HOTKEY.upper())
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to register hotkey '%s': %s", config.HOTKEY, exc)


def _on_hotkey_pressed() -> None:
    """Handle hotkey press; only toggle if overlay is enabled."""
    if config.ALLOW_OVERLAY:
        sd.toggle_event.set()


def _listener_alive() -> bool:
    """Best-effort check that the keyboard listener thread is alive."""
    try:
        listener = getattr(keyboard, "_listener", None)
        if listener is None:
            return False
        # The listener exposes a `listening` flag and/or a thread.
        thread = getattr(listener, "listening_thread", None)
        if thread is not None:
            return bool(thread.is_alive())
        # Fall back to the `listening` attribute if present.
        return bool(getattr(listener, "listening", True))
    except Exception as exc:  # noqa: BLE001
        log.debug("Could not inspect keyboard listener: %s", exc)
        # Assume alive to avoid pointless re-registration storms.
        return True


def start_watchdog() -> threading.Thread:
    """Start the background watchdog thread and return it."""

    def _run() -> None:
        while not sd.shutdown_event.is_set():
            sd.shutdown_event.wait(timeout=config.WATCHDOG_INTERVAL)
            if sd.shutdown_event.is_set():
                break
            try:
                if not _listener_alive():
                    log.warning("Keyboard listener died - restarting...")
                    try:
                        keyboard.unhook_all_hotkeys()
                    except Exception:  # noqa: BLE001
                        pass
                    install_hotkey()
            except Exception as exc:  # noqa: BLE001
                log.debug("Watchdog iteration error (ignored): %s", exc)

    watchdog = threading.Thread(target=_run, name="hotkey-watchdog", daemon=True)
    watchdog.start()
    return watchdog


def teardown() -> None:
    """Remove all hotkeys. Never raises."""
    try:
        keyboard.unhook_all_hotkeys()
    except Exception as exc:  # noqa: BLE001
        log.debug("unhook_all_hotkeys failed: %s", exc)
