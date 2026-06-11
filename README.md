# SpeechSkin

SpeechSkin is a lightweight, low-latency Windows utility that lets you speak in voice chats using high-quality AI text-to-speech (TTS) and speech-to-text (STT).


<img width="568" height="521" alt="image" src="https://github.com/user-attachments/assets/b22ee685-9b94-4981-b99f-2227d804ed70" />


## Core Concept

1. **Type to Speak**: Press `Ctrl+Alt+T` to open a floating overlay. Type a message, press Enter, and SpeechSkin speaks it through your virtual audio cable.
2. **Skin Mode**: Press the **SKIN** button to start a continuous loop: **Microphone Input ➔ ElevenLabs Speech-to-Text ➔ ElevenLabs Text-to-Speech ➔ Virtual Audio Cable**. You talk, and it speaks in your chosen AI voice!

---

## Quick Start

1. **Setup Environment**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Secrets**:
   Copy `secrets.env.example` to `secrets.env` and add your ElevenLabs API key:
   ```env
   ELEVENLABS_API_KEY=your_key_here
   ```

3. **Run**:
   Double-click `start.bat` or run:
   ```bash
   python speechskin.py
   ```

---

## Live Commands

Type these directly into the floating `Ctrl+Alt+T` overlay for quick controls:

- `/engine [name]` — Switch TTS engine
- `/voice <index>` — Change active voice
- `/audio input <idx>` — Set input virtual cable
- `/audio output <idx>` — Set speaker device
- `/audio speakers <on|off>` — Toggle speaker playback
- `/exit` — Quit the application

---

## Running Tests

Verify your installation with `pytest`:
```bash
python -m pytest
```
