"""Tests for the persistent settings layer."""

from __future__ import annotations

import json

import pytest

from tts_overlay import config, settings


def test_set_persists_to_disk(temp_settings):
    settings.set("PLAY_ON_SPEAKERS", False)
    assert temp_settings.is_file()
    data = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert data["PLAY_ON_SPEAKERS"] is False


def test_set_updates_live_config(temp_settings):
    settings.set("TTS_VOICE_INDEX", 7)
    assert config.TTS_VOICE_INDEX == 7


def test_set_rejects_unknown_key(temp_settings):
    with pytest.raises(KeyError):
        settings.set("NOT_A_REAL_KEY", 123)


def test_set_allows_mic_device_index(temp_settings):
    settings.set("MIC_DEVICE_INDEX", 3)
    assert config.MIC_DEVICE_INDEX == 3
    data = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert data["MIC_DEVICE_INDEX"] == 3


def test_set_allows_none_value(temp_settings):
    settings.set("CABLE_DEVICE_INDEX", None)
    assert config.CABLE_DEVICE_INDEX is None
    data = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert data["CABLE_DEVICE_INDEX"] is None


def test_apply_loads_overrides(temp_settings, monkeypatch):
    temp_settings.write_text(
        json.dumps({"TTS_VOICE_INDEX": 4, "PLAY_ON_SPEAKERS": False}),
        encoding="utf-8",
    )
    settings.apply()
    assert config.TTS_VOICE_INDEX == 4
    assert config.PLAY_ON_SPEAKERS is False


def test_apply_ignores_unknown_keys(temp_settings):
    temp_settings.write_text(
        json.dumps({"BOGUS_KEY": 1, "TTS_VOICE_INDEX": 9}),
        encoding="utf-8",
    )
    settings.apply()
    assert not hasattr(config, "BOGUS_KEY")
    assert config.TTS_VOICE_INDEX == 9


def test_apply_handles_missing_file(temp_settings):
    assert not temp_settings.exists()
    # Should not raise.
    settings.apply()


def test_apply_handles_corrupt_file(temp_settings):
    temp_settings.write_text("{ this is not json", encoding="utf-8")
    # Should not raise; just ignore.
    settings.apply()


def test_mic_device_index_in_persisted_keys():
    assert "MIC_DEVICE_INDEX" in settings.PERSISTED_KEYS


def test_roundtrip_multiple_keys(temp_settings):
    settings.set("TTS_ENGINE", "elevenlabs")
    settings.set("TTS_VOICE_INDEX", 2)
    settings.set("SPEAKER_DEVICE_INDEX", 5)
    data = json.loads(temp_settings.read_text(encoding="utf-8"))
    assert data == {
        "TTS_ENGINE": "elevenlabs",
        "TTS_VOICE_INDEX": 2,
        "SPEAKER_DEVICE_INDEX": 5,
    }
