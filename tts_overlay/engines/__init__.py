"""TTS engine registry and factory.

Add a new backend by implementing :class:`~tts_overlay.engines.base.TTSEngine`
and registering it in :data:`_REGISTRY`. Select the active engine with
``config.TTS_ENGINE``.
"""

from __future__ import annotations

from .. import config, logutil
from .base import TTSEngine

log = logutil.get(__name__)

# Map of config.TTS_ENGINE value -> factory returning a TTSEngine instance.
# Factories are lazy so importing an engine's heavy/optional deps only happens
# when that engine is actually selected.


def _make_elevenlabs() -> TTSEngine:
    from .elevenlabs import ElevenLabsEngine
    return ElevenLabsEngine()


_REGISTRY = {
    "elevenlabs": _make_elevenlabs,
}


def available() -> list[str]:
    """Return the names of all registered engines."""
    return list(_REGISTRY)


def create(name: str | None = None) -> TTSEngine:
    """Instantiate the engine selected by *name* (defaults to config)."""
    key = (name or config.TTS_ENGINE or "elevenlabs").strip().lower()
    factory = _REGISTRY.get(key)
    if factory is None:
        log.error("Unknown TTS_ENGINE '%s'. Known: %s. Falling back to ElevenLabs.",
                  key, ", ".join(_REGISTRY))
        factory = _make_elevenlabs
    return factory()
