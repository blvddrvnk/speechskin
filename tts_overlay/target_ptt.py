"""Hold/release a virtual key or mouse button to activate push-to-talk in a target app.

When SpeechSkin plays processed audio through the virtual cable, the target
application (a game, Discord, etc.) needs its PTT key held down so it actually
transmits the audio. This module handles that by pressing and releasing the
configured ``TARGET_PTT_KEY`` via the ``pynput`` library, supporting both keyboard
keys and mouse buttons.

If no key is configured (empty string) all operations are silent no-ops.
"""

from __future__ import annotations

from contextlib import contextmanager

from . import config, logutil

log = logutil.get(__name__)

_held = False
_kb_controller = None
_mouse_controller = None


def _get_controllers():
    """Lazily initialize pynput controllers."""
    global _kb_controller, _mouse_controller
    if _kb_controller is None:
        try:
            from pynput import keyboard, mouse
            _kb_controller = keyboard.Controller()
            _mouse_controller = mouse.Controller()
        except Exception as exc:
            log.error("Failed to initialize pynput controllers: %s", exc)
    return _kb_controller, _mouse_controller


def parse_mouse_button(name: str):
    """Map user-friendly mouse button names to pynput Button attributes."""
    try:
        from pynput import mouse
        name = name.lower().strip()
        if name == "left_mouse":
            return mouse.Button.left
        elif name == "right_mouse":
            return mouse.Button.right
        elif name == "middle_mouse":
            return mouse.Button.middle
        elif name in ("mouse4", "xbutton1"):
            return mouse.Button.x1
        elif name in ("mouse5", "xbutton2"):
            return mouse.Button.x2
    except Exception as exc:
        log.error("Error parsing mouse button '%s': %s", name, exc)
    return None


def parse_keyboard_key(name: str):
    """Map user-friendly key names to pynput Key attributes or KeyCode."""
    try:
        from pynput import keyboard
        name = name.lower().strip()
        
        special_mappings = {
            "ctrl": keyboard.Key.ctrl,
            "shift": keyboard.Key.shift,
            "alt": keyboard.Key.alt,
            "space": keyboard.Key.space,
            "enter": keyboard.Key.enter,
            "tab": keyboard.Key.tab,
            "backspace": keyboard.Key.backspace,
            "caps lock": keyboard.Key.caps_lock,
            "capslock": keyboard.Key.caps_lock,
            "num lock": keyboard.Key.num_lock,
            "numlock": keyboard.Key.num_lock,
            "scroll lock": keyboard.Key.scroll_lock,
            "scrolllock": keyboard.Key.scroll_lock,
            "print screen": keyboard.Key.print_screen,
            "insert": keyboard.Key.insert,
            "delete": keyboard.Key.delete,
            "home": keyboard.Key.home,
            "end": keyboard.Key.end,
            "page up": keyboard.Key.page_up,
            "pageup": keyboard.Key.page_up,
            "page down": keyboard.Key.page_down,
            "pagedown": keyboard.Key.page_down,
            "up": keyboard.Key.up,
            "down": keyboard.Key.down,
            "left": keyboard.Key.left,
            "right": keyboard.Key.right,
            "f1": keyboard.Key.f1,
            "f2": keyboard.Key.f2,
            "f3": keyboard.Key.f3,
            "f4": keyboard.Key.f4,
            "f5": keyboard.Key.f5,
            "f6": keyboard.Key.f6,
            "f7": keyboard.Key.f7,
            "f8": keyboard.Key.f8,
            "f9": keyboard.Key.f9,
            "f10": keyboard.Key.f10,
            "f11": keyboard.Key.f11,
            "f12": keyboard.Key.f12,
        }
        
        if name in special_mappings:
            return special_mappings[name]
            
        try:
            return keyboard.Key[name]
        except KeyError:
            pass
            
        if name.startswith("vk_"):
            try:
                return keyboard.KeyCode(vk=int(name[3:]))
            except ValueError:
                pass
                
        if len(name) == 1:
            return keyboard.KeyCode.from_char(name)
            
        return keyboard.KeyCode.from_char(name)
    except Exception as exc:
        log.error("Error parsing keyboard key '%s': %s", name, exc)
        return None


def hold() -> None:
    """Press and hold the target PTT key or mouse button. No-op if unconfigured or already held."""
    global _held
    key = config.TARGET_PTT_KEY
    if not key or _held:
        return
    try:
        kb_ctrl, mouse_ctrl = _get_controllers()
        if kb_ctrl is None or mouse_ctrl is None:
            return
            
        if key.endswith("_mouse") or key.startswith("mouse"):
            button = parse_mouse_button(key)
            if button is not None:
                mouse_ctrl.press(button)
                _held = True
                log.debug("target_ptt: holding mouse button '%s'", key)
        else:
            kb_key = parse_keyboard_key(key)
            if kb_key is not None:
                kb_ctrl.press(kb_key)
                _held = True
                log.debug("target_ptt: holding keyboard key '%s'", key)
    except Exception as exc:  # noqa: BLE001
        log.error("target_ptt: failed to press '%s': %s", key, exc)


def release() -> None:
    """Release the target PTT key or mouse button. No-op if unconfigured or not held."""
    global _held
    key = config.TARGET_PTT_KEY
    if not key or not _held:
        _held = False
        return
    try:
        kb_ctrl, mouse_ctrl = _get_controllers()
        if kb_ctrl is None or mouse_ctrl is None:
            return
            
        if key.endswith("_mouse") or key.startswith("mouse"):
            button = parse_mouse_button(key)
            if button is not None:
                mouse_ctrl.release(button)
                log.debug("target_ptt: released mouse button '%s'", key)
        else:
            kb_key = parse_keyboard_key(key)
            if kb_key is not None:
                kb_ctrl.release(kb_key)
                log.debug("target_ptt: released keyboard key '%s'", key)
    except Exception as exc:  # noqa: BLE001
        log.error("target_ptt: failed to release '%s': %s", key, exc)
    finally:
        _held = False


@contextmanager
def held():
    """Context manager: hold the target PTT key for the duration of the block.

    Usage::

        with target_ptt.held():
            play_audio_on_virtual_cable()
    """
    hold()
    try:
        yield
    finally:
        release()
