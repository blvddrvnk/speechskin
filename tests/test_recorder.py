"""Tests for the microphone recorder module."""

from __future__ import annotations

import io
import sys
import types
import wave

import pytest

from tts_overlay import recorder


# --------------------------------------------------------- encode_wav


def test_encode_wav_produces_valid_wav():
    frames = b"\x01\x00\x02\x00\x03\x00"  # 3 int16 samples
    data = recorder.encode_wav(frames, sample_rate=16000, channels=1)
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == 16000
        assert wav.readframes(3) == frames


def test_encode_wav_empty_frames():
    data = recorder.encode_wav(b"")
    with wave.open(io.BytesIO(data), "rb") as wav:
        assert wav.getnframes() == 0


# --------------------------------------------- fake sounddevice harness


class FakeStream:
    def __init__(self, callback=None, **kwargs):
        self.callback = callback
        self.started = False
        self.stopped = False
        self.closed = False
        self.kwargs = kwargs

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def close(self):
        self.closed = True

    def feed(self, raw: bytes):
        """Simulate a PortAudio callback delivering *raw* int16 bytes."""
        self.callback(raw, len(raw) // 2, None, None)


class FakeSounddevice(types.ModuleType):
    def __init__(self, devices=None, fail_stream=False):
        super().__init__("sounddevice")
        self._devices = devices or [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "Speakers", "max_input_channels": 0,
             "max_output_channels": 2},
        ]
        self._fail_stream = fail_stream
        self.last_stream: FakeStream | None = None

    def query_devices(self, *args, **kwargs):
        return self._devices

    def InputStream(self, callback=None, **kwargs):
        if self._fail_stream:
            raise RuntimeError("device busy")
        self.last_stream = FakeStream(callback=callback, **kwargs)
        return self.last_stream


@pytest.fixture
def fake_sd(monkeypatch):
    fake = FakeSounddevice()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    return fake


# ------------------------------------------------- device enumeration


def test_enumerate_input_devices(fake_sd):
    devices = recorder.enumerate_input_devices()
    assert devices == [(0, "Mic")]






def test_enumerate_input_devices_handles_import_error(monkeypatch):
    # Remove sounddevice so the lazy import fails.
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    assert recorder.enumerate_input_devices() == []


# -------------------------------------------------------- Recorder


def test_recorder_start_stop_captures_audio(fake_sd):
    rec = recorder.Recorder(device_index=0)
    assert rec.start() is True
    assert rec.is_recording is True

    # Simulate incoming audio.
    fake_sd.last_stream.feed(b"\x01\x00\x02\x00")
    fake_sd.last_stream.feed(b"\x03\x00\x04\x00")

    wav_bytes = rec.stop()
    assert rec.is_recording is False
    assert fake_sd.last_stream.stopped
    assert fake_sd.last_stream.closed

    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        assert wav.readframes(4) == b"\x01\x00\x02\x00\x03\x00\x04\x00"


def test_recorder_tracks_voice_activity(fake_sd):
    rec = recorder.Recorder(device_index=0, voice_threshold=500)
    rec.start()

    fake_sd.last_stream.feed(b"\x0a\x00")  # 10, below threshold
    assert rec.heard_voice is False
    assert rec.seconds_since_voice() is None

    fake_sd.last_stream.feed(b"\x58\x02")  # 600, above threshold

    assert rec.heard_voice is True
    assert rec.seconds_since_voice() is not None


def test_recorder_stop_without_start_returns_empty(fake_sd):
    rec = recorder.Recorder()
    assert rec.stop() == b""


def test_recorder_stop_with_no_audio_returns_empty(fake_sd):
    rec = recorder.Recorder()
    rec.start()
    wav_bytes = rec.stop()
    assert wav_bytes == b""


def test_recorder_double_start_is_idempotent(fake_sd):
    rec = recorder.Recorder()
    assert rec.start() is True
    assert rec.start() is True  # already recording


def test_recorder_start_failure_returns_false(monkeypatch):
    fake = FakeSounddevice(fail_stream=True)
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    rec = recorder.Recorder()
    assert rec.start() is False
    assert rec.is_recording is False


def test_recorder_start_without_sounddevice(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", None)
    rec = recorder.Recorder()
    assert rec.start() is False
