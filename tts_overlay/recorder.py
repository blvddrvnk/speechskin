"""Microphone capture via PortAudio (``sounddevice``).

Records audio from an input device into memory and encodes it as a WAV byte
buffer suitable for sending to a speech-to-text backend.

A :class:`Recorder` supports toggle-style recording: call :meth:`start` to begin
capturing on a background stream, then :meth:`stop` to finish and obtain the
recorded audio as 16-bit mono PCM WAV bytes.

Device indices here are PortAudio indices (``sounddevice.query_devices``).
"""

from __future__ import annotations

import io
import threading
import time
import wave

from . import logutil

log = logutil.get(__name__)

# Speech-to-text works best at 16 kHz mono; this also matches the ElevenLabs
# ``pcm_s16le_16`` low-latency input format.
SAMPLE_RATE = 16000
CHANNELS = 1


def _import_sounddevice():
    """Import sounddevice lazily with a helpful error message."""
    try:
        import sounddevice as sd
        return sd
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "Microphone capture requires 'sounddevice'. "
            "Install it with:  pip install sounddevice"
        ) from exc


def enumerate_input_devices() -> list[tuple[int, str]]:
    """Return ``(index, name)`` for each PortAudio input-capable device."""
    try:
        sd = _import_sounddevice()
    except RuntimeError as exc:
        log.error("%s", exc)
        return []
    try:
        devices = sd.query_devices()
    except Exception as exc:  # noqa: BLE001
        log.error("Failed to query audio devices: %s", exc)
        return []
    out: list[tuple[int, str]] = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            out.append((idx, dev.get("name", f"device {idx}")))
    return out





def encode_wav(frames: bytes, sample_rate: int = SAMPLE_RATE,
               channels: int = CHANNELS) -> bytes:
    """Wrap raw 16-bit little-endian PCM *frames* in a WAV container."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)  # 16-bit
        wav.setframerate(sample_rate)
        wav.writeframes(frames)
    return buffer.getvalue()


class Recorder:
    """Toggle-style microphone recorder.

    Not raising is a design goal: a failed device open is logged and leaves the
    recorder in a clean ``not recording`` state so the UI can recover.
    """

    def __init__(self, device_index: int | None = None,
                 sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS,
                 voice_threshold: int = 650):
        self.device_index = device_index
        self.sample_rate = sample_rate
        self.channels = channels
        self.voice_threshold = voice_threshold
        self._stream = None
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()
        self._recording = False
        self._heard_voice = False
        self._last_voice_at: float | None = None

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def heard_voice(self) -> bool:
        return self._heard_voice

    def seconds_since_voice(self) -> float | None:
        last_voice_at = self._last_voice_at
        if last_voice_at is None:
            return None
        return time.monotonic() - last_voice_at



    def _chunk_has_voice(self, raw: bytes) -> bool:
        if len(raw) < 2:
            return False
        samples = memoryview(raw[:len(raw) - len(raw) % 2]).cast("h")
        return any(abs(sample) >= self.voice_threshold for sample in samples)

    def _on_audio(self, indata, _frames, _time, _status) -> None:
        # indata is an int16 numpy array; store raw little-endian bytes.
        try:
            raw = bytes(indata)
            with self._lock:
                self._chunks.append(raw)
                if self._chunk_has_voice(raw):
                    self._heard_voice = True
                    self._last_voice_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            log.debug("Recorder callback error (ignored): %s", exc)

    def start(self) -> bool:
        """Begin recording. Returns True on success, False on failure."""
        if self._recording:
            return True
        try:
            sd = _import_sounddevice()
        except RuntimeError as exc:
            log.error("%s", exc)
            return False
        with self._lock:
            self._chunks = []
            self._heard_voice = False
            self._last_voice_at = None
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype="int16",
                device=self.device_index,
                callback=self._on_audio,
            )
            self._stream.start()
            self._recording = True
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to start recording: %s", exc)
            self._stream = None
            self._recording = False
            return False

    def stop(self) -> bytes:
        """Stop recording and return the captured audio as WAV bytes.

        Returns an empty ``bytes`` object if nothing was recorded.
        """
        raw, _sr, _ch, _sw = self.stop_raw()
        if not raw:
            return b""
        return encode_wav(raw, self.sample_rate, self.channels)

    def stop_raw(self) -> tuple[bytes, int, int, int]:
        """Stop recording and return raw PCM frames with format metadata.

        Returns ``(pcm_bytes, sample_rate, channels, sample_width)`` where
        *sample_width* is in bytes (2 for 16-bit).  Returns ``(b"", 0, 0, 0)``
        if nothing was recorded.

        This is the low-latency alternative to :meth:`stop` — it skips WAV
        encoding entirely, saving ~10-20 ms that would otherwise be wasted
        encoding and then immediately re-parsing the header.
        """
        if not self._recording:
            return b"", 0, 0, 0
        self._recording = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as exc:  # noqa: BLE001
            log.error("Error stopping recording stream: %s", exc)
        finally:
            self._stream = None

        with self._lock:
            frames = b"".join(self._chunks)
            self._chunks = []

        if not frames:
            return b"", 0, 0, 0
        return frames, self.sample_rate, self.channels, 2  # 2 = 16-bit
