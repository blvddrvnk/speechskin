"""Persistent runtime settings layer.

``config.py`` holds the hand-edited *defaults*. A handful of settings can also
be changed at runtime via the overlay's slash commands (the active engine, the
selected voice, ...). Those changes are persisted to ``settings.json`` next to
the project so they survive a restart, *without* rewriting the commented
``config.py``.

How it works
------------
* :func:`apply` is called once at startup. It reads ``settings.json`` and
  copies any saved overrides onto the live ``config`` module, so every existing
  ``config.X`` read across the app transparently sees the user's last choice.
* :func:`set` updates the live ``config`` attribute *and* writes the override
  back to disk.

Only the keys in :data:`PERSISTED_KEYS` are ever saved, so we never accidentally
serialize appearance/timing constants that belong solely to ``config.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import config, logutil

log = logutil.get(__name__)

# settings.json lives at the repo root (parent of the tts_overlay package),
# alongside secrets.env.
SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

# The only config keys that runtime commands may change and persist.
PERSISTED_KEYS = (
    "TTS_ENGINE",
    "TTS_VOICE_INDEX",
    "ELEVENLABS_VOICE_ID",
    "CABLE_DEVICE_INDEX",
    "SPEAKER_DEVICE_INDEX",
    "PLAY_ON_SPEAKERS",
    "MIC_DEVICE_INDEX",
    "ALLOW_OVERLAY",
    "SKIN_PTT_KEY",
    "TARGET_PTT_KEY",
    "ACTIVE_PROFILE",
    "PROFILES",
)

_overrides: dict[str, object] = {}


def _read_file() -> dict[str, object]:
    try:
        if SETTINGS_PATH.is_file():
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read settings file %s: %s", SETTINGS_PATH, exc)
    return {}


def _write_file() -> None:
    try:
        SETTINGS_PATH.write_text(
            json.dumps(_overrides, indent=2) + "\n", encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not write settings file %s: %s", SETTINGS_PATH, exc)


def apply() -> None:
    """Load saved overrides and apply them onto the live ``config`` module."""
    global _overrides
    _overrides = {}
    for key, value in _read_file().items():
        if key in PERSISTED_KEYS and hasattr(config, key):
            _overrides[key] = value
            setattr(config, key, value)
    if _overrides:
        log.info("Applied persisted settings: %s", ", ".join(_overrides))


def set(key: str, value: object) -> None:
    """Set a persisted ``config`` value at runtime and save it to disk."""
    if key not in PERSISTED_KEYS:
        raise KeyError(f"'{key}' is not a persistable setting")
    setattr(config, key, value)
    _overrides[key] = value
    _write_file()
