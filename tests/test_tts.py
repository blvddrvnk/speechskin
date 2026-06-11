"""Tests for the tts facade module."""

from __future__ import annotations

import pytest

from tts_overlay import config, tts


def test_get_engine_caches(reset_engine):
    e1 = tts.get_engine()
    e2 = tts.get_engine()
    assert e1 is e2


def test_available_engines(reset_engine):
    assert "elevenlabs" in tts.available_engines()


def test_current_engine_key_default(monkeypatch):
    monkeypatch.setattr(config, "TTS_ENGINE", "ElevenLabs")
    assert tts.current_engine_key() == "elevenlabs"


def test_current_engine_key_handles_none(monkeypatch):
    monkeypatch.setattr(config, "TTS_ENGINE", None)
    assert tts.current_engine_key() == "elevenlabs"


def test_set_engine_rejects_unknown(reset_engine, temp_settings):
    with pytest.raises(ValueError):
        tts.set_engine("bogus")


def test_set_engine_persists(reset_engine, temp_settings):
    tts.set_engine("elevenlabs")
    import json
    data = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert data["TTS_ENGINE"] == "elevenlabs"


# -------------------------------------------- facade delegates to engine


def test_enumerate_voices_delegates(fake_engine):
    assert tts.enumerate_voices() == [(0, "Alpha (a0)"), (1, "Beta (b1)")]


def test_select_voice_delegates(fake_engine):
    result = tts.select_voice(1)
    assert result == "Beta (b1)"
    assert fake_engine.selected_voice == 1


def test_enumerate_audio_devices_delegates(fake_engine):
    assert tts.enumerate_audio_devices() == fake_engine.devices


def test_find_cable_device_delegates(fake_engine):
    assert tts.find_cable_device("cable") == 1


def test_supports_transcription_delegates(fake_engine):
    assert tts.supports_transcription() is True
    fake_engine._supports_stt = False
    assert tts.supports_transcription() is False


def test_transcribe_delegates(fake_engine):
    fake_engine.transcribe_result = "transcribed text"
    assert tts.transcribe(b"data") == "transcribed text"


def test_current_voice_description_delegates(fake_engine):
    assert tts.current_voice_description() == "Alpha (a0)"


def test_current_engine_display_name(fake_engine):
    assert tts.current_engine_display_name() == "Fake"


# ----------------------------------------------- speak_on_device guards


def test_speak_on_device_forwards(fake_engine):
    tts.speak_on_device("hi", 2)
    assert fake_engine.spoken == [("hi", 2)]


def test_speak_on_device_refuses_commands(fake_engine):
    tts.speak_on_device("/voice 1", 0)
    assert fake_engine.spoken == []


def test_speak_on_device_refuses_command_with_leading_space(fake_engine):
    tts.speak_on_device("   /exit", 0)
    assert fake_engine.spoken == []
