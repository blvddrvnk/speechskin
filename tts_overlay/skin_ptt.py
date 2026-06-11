"""Push-to-Talk driven voice skinning using pynput.

Registers ``SKIN_PTT_KEY`` as a global hotkey/button:

* **Press**: start recording from the microphone.
* **Release**: stop recording, send audio through the STS (or STT→TTS)
  pipeline, and play the result through the virtual cable while holding
  the target PTT key/button.

Uses the ``pynput`` library for global low-level hooks on both mouse and keyboard
events, enabling the use of any keyboard key or mouse button.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from . import config, logutil, micmute, speech, tts
from . import shutdown as sd
from . import target_ptt
from .recorder import Recorder

log = logutil.get(__name__)

# Status constants for UI callbacks.
STATUS_IDLE = "idle"
STATUS_RECORDING = "recording"
STATUS_PROCESSING = "processing"
STATUS_PLAYING = "playing"


def key_matches(event_key, config_key: str) -> bool:
    """Helper to check if a pynput keyboard key event matches the configured hotkey."""
    if not config_key:
        return False
    config_key = config_key.lower().strip()
    
    try:
        from pynput import keyboard
        event_str = ""
        if isinstance(event_key, keyboard.Key):
            event_str = event_key.name.lower()
        elif isinstance(event_key, keyboard.KeyCode):
            if event_key.char:
                event_str = event_key.char.lower()
            else:
                event_str = f"vk_{event_key.vk}".lower()
        else:
            return False
            
        if event_str == config_key:
            return True
            
        # Match general modifiers to specific left/right versions
        if config_key == "ctrl" and event_str in ("ctrl_l", "ctrl_r"):
            return True
        if config_key == "shift" and event_str in ("shift_l", "shift_r"):
            return True
        if config_key == "alt" and event_str in ("alt_l", "alt_r"):
            return True
    except Exception as exc:
        log.error("Error matching key event: %s", exc)
        
    return False


def mouse_matches(button, config_key: str) -> bool:
    """Helper to check if a pynput mouse button matches the configured hotkey."""
    if not config_key:
        return False
    config_key = config_key.lower().strip()
    
    try:
        from pynput import mouse
        btn_str = ""
        if button == mouse.Button.left:
            btn_str = "left_mouse"
        elif button == mouse.Button.right:
            btn_str = "right_mouse"
        elif button == mouse.Button.middle:
            btn_str = "middle_mouse"
        elif button == mouse.Button.x1:
            btn_str = "mouse4"
        elif button == mouse.Button.x2:
            btn_str = "mouse5"
        else:
            btn_str = f"mouse_{button.name}".lower()
            
        return btn_str == config_key
    except Exception as exc:
        log.error("Error matching mouse button event: %s", exc)
        
    return False


class SkinPTT:
    """PTT-driven voice skin controller using pynput.

    Call :meth:`install` to start listening for the PTT key/button, and
    :meth:`teardown` to stop. The controller is reusable.
    """

    def __init__(self, on_status: Callable[[str, str], None] | None = None,
                 on_transcribed: Callable[[str], None] | None = None):
        """*on_status* receives ``(status_const, human_message)`` on changes."""
        self._on_status = on_status
        self._on_transcribed = on_transcribed
        self._recorder: Recorder | None = None
        self._installed = False
        self._kb_listener = None
        self._mouse_listener = None
        self._busy = False  # True while processing/playing

    # --------------------------------------------------------- public API

    def install(self) -> bool:
        """Register the PTT key/button global hooks. Returns True on success."""
        key = config.SKIN_PTT_KEY
        if not key:
            log.warning("skin_ptt: no SKIN_PTT_KEY configured")
            return False
        if self._installed:
            return True
        try:
            from pynput import keyboard, mouse
            
            # Start keyboard listener
            self._kb_listener = keyboard.Listener(
                on_press=self._on_kb_press,
                on_release=self._on_kb_release
            )
            self._kb_listener.start()
            
            # Start mouse listener
            self._mouse_listener = mouse.Listener(
                on_click=self._on_mouse_click
            )
            self._mouse_listener.start()
            
            self._installed = True
            log.info("skin_ptt: PTT global hooks for '%s' registered successfully", key)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("skin_ptt: failed to register PTT global hooks for '%s': %s", key, exc)
            return False

    def teardown(self) -> None:
        """Remove PTT global hooks and stop any in-progress recording."""
        self._installed = False
        
        # Stop keyboard listener
        kb_listener = getattr(self, "_kb_listener", None)
        if kb_listener is not None:
            try:
                kb_listener.stop()
            except Exception as exc:
                log.debug("skin_ptt: failed to stop keyboard listener: %s", exc)
            self._kb_listener = None
            
        # Stop mouse listener
        mouse_listener = getattr(self, "_mouse_listener", None)
        if mouse_listener is not None:
            try:
                mouse_listener.stop()
            except Exception as exc:
                log.debug("skin_ptt: failed to stop mouse listener: %s", exc)
            self._mouse_listener = None

        # Stop any in-progress recording.
        rec = self._recorder
        self._recorder = None
        if rec is not None and rec.is_recording:
            try:
                rec.stop()
            except Exception:  # noqa: BLE001
                pass
        target_ptt.release()  # safety: ensure key isn't stuck

    @property
    def is_installed(self) -> bool:
        return self._installed

    # -------------------------------------------------------- key events

    def _on_kb_press(self, key) -> None:
        if key_matches(key, config.SKIN_PTT_KEY):
            self._on_press()

    def _on_kb_release(self, key) -> None:
        if key_matches(key, config.SKIN_PTT_KEY):
            self._on_release()

    def _on_mouse_click(self, x, y, button, pressed) -> None:
        if mouse_matches(button, config.SKIN_PTT_KEY):
            if pressed:
                self._on_press()
            else:
                self._on_release()

    def _on_press(self) -> None:
        """PTT key/button pressed — start recording."""
        if self._busy or sd.shutdown_event.is_set():
            return
        if self._recorder is not None and self._recorder.is_recording:
            return  # already recording (key repeat / click hold)
        self._recorder = Recorder(device_index=config.MIC_DEVICE_INDEX)
        if self._recorder.start():
            self._set_status(STATUS_RECORDING, "Recording...")
            log.debug("skin_ptt: recording started")
        else:
            self._set_status(STATUS_IDLE, "Mic failed to start")
            self._recorder = None

    def _on_release(self) -> None:
        """PTT key/button released — stop recording and process."""
        rec = self._recorder
        self._recorder = None
        if rec is None or not rec.is_recording:
            return
        # Grab the heard_voice flag *before* stopping (it's set during capture).
        heard = rec.heard_voice
        pcm_bytes, sample_rate, _channels, _sw = rec.stop_raw()
        if not pcm_bytes or not heard:
            self._set_status(STATUS_IDLE, "No voice detected")
            return
        self._busy = True
        self._set_status(STATUS_PROCESSING, "Processing...")
        threading.Thread(
            target=self._process_audio,
            args=(pcm_bytes, sample_rate),
            daemon=True,
        ).start()

    # ----------------------------------------------------- audio pipeline

    def _process_audio(self, pcm_bytes: bytes, sample_rate: int) -> None:
        """Worker thread: send audio through STT→TTS (transcription method) and play result.

        Mic mute runs on a background thread so it doesn't block the API call
        (~20-80 ms saved from COM/pycaw initialisation).
        """
        # Fire mic mute asynchronously — don't wait for COM init.
        mute_token_box: list = [None]
        mute_done = threading.Event()

        def _do_mute():
            mute_token_box[0] = micmute.mute(config.MIC_DEVICE_INDEX)
            mute_done.set()

        threading.Thread(target=_do_mute, daemon=True).start()

        try:
            self._process_stt_tts_raw(pcm_bytes, sample_rate)
        except Exception as exc:  # noqa: BLE001
            log.error("skin_ptt: processing failed: %s", exc)
            self._set_status(STATUS_IDLE, f"Error: {exc}")
        finally:
            # Wait for mic mute to finish before unmuting.
            mute_done.wait(timeout=2.0)
            micmute.unmute(mute_token_box[0])
            target_ptt.release()  # safety
            self._busy = False
            self._set_status(STATUS_IDLE, "Ready")

    def _process_stt_tts_raw(self, pcm_bytes: bytes, sample_rate: int) -> None:
        """STT→TTS path from raw PCM."""
        from .recorder import encode_wav
        wav_bytes = encode_wav(pcm_bytes, sample_rate)
        text = tts.transcribe(wav_bytes)
        if not text:
            self._set_status(STATUS_IDLE, "Nothing transcribed")
            return
        log.info("skin_ptt: transcribed: %s", text)

        if self._on_transcribed is not None:
            try:
                self._on_transcribed(text)
            except Exception as exc:
                log.error("skin_ptt: on_transcribed callback failed: %s", exc)

        self._set_status(STATUS_PLAYING, "Speaking...")

        cable_idx = config.CABLE_DEVICE_INDEX

        # Play on cable with target PTT held.
        if cable_idx is not None:
            with target_ptt.held():
                speech.speak_to_devices_streaming(text)
        else:
            speech.speak_to_devices_streaming(text)

    # ------------------------------------------------------------ status

    def _set_status(self, status: str, message: str) -> None:
        log.debug("skin_ptt status: %s - %s", status, message)
        if self._on_status is not None:
            try:
                self._on_status(status, message)
            except Exception:  # noqa: BLE001
                pass
