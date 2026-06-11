"""Tests for the shared speech routing logic."""

from __future__ import annotations

import pytest

from tts_overlay import config, speech
from tts_overlay import shutdown as sd


@pytest.fixture(autouse=True)
def clear_shutdown():
    sd.shutdown_event.clear()
    yield
    sd.shutdown_event.clear()


# ------------------------------------------------- target resolution


def test_targets_cable_and_speaker(monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "SPEAKER_DEVICE_INDEX", 2)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", True)
    assert speech._resolve_targets(1, 2) == [1, 2]


def test_targets_cable_only_when_speakers_off(monkeypatch):
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    assert speech._resolve_targets(1, 2) == [1]


def test_targets_speaker_only_when_no_cable(monkeypatch):
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", True)
    assert speech._resolve_targets(None, 2) == [2]


def test_targets_fallback_to_default_when_nothing(monkeypatch):
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    # No cable, speakers off -> still produce one default target.
    assert speech._resolve_targets(None, None) == [None]


# ------------------------------------------------- speak_to_devices


def test_speak_to_devices_parallel(fake_engine, monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "SPEAKER_DEVICE_INDEX", 2)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", True)
    fake_engine._supports_dual = True

    speech.speak_to_devices("hello")

    spoken_devices = sorted(d for _, d in fake_engine.spoken)
    assert spoken_devices == [1, 2]
    assert all(text == "hello" for text, _ in fake_engine.spoken)


def test_speak_to_devices_sequential(fake_engine, monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "SPEAKER_DEVICE_INDEX", 2)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", True)
    fake_engine._supports_dual = False

    speech.speak_to_devices("world")

    assert ("world", 1) in fake_engine.spoken
    assert ("world", 2) in fake_engine.spoken


def test_speak_to_devices_empty_text_noop(fake_engine):
    speech.speak_to_devices("")
    assert fake_engine.spoken == []


def test_speak_to_devices_skips_when_shutdown(fake_engine):
    sd.shutdown_event.set()
    speech.speak_to_devices("hello")
    assert fake_engine.spoken == []


def test_speak_to_devices_never_raises(monkeypatch, fake_engine):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    fake_engine._supports_dual = False

    def boom(text, device_index):
        raise RuntimeError("boom")

    monkeypatch.setattr("tts_overlay.tts.speak_on_device", boom)
    # Must swallow the error.
    speech.speak_to_devices("hello")


# ----------------------------------------- speak_to_devices_streaming


def test_speak_streaming_uses_stream_when_supported(fake_engine, monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    fake_engine._supports_streaming = True

    speech.speak_to_devices_streaming("hi")

    assert ("hi", 1) in fake_engine.streamed
    assert fake_engine.spoken == []


def test_speak_streaming_falls_back_when_not_supported(fake_engine, monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    fake_engine._supports_streaming = False
    fake_engine._supports_dual = False

    speech.speak_to_devices_streaming("hi")

    assert ("hi", 1) in fake_engine.spoken
    assert fake_engine.streamed == []


def test_speak_streaming_secondary_targets_use_normal_speak(
    fake_engine, monkeypatch
):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "SPEAKER_DEVICE_INDEX", 2)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", True)
    fake_engine._supports_streaming = True

    speech.speak_to_devices_streaming("hello")

    # Primary (cable) goes via streaming.
    assert ("hello", 1) in fake_engine.streamed
    # Secondary (speaker) goes via normal speak_on_device.
    assert ("hello", 2) in fake_engine.spoken


def test_speak_streaming_empty_text_noop(fake_engine):
    speech.speak_to_devices_streaming("")
    assert fake_engine.streamed == []
    assert fake_engine.spoken == []


def test_speak_streaming_skips_when_shutdown(fake_engine):
    sd.shutdown_event.set()
    speech.speak_to_devices_streaming("hello")
    assert fake_engine.streamed == []
    assert fake_engine.spoken == []


def test_speak_streaming_never_raises(fake_engine, monkeypatch):
    monkeypatch.setattr(config, "CABLE_DEVICE_INDEX", 1)
    monkeypatch.setattr(config, "PLAY_ON_SPEAKERS", False)
    fake_engine._supports_streaming = True

    def boom(text, device_index):
        raise RuntimeError("boom")

    monkeypatch.setattr(fake_engine, "speak_streaming", boom)
    # Must swallow the error.
    speech.speak_to_devices_streaming("hello")
