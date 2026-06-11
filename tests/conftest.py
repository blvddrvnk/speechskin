"""Shared pytest fixtures for the SpeechSkin test suite.

Key isolation concerns handled here:

* ``settings.set`` writes to ``settings.json`` on disk. Tests redirect that path
  to a temp file so the user's real settings are never touched.
* Several modules mutate the live ``config`` module. A fixture snapshots and
  restores the relevant attributes around every test.
* No real audio devices or network calls are made; tests stub the engine and
  audio/recorder layers.
"""

from __future__ import annotations



import pytest

from tts_overlay import config, settings


# The config attributes tests may mutate; snapshot/restore them every test.
_CONFIG_KEYS = (
    "TTS_ENGINE",
    "TTS_VOICE_INDEX",
    "ELEVENLABS_VOICE_ID",
    "CABLE_DEVICE_INDEX",
    "SPEAKER_DEVICE_INDEX",
    "PLAY_ON_SPEAKERS",
    "MIC_DEVICE_INDEX",
    "CABLE_DEVICE_KEYWORD",
)


@pytest.fixture(autouse=True)
def restore_config():
    """Snapshot and restore mutated ``config`` attributes around each test."""
    snapshot = {k: getattr(config, k) for k in _CONFIG_KEYS}
    yield
    for k, v in snapshot.items():
        setattr(config, k, v)


@pytest.fixture
def temp_settings(tmp_path, monkeypatch):
    """Redirect the settings file to a temp path and reset the overrides dict.

    Returns the temp ``settings.json`` Path for assertions.
    """
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", path)
    monkeypatch.setattr(settings, "_overrides", {})
    return path


@pytest.fixture
def reset_engine(monkeypatch):
    """Ensure the tts facade starts with no cached engine."""
    from tts_overlay import tts
    monkeypatch.setattr(tts, "_engine", None)
    return tts


class FakeEngine:
    """A controllable in-memory TTSEngine stand-in for tests."""

    name = "Fake"

    def __init__(self):
        self.spoken: list[tuple[str, object]] = []
        self.streamed: list[tuple[str, object]] = []
        self.voices = [(0, "Alpha (a0)"), (1, "Beta (b1)")]
        self.devices = [(0, "Speakers"), (1, "CABLE Input"), (2, "Headphones")]
        self.selected_voice = 0
        self.transcribe_result = "hello world"
        self.transcribe_error: Exception | None = None
        self._supports_dual = True
        self._supports_stt = True
        self._supports_streaming = False


    def startup_check(self):
        return None

    def enumerate_voices(self):
        return list(self.voices)

    def current_voice_description(self):
        return dict(self.voices).get(self.selected_voice, "?")

    def select_voice(self, index):
        if not (0 <= index < len(self.voices)):
            raise ValueError(f"voice #{index} out of range")
        self.selected_voice = index
        return dict(self.voices)[index]

    def enumerate_audio_devices(self):
        return list(self.devices)

    def find_cable_device(self, keyword):
        for i, name in self.devices:
            if keyword.lower() in name.lower():
                return i
        return None

    @property
    def supports_dual_output(self):
        return self._supports_dual

    def speak(self, text, device_index):
        self.spoken.append((text, device_index))

    def speak_streaming(self, text, device_index):
        self.streamed.append((text, device_index))

    @property
    def supports_streaming(self):
        return self._supports_streaming

    @property
    def supports_transcription(self):
        return self._supports_stt

    def transcribe(self, wav_bytes):
        if self.transcribe_error is not None:
            raise self.transcribe_error
        return self.transcribe_result





@pytest.fixture
def fake_engine(monkeypatch):
    """Install a FakeEngine as the active engine in the tts facade."""
    from tts_overlay import tts
    engine = FakeEngine()
    monkeypatch.setattr(tts, "_engine", engine)
    return engine
