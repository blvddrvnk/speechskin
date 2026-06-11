"""Slash-command system for the overlay.

When the text the user types starts with ``/`` it is treated as a command
rather than something to speak. Commands let the user change the active engine,
pick a voice, list things, and quit -- without editing ``config.py`` or
restarting.

Design
------
Each command is a small subclass of :class:`Command` exposing three things:

* ``name`` / ``summary`` -- shown in the ``/help`` and autocomplete dropdown.
* :meth:`complete` -- given the partially-typed argument, return the candidate
  completions (so the overlay can offer a navigable dropdown).
* :meth:`run` -- execute with the final argument and return a
  :class:`CommandResult` (a status line, and optional side-effects flags).

Adding a command is one class plus one entry in :data:`_COMMANDS`. The overlay
never hard-codes any command behaviour; it only calls :func:`suggest`,
:func:`run`, and renders the results.

A :class:`Suggestion` is ``(insert, label)``:
* ``insert`` -- the full entry text to put in the box if chosen (e.g.
  ``"/voice 3"``), enabling Tab/Enter autocomplete.
* ``label``  -- the human-readable line shown in the dropdown.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import config, logutil, settings, tts
from . import shutdown as sd

log = logutil.get(__name__)

PREFIX = "/"


@dataclass
class Suggestion:
    insert: str  # full text to place in the entry box when chosen
    label: str   # text displayed in the dropdown


@dataclass
class CommandResult:
    message: str = ""
    ok: bool = True
    quit: bool = False
    # If set, the overlay should replace the entry text with this (e.g. to
    # turn "/voice" into "/voice " so the user can keep typing the argument).
    rewrite: str | None = None


# --------------------------------------------------------------------------
# Command base + concrete commands
# --------------------------------------------------------------------------


class Command:
    name: str = ""
    summary: str = ""

    def complete(self, arg_prefix: str) -> list[Suggestion]:
        """Return argument completions for the given (possibly empty) prefix."""
        return []

    def run(self, arg: str) -> CommandResult:
        raise NotImplementedError

    # helper for subclasses
    def _sugg(self, arg: str, label: str) -> Suggestion:
        text = f"{PREFIX}{self.name}" + (f" {arg}" if arg != "" else "")
        return Suggestion(insert=text, label=label)


class ExitCommand(Command):
    name = "exit"
    summary = "Quit the application"

    def run(self, arg: str) -> CommandResult:
        return CommandResult(message="Exiting...", quit=True)


class EngineCommand(Command):
    name = "engine"
    summary = "Switch engine (blank = cycle to next)"

    def complete(self, arg_prefix: str) -> list[Suggestion]:
        cur = tts.current_engine_key()
        out: list[Suggestion] = []
        for e in tts.available_engines():
            if e.startswith(arg_prefix.lower()):
                mark = "  (current)" if e == cur else ""
                out.append(self._sugg(e, f"{e}{mark}"))
        return out

    def run(self, arg: str) -> CommandResult:
        engines = tts.available_engines()
        if not engines:
            return CommandResult(message="No engines available", ok=False)
        arg = arg.strip().lower()
        if not arg:
            # Cycle to the next engine.
            cur = tts.current_engine_key()
            try:
                nxt = engines[(engines.index(cur) + 1) % len(engines)]
            except ValueError:
                nxt = engines[0]
            arg = nxt
        if arg not in engines:
            return CommandResult(
                message=f"Unknown engine '{arg}'. Try: {', '.join(engines)}",
                ok=False,
            )
        try:
            engine = tts.set_engine(arg)
        except Exception as exc:  # noqa: BLE001
            return CommandResult(message=f"Engine switch failed: {exc}", ok=False)
        return CommandResult(message=f"Engine -> {engine.name}")


class VoiceCommand(Command):
    name = "voice"
    summary = "Pick a voice by index"

    def complete(self, arg_prefix: str) -> list[Suggestion]:
        out: list[Suggestion] = []
        prefix = arg_prefix.strip().lower()
        for i, desc in _safe_voices():
            haystack = f"{i} {desc}".lower()
            if prefix == "" or prefix in haystack:
                out.append(self._sugg(str(i), f"[{i}] {desc}"))
        return out

    def run(self, arg: str) -> CommandResult:
        arg = arg.strip()
        if not arg:
            return CommandResult(message="Usage: /voice <index>", ok=False)
        try:
            index = int(arg)
        except ValueError:
            return CommandResult(message=f"'{arg}' is not a number", ok=False)
        try:
            chosen = tts.get_engine().select_voice(index)
        except Exception as exc:  # noqa: BLE001
            return CommandResult(message=f"Voice select failed: {exc}", ok=False)
        return CommandResult(message=f"Voice -> {chosen}")


class AudioCommand(Command):
    """Configure audio routing.

    Sub-commands:
      /audio input  <index>     - set the virtual cable (TTS goes here)
      /audio output <index>     - set the speaker output device
      /audio speakers <on|off>  - toggle whether TTS also plays on speakers
    """

    name = "audio"
    summary = "Configure audio routing (input/output/speakers)"

    _SUBCOMMANDS = ("input", "output", "speakers")

    def complete(self, arg_prefix: str) -> list[Suggestion]:
        parts = arg_prefix.split(None, 1)
        sub = parts[0].lower() if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        # Still typing the sub-command name.
        if len(parts) <= 1 and not arg_prefix.endswith(" "):
            out: list[Suggestion] = []
            summaries = {
                "input":    "set virtual cable device (TTS input)",
                "output":   "set speaker device (what you hear)",
                "speakers": "toggle play-through-speakers on/off",
            }
            for sc in self._SUBCOMMANDS:
                if sc.startswith(sub):
                    out.append(self._sugg(f"{sc} ", f"{sc}  —  {summaries[sc]}"))
            return out

        # Sub-command known — complete its argument.
        if sub == "input":
            return _device_suggestions(self, rest, sub)
        if sub == "output":
            return _device_suggestions(self, rest, sub)
        if sub == "speakers":
            out = []
            cur = "on" if config.PLAY_ON_SPEAKERS else "off"
            for val in ("on", "off"):
                mark = "  (current)" if val == cur else ""
                out.append(self._sugg(f"speakers {val}", f"{val}{mark}"))
            return out
        return []

    def run(self, arg: str) -> CommandResult:
        parts = arg.strip().split(None, 1)
        if not parts:
            return CommandResult(
                message="Usage: /audio input <idx> | output <idx> | speakers <on|off>",
                ok=False,
            )
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "input":
            return self._set_device("input", rest)
        if sub == "output":
            return self._set_device("output", rest)
        if sub == "speakers":
            return self._set_speakers(rest)
        return CommandResult(
            message=f"Unknown sub-command '{sub}'. Try: input, output, speakers",
            ok=False,
        )

    # -- helpers --

    def _set_device(self, role: str, arg: str) -> CommandResult:
        if not arg:
            return CommandResult(
                message=f"Usage: /audio {role} <device_index>", ok=False
            )
        try:
            index = int(arg)
        except ValueError:
            return CommandResult(message=f"'{arg}' is not a number", ok=False)
        try:
            devices = dict(_safe_audio_devices())
            if index not in devices:
                avail = ", ".join(str(k) for k in devices)
                return CommandResult(
                    message=f"Unknown device {index}. Available: {avail}", ok=False
                )
            name = devices[index]
            cfg_key = "CABLE_DEVICE_INDEX" if role == "input" else "SPEAKER_DEVICE_INDEX"
            settings.set(cfg_key, index)
            label = "Input (cable)" if role == "input" else "Output (speakers)"
            return CommandResult(message=f"{label} -> [{index}] {name}")
        except Exception as exc:  # noqa: BLE001
            return CommandResult(message=f"Audio {role} switch failed: {exc}", ok=False)

    def _set_speakers(self, arg: str) -> CommandResult:
        if not arg:
            state = "on" if config.PLAY_ON_SPEAKERS else "off"
            return CommandResult(
                message=f"Play on speakers is currently {state}. "
                        "Use: /audio speakers on|off",
                ok=False,
            )
        val = arg.lower()
        if val not in ("on", "off", "true", "false", "1", "0"):
            return CommandResult(
                message=f"'{arg}' is not valid. Use: on or off", ok=False
            )
        enabled = val in ("on", "true", "1")
        settings.set("PLAY_ON_SPEAKERS", enabled)
        return CommandResult(message=f"Play on speakers -> {'on' if enabled else 'off'}")


def _device_suggestions(cmd: Command, prefix: str, sub: str) -> list[Suggestion]:
    """Build device index completions for /audio input or /audio output."""
    out: list[Suggestion] = []
    p = prefix.strip().lower()
    for i, desc in _safe_audio_devices():
        haystack = f"{i} {desc}".lower()
        if p == "" or p in haystack:
            out.append(Suggestion(
                insert=f"{PREFIX}{cmd.name} {sub} {i}",
                label=f"[{i}] {desc}",
            ))
    return out


def _safe_voices() -> list[tuple[int, str]]:
    try:
        return tts.get_engine().enumerate_voices()
    except Exception as exc:  # noqa: BLE001
        log.error("Could not enumerate voices: %s", exc)
        return []


def _safe_audio_devices() -> list[tuple[int, str]]:
    try:
        return tts.get_engine().enumerate_audio_devices()
    except Exception as exc:  # noqa: BLE001
        log.error("Could not enumerate audio devices: %s", exc)
        return []


# Registration order controls dropdown ordering.
_COMMAND_LIST: list[Command] = [
    EngineCommand(),
    VoiceCommand(),
    AudioCommand(),
    ExitCommand(),
]
_COMMANDS: dict[str, Command] = {c.name: c for c in _COMMAND_LIST}


# --------------------------------------------------------------------------
# Public API used by the overlay
# --------------------------------------------------------------------------


def is_command(text: str) -> bool:
    return text.lstrip().startswith(PREFIX)


def _split(text: str) -> tuple[str, str, bool]:
    """Split entry text into ``(command, argument, has_space)``.

    ``has_space`` tells whether the user has typed past the command name (a
    space), which decides whether we complete command names or arguments.
    """
    body = text.lstrip()[len(PREFIX):]  # drop leading "/"
    if " " in body:
        cmd, _, arg = body.partition(" ")
        return cmd.lower(), arg, True
    return body.lower(), "", False


def suggest(text: str) -> list[Suggestion]:
    """Return dropdown suggestions for the current entry *text*.

    * While typing the command name -> matching command names.
    * Once a command + space is typed -> that command's argument completions.
    """
    if not is_command(text):
        return []
    cmd_name, arg, has_space = _split(text)

    if not has_space:
        out: list[Suggestion] = []
        for c in _COMMAND_LIST:
            if c.name.startswith(cmd_name):
                out.append(Suggestion(insert=f"{PREFIX}{c.name} ",
                                      label=f"/{c.name}  -  {c.summary}"))
        return out

    cmd = _COMMANDS.get(cmd_name)
    if cmd is None:
        return []
    return cmd.complete(arg)


def run(text: str) -> CommandResult:
    """Execute the command described by *text*."""
    cmd_name, arg, _ = _split(text)
    cmd = _COMMANDS.get(cmd_name)
    if cmd is None:
        known = ", ".join(f"/{c.name}" for c in _COMMAND_LIST)
        return CommandResult(
            message=f"Unknown command '/{cmd_name}'. Try: {known}", ok=False
        )
    try:
        return cmd.run(arg)
    except Exception as exc:  # noqa: BLE001
        log.error("Command /%s failed: %s", cmd_name, exc)
        return CommandResult(message=f"/{cmd_name} failed: {exc}", ok=False)
