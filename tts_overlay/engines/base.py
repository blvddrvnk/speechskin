"""TTS engine abstraction.

The app supports swappable text-to-speech backends. Each backend implements
:class:`TTSEngine`.

The engine is the single source of truth for "what are my output devices"
and "speak this text on device N". The rest of the app stays engine-agnostic:
it asks the active engine to enumerate devices, find the virtual cable, and
speak.
"""

from __future__ import annotations

import abc


class TTSEngine(abc.ABC):
    """Common interface every TTS backend must implement."""

    #: Human-readable name, shown in the startup banner.
    name: str = "tts"

    def startup_check(self) -> None:
        """Validate configuration / credentials at startup.

        Override to raise a clear error (or log a warning) if the engine
        cannot run. The default implementation does nothing.
        """

    @abc.abstractmethod
    def enumerate_voices(self) -> list[tuple[int, str]]:
        """Return ``(index, description)`` for each available voice."""

    def invalidate_cache(self) -> None:
        """Clear any cached data like voices, forcing a fresh fetch on next call."""
        # The default implementation does nothing.

    def current_voice_description(self) -> str:
        """Return a human-readable description of the currently selected voice."""
        from .. import config as _config
        voices = dict(self.enumerate_voices())
        return voices.get(_config.TTS_VOICE_INDEX,
                          f"Voice #{_config.TTS_VOICE_INDEX}")

    def select_voice(self, index: int) -> str:
        """Persist *index* (into :meth:`enumerate_voices`) as the active voice.

        Returns a short human-readable confirmation of what was selected.
        Each engine decides how a voice is pinned, keeping selection logic
        with the backend. The default stores ``TTS_VOICE_INDEX`` via the
        settings layer.
        """
        from .. import settings
        settings.set("TTS_VOICE_INDEX", int(index))
        voices = dict(self.enumerate_voices())
        return voices.get(index, f"voice #{index}")

    @abc.abstractmethod
    def enumerate_audio_devices(self) -> list[tuple[int, str]]:
        """Return ``(index, name)`` for each audio *output* device."""

    @abc.abstractmethod
    def find_cable_device(self, keyword: str) -> int | None:
        """Return the device index whose name contains *keyword*, or None."""

    @property
    def supports_dual_output(self) -> bool:
        """Whether this engine can play on two devices without double-speaking.

        If ``False``, the overlay runs each target device sequentially instead
        of in parallel. Override in a backend that cannot share a single render
        across multiple outputs.
        """
        return True

    @abc.abstractmethod
    def speak(self, text: str, device_index: int | None | list[int | None]) -> None:
        """Speak *text* on a specific output device or list of devices.

        ``device_index`` of ``None`` means the system default device.
        Implementations must never raise; errors are logged so a single
        failed utterance cannot take down the app.
        """

    def speak_streaming(self, text: str, device_index: int | None | list[int | None]) -> None:
        """Speak *text* with minimal latency by streaming audio as it arrives.

        Backends that support streaming should override this to start playback
        before the full synthesis response is received.  The default falls back
        to :meth:`speak` so all existing engines remain compatible.
        """
        self.speak(text, device_index)

    @property
    def supports_streaming(self) -> bool:
        """Whether this engine implements low-latency :meth:`speak_streaming`.

        Defaults to ``False``.  Override in backends that provide a real
        streaming implementation.
        """
        return False

    # -- speech-to-text (optional) --

    @property
    def supports_transcription(self) -> bool:
        """Whether this engine can transcribe audio (speech-to-text).

        Defaults to ``False``. Backends that implement :meth:`transcribe`
        should override this to return ``True``.
        """
        return False

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcribe WAV audio *wav_bytes* to text.

        The default raises :class:`NotImplementedError`. Backends advertising
        :attr:`supports_transcription` must override this. Implementations may
        raise on failure; callers are expected to handle errors.
        """
        raise NotImplementedError(
            f"{self.name} does not support transcription"
        )



