"""Text-to-speech facade.

The actual synthesis lives in swappable backends under
:mod:`tts_overlay.engines`. This module exposes a single active engine
(selected by ``config.TTS_ENGINE``) and thin module-level helpers so the rest
of the app stays backend-agnostic.
"""

from __future__ import annotations

from . import config, engines, logutil, settings
from .engines.base import TTSEngine

log = logutil.get(__name__)

_engine: TTSEngine | None = None


def get_engine() -> TTSEngine:
    """Return the active TTS engine, creating it on first use."""
    global _engine
    if _engine is None:
        _engine = engines.create()
    return _engine


def available_engines() -> list[str]:
    """Return the names of all registered/selectable engines."""
    return engines.available()


def current_engine_key() -> str:
    """Return the config key (e.g. ``"elevenlabs"``) of the active engine."""
    return (config.TTS_ENGINE or "elevenlabs").strip().lower()


def set_engine(name: str) -> TTSEngine:
    """Switch the active engine at runtime, persist the choice, and return it.

    Rebuilds the engine instance so its (lazy) backend is freshly initialised.
    """
    global _engine
    key = name.strip().lower()
    if key not in engines.available():
        raise ValueError(f"Unknown engine '{name}'")
    settings.set("TTS_ENGINE", key)
    _engine = engines.create(key)
    return _engine


def current_engine_display_name() -> str:
    return get_engine().name


def current_voice_description() -> str:
    return get_engine().current_voice_description()


def enumerate_voices() -> list[tuple[int, str]]:
    """Return ``(index, description)`` for each voice of the active engine."""
    return get_engine().enumerate_voices()


def select_voice(index: int) -> str:
    """Select the voice at *index* for the active engine and persist it."""
    return get_engine().select_voice(index)


def invalidate_cache() -> None:
    """Clear cached data in the active engine to force fresh queries."""
    get_engine().invalidate_cache()


def enumerate_audio_devices() -> list[tuple[int, str]]:
    return get_engine().enumerate_audio_devices()


def find_cable_device(keyword: str) -> int | None:
    """Find the virtual cable device index for the active engine."""
    return get_engine().find_cable_device(keyword)


def supports_transcription() -> bool:
    """Whether the active engine can transcribe audio (speech-to-text)."""
    return get_engine().supports_transcription


def transcribe(wav_bytes: bytes) -> str:
    """Transcribe WAV *wav_bytes* to text using the active engine."""
    return get_engine().transcribe(wav_bytes)


def speak_on_device(text: str, device_index: int | None) -> None:
    """Speak *text* on a specific device using the active engine.

    Text starting with ``/`` is a command and is never forwarded to the engine.
    """
    if text.lstrip().startswith("/"):
        log.warning("Refusing to speak command-like text (starts with '/').")
        return
    get_engine().speak(text, device_index)


