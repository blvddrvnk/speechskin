"""Tests for the slash-command system used by the overlay."""

from __future__ import annotations

import pytest

from tts_overlay import commands, config


# ------------------------------------------------------- is_command


@pytest.mark.parametrize("text,expected", [
    ("/voice", True),
    ("  /engine", True),
    ("hello", False),
    ("", False),
    ("a/b", False),
])
def test_is_command(text, expected):
    assert commands.is_command(text) is expected


# ----------------------------------------------------------- _split


def test_split_command_only():
    assert commands._split("/voice") == ("voice", "", False)


def test_split_command_with_arg():
    assert commands._split("/voice 3") == ("voice", "3", True)


def test_split_lowercases_command():
    assert commands._split("/VOICE 3") == ("voice", "3", True)


# --------------------------------------------------------- suggest


def test_suggest_command_names():
    suggestions = commands.suggest("/e")
    inserts = [s.insert for s in suggestions]
    assert "/engine " in inserts
    assert "/exit " in inserts


def test_suggest_non_command_returns_empty():
    assert commands.suggest("hello") == []


def test_suggest_engine_args(fake_engine, reset_engine, monkeypatch):
    # Engine command should offer the available engines.
    monkeypatch.setattr(commands.tts, "available_engines", lambda: ["elevenlabs"])
    monkeypatch.setattr(commands.tts, "current_engine_key", lambda: "elevenlabs")
    suggestions = commands.suggest("/engine ")
    labels = [s.label for s in suggestions]
    assert any("elevenlabs" in lab for lab in labels)


# ------------------------------------------------------------- run


def test_run_unknown_command():
    result = commands.run("/bogus")
    assert result.ok is False
    assert "Unknown command" in result.message


def test_run_exit():
    result = commands.run("/exit")
    assert result.quit is True


def test_run_voice_requires_index(fake_engine):
    result = commands.run("/voice")
    assert result.ok is False


def test_run_voice_non_numeric(fake_engine):
    result = commands.run("/voice abc")
    assert result.ok is False


def test_run_voice_selects(fake_engine):
    result = commands.run("/voice 1")
    assert result.ok is True
    assert fake_engine.selected_voice == 1


def test_run_engine_unknown(monkeypatch):
    monkeypatch.setattr(commands.tts, "available_engines", lambda: ["elevenlabs"])
    monkeypatch.setattr(commands.tts, "current_engine_key", lambda: "elevenlabs")
    result = commands.run("/engine nope")
    assert result.ok is False


def test_run_audio_speakers_toggle(temp_settings):
    result = commands.run("/audio speakers off")
    assert result.ok is True
    assert config.PLAY_ON_SPEAKERS is False


def test_run_audio_speakers_invalid(temp_settings):
    result = commands.run("/audio speakers maybe")
    assert result.ok is False


def test_run_audio_input_sets_device(fake_engine, temp_settings):
    # FakeEngine exposes devices [0,1,2].
    result = commands.run("/audio input 1")
    assert result.ok is True
    assert config.CABLE_DEVICE_INDEX == 1


def test_run_audio_input_unknown_device(fake_engine, temp_settings):
    result = commands.run("/audio input 99")
    assert result.ok is False


def test_run_audio_output_sets_device(fake_engine, temp_settings):
    result = commands.run("/audio output 2")
    assert result.ok is True
    assert config.SPEAKER_DEVICE_INDEX == 2


def test_run_command_never_raises(monkeypatch, fake_engine):
    def boom(index):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(fake_engine, "select_voice", boom)
    result = commands.run("/voice 0")
    assert result.ok is False
    assert "failed" in result.message.lower()
