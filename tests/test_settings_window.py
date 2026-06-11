"""Tests for the settings window.

GUI construction needs a Tk display. Where a display isn't available the
construction tests are skipped, but the pure logic (label parsing, device/value
mapping, dropdown value generation) is always exercised by driving the methods
on a lightweight stand-in instance.
"""

from __future__ import annotations

import types

import pytest

from tts_overlay import config, settings_window
from tts_overlay.settings_window import SettingsWindow, _device_label


# ----------------------------------------------- pure helper functions


def test_device_label_with_index():
    assert _device_label(3, "Speakers") == "[3] Speakers"


def test_device_label_default():
    assert _device_label(None, "System default") == "System default"


@pytest.mark.parametrize("label,expected", [
    ("[0] Mic", 0),
    ("[12] CABLE Input", 12),
    ("System default", None),
    ("", None),
    ("no brackets", None),
    ("[x] bad", None),
])
def test_parse_index(label, expected):
    assert SettingsWindow._parse_index(label) == expected


# -------------------------------------- logic via a stand-in instance


def _make_stub():
    """Create a SettingsWindow-like object without constructing Tk.

    We bypass __init__ and set just the attributes the logic methods read.
    """
    obj = SettingsWindow.__new__(SettingsWindow)
    obj._output_devices = [(0, "Speakers"), (1, "CABLE Input")]
    obj._input_devices = [(3, "Mic"), (4, "Headset")]
    obj._voices = [(0, "Alpha (a0)"), (1, "Beta (b1)")]
    obj._building = False
    obj._skin_active = False
    return obj


class _FakeButton:
    def __init__(self):
        self.options = {}

    def config(self, **kwargs):
        self.options.update(kwargs)


class _FakeRoot:
    def __init__(self):
        self.after_calls = []

    def after(self, delay, callback):
        self.after_calls.append((delay, callback))
        return f"after-{len(self.after_calls)}"


class _FakeText:
    def __init__(self):
        self.deleted = []

    def delete(self, start, end):
        self.deleted.append((start, end))


def test_device_value_index_default():
    obj = _make_stub()
    assert obj._device_value_index(SettingsWindow._DEFAULT_OPTION) is None
    assert obj._device_value_index("") is None


def test_device_value_index_real():
    obj = _make_stub()
    assert obj._device_value_index("[1] CABLE Input") == 1


def test_engine_values():
    obj = _make_stub()
    assert "elevenlabs" in obj._engine_values()


def test_voice_values():
    obj = _make_stub()
    assert obj._voice_values() == ["[0] Alpha (a0)", "[1] Beta (b1)"]


def test_input_values_includes_default():
    obj = _make_stub()
    vals = obj._input_values()
    assert vals[0] == SettingsWindow._DEFAULT_OPTION
    assert "[3] Mic" in vals
    assert "[4] Headset" in vals


def test_output_values_with_default():
    obj = _make_stub()
    vals = obj._output_values(include_default=True)
    assert vals[0] == SettingsWindow._DEFAULT_OPTION
    assert "[0] Speakers" in vals


def test_output_values_without_default():
    obj = _make_stub()
    vals = obj._output_values(include_default=False)
    assert SettingsWindow._DEFAULT_OPTION not in vals
    assert "[1] CABLE Input" in vals


def test_device_selection_default_when_none():
    obj = _make_stub()
    assert obj._device_selection(None, obj._input_devices, default=True) \
        == SettingsWindow._DEFAULT_OPTION


def test_device_selection_finds_index():
    obj = _make_stub()
    assert obj._device_selection(4, obj._input_devices, default=True) \
        == "[4] Headset"


def test_voice_label_for_current(monkeypatch):
    obj = _make_stub()
    monkeypatch.setattr(config, "TTS_VOICE_INDEX", 1)
    assert obj._voice_label_for_current() == "[1] Beta (b1)"


def test_voice_label_for_current_fallback_to_first(monkeypatch):
    obj = _make_stub()
    monkeypatch.setattr(config, "TTS_VOICE_INDEX", 99)
    assert obj._voice_label_for_current() == "[0] Alpha (a0)"


def test_voice_label_for_current_no_voices(monkeypatch):
    obj = _make_stub()
    obj._voices = []
    monkeypatch.setattr(config, "TTS_VOICE_INDEX", 0)
    assert obj._voice_label_for_current() is None


def test_transcription_available(monkeypatch):
    obj = _make_stub()
    monkeypatch.setattr(settings_window.tts, "supports_transcription",
                        lambda: True)
    assert obj._transcription_available() is True
    monkeypatch.setattr(settings_window.tts, "supports_transcription",
                        lambda: False)
    assert obj._transcription_available() is False


def test_transcription_available_swallows_errors(monkeypatch):
    obj = _make_stub()

    def boom():
        raise RuntimeError("no engine")

    monkeypatch.setattr(settings_window.tts, "supports_transcription", boom)
    assert obj._transcription_available() is False


def test_update_listen_availability_keeps_active_skin_stoppable(monkeypatch):
    obj = _make_stub()
    obj._skin_active = True
    obj._skin_btn = _FakeButton()

    def boom():
        raise RuntimeError("engine unavailable")

    monkeypatch.setattr(settings_window.tts, "supports_transcription", boom)

    obj._update_listen_availability()

    assert obj._skin_btn.options["state"] == "normal"


def test_pump_worker_events_runs_queued_callbacks():
    obj = _make_stub()
    obj._ui_callbacks = settings_window.Queue()
    calls = []
    obj._ui_callbacks.put(lambda: calls.append("done"))

    obj.pump_worker_events()

    assert calls == ["done"]


def test_profile_change(monkeypatch):
    obj = _make_stub()
    obj._skin_ptt_label = _FakeButton()
    obj._target_ptt_label = _FakeButton()
    obj._skin_active = False
    obj._status = lambda *args: None
    
    monkeypatch.setattr(config, "PROFILES", {
        "Default": {"SKIN_PTT_KEY": "", "TARGET_PTT_KEY": ""},
        "Valorant": {"SKIN_PTT_KEY": "caps lock", "TARGET_PTT_KEY": "v"}
    })
    
    obj.profile_var = types.SimpleNamespace(get=lambda: "Valorant")
    
    saved = []
    monkeypatch.setattr(settings_window.settings, "set", lambda k, v: saved.append((k, v)))
    
    obj._on_profile_change()
    
    assert ("ACTIVE_PROFILE", "Valorant") in saved
    assert ("SKIN_PTT_KEY", "caps lock") in saved
    assert ("TARGET_PTT_KEY", "v") in saved



# ---------------------------------------------- full GUI construction


def _tk_available() -> bool:
    try:
        import tkinter as tk
        root = tk.Tk()
        root.destroy()
        return True
    except Exception:  # noqa: BLE001
        return False


tk_required = pytest.mark.skipif(
    not _tk_available(), reason="Tk display not available"
)


@tk_required
def test_window_constructs(monkeypatch, fake_engine, temp_settings):
    # Avoid real device enumeration; feed known lists.
    monkeypatch.setattr(settings_window.recorder, "enumerate_input_devices",
                        lambda: [(3, "Mic")])
    try:
        win = SettingsWindow(
            output_devices=[(0, "Speakers"), (1, "CABLE Input")])
    except settings_window.tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    try:
        assert win.engine_var.get()
        assert "[0] Speakers" in win._output_values(include_default=True)
    finally:
        win.destroy()


@tk_required
def test_window_speak_uses_text(monkeypatch, fake_engine, temp_settings):
    monkeypatch.setattr(settings_window.recorder, "enumerate_input_devices",
                        lambda: [])
    calls = []
    monkeypatch.setattr(settings_window.speech, "speak_to_devices",
                        lambda text: calls.append(text))
    try:
        win = SettingsWindow(output_devices=[(0, "Speakers")])
    except settings_window.tk.TclError as exc:
        pytest.skip(f"Tk unavailable: {exc}")
    try:
        win.text.insert("1.0", "hello there")
        win._do_speak("hello there")
        assert calls == ["hello there"]
    finally:
        win.destroy()


def test_decoupled_playback_logic():
    obj = _make_stub()
    obj._play_btn = _FakeButton()
    obj.text = _FakeText()
    obj._speaking = False
    obj._ptt_playing = False
    
    # Test update_play_btn_state when idle
    obj._update_play_btn_state()
    assert obj._play_btn.options["state"] == "normal"
    
    # Test update_play_btn_state when speaking
    obj._speaking = True
    obj._update_play_btn_state()
    assert obj._play_btn.options["state"] == "disabled"
    
    # Test update_play_btn_state when PTT is playing
    obj._speaking = False
    obj._ptt_playing = True
    obj._update_play_btn_state()
    assert obj._play_btn.options["state"] == "disabled"


def test_apply_ptt_status_clears_text_on_idle():
    obj = _make_stub()
    obj._play_btn = _FakeButton()
    obj.text = _FakeText()
    obj._speaking = False
    obj._ptt_playing = False
    obj._status = lambda *args: None
    
    # Transition to PLAYING
    obj._apply_ptt_status(settings_window._skin_ptt_mod.STATUS_PLAYING, "Speaking...")
    assert obj._ptt_playing is True
    assert obj._play_btn.options["state"] == "disabled"
    
    # Transition to IDLE should clear the text
    obj._apply_ptt_status(settings_window._skin_ptt_mod.STATUS_IDLE, "Ready")
    assert obj._ptt_playing is False
    assert obj._play_btn.options["state"] == "normal"
    assert ("1.0", "end") in obj.text.deleted

