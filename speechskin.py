"""SpeechSkin - entry point.

A floating text input that appears on a global hotkey (default CTRL+ALT+T).
Type text, press Enter, and it speaks through ElevenLabs, routing audio to a
virtual audio cable for voice chat (and optionally your speakers too).

On startup a full settings window opens with dropdown menus (engine, voice,
microphone, virtual cable, speakers), a transcript pane, and a **Skin** button
(continuous listen → transcribe → speak loop). The CTRL+ALT+T overlay keeps
working independently.

The implementation lives in the ``tts_overlay`` package:

    tts_overlay/
        config.py          - user-tweakable settings
        settings.py        - JSON persistence layer for runtime overrides
        secrets.py         - API key loader (secrets.env / environment)
        app.py             - startup banner + resilient main loop
        settings_window.py - the main window (dropdowns, Skin, Speak)
        overlay.py         - the Tk overlay window (crash-hardened callbacks)
        tkutil.py          - shared Tk helpers (safe decorator, device label)
        tts.py             - engine facade (device enumeration + speak/transcribe)
        speech.py          - shared render+play-to-devices routing
        commands.py        - slash-command system (/engine, /voice, /audio, /exit)
        audioplayer.py     - per-device audio playback (sounddevice/soundfile)
        recorder.py        - microphone capture -> WAV bytes (for Skin / Listen)
        hotkey.py          - global hotkey + listener watchdog
        micmute.py         - system-level mic mute during TTS playback
        skin_ptt.py        - push-to-talk driven voice skinning (pynput)
        target_ptt.py      - target app PTT key hold during playback
        win32utils.py      - defensive Win32 focus helpers
        shutdown.py        - cross-thread events + signal handling
        logutil.py         - logging setup
        engines/
            base.py        - TTSEngine abstract base class
            elevenlabs.py  - ElevenLabs cloud backend (TTS + speech-to-text)

Requirements:
    pip install -r requirements.txt
"""

from tts_overlay import run

if __name__ == "__main__":
    run()
