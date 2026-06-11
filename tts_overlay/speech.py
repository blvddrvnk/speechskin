"""Shared speech playback orchestration.

Both the overlay and the settings window need to take a line of text and play it
through the configured output devices (the virtual cable and/or the speakers).
That routing logic lives here so it is defined once and tested once.

This module performs blocking work and must be called from a worker thread, not
the Tk thread.
"""

from __future__ import annotations

import threading

from . import config, logutil, tts
from . import shutdown as sd

log = logutil.get(__name__)


def speak_to_devices(text: str) -> None:
    """Render *text* and play it on the configured output device(s).

    Reads routing config fresh each call so device/speaker changes take effect
    immediately without a restart. Honors the shutdown event for prompt
    cancellation. Never raises.
    """
    if not text or sd.shutdown_event.is_set():
        return

    try:
        cable_idx = config.CABLE_DEVICE_INDEX
        speaker_idx = config.SPEAKER_DEVICE_INDEX  # None = system default

        targets = _resolve_targets(cable_idx, speaker_idx)

        if tts.get_engine().supports_dual_output:
            _speak_parallel(text, targets)
        else:
            _speak_sequential(text, targets)
    except Exception as exc:  # noqa: BLE001
        log.error("Error during speech: %s", exc)


def speak_to_devices_streaming(text: str) -> None:
    """Like :func:`speak_to_devices` but uses low-latency streaming playback.

    When the active engine supports streaming (``engine.supports_streaming``),
    audio begins playing as the first bytes arrive from the API rather than
    waiting for the full synthesis response.  Falls back transparently to
    :func:`speak_to_devices` for engines that don't implement streaming.

    For multi-device routing the cable device is streamed first (lowest
    latency path), then the speaker device plays via the normal path so
    the user can hear themselves without adding a second streaming buffer.
    """
    if not text or sd.shutdown_event.is_set():
        return

    try:
        engine = tts.get_engine()
        if not engine.supports_streaming:
            speak_to_devices(text)
            return

        cable_idx = config.CABLE_DEVICE_INDEX
        speaker_idx = config.SPEAKER_DEVICE_INDEX
        targets = _resolve_targets(cable_idx, speaker_idx)

        if not targets:
            return

        # Stream to the first (primary) target for minimal latency, then play
        # remaining targets normally in parallel.
        primary = targets[0]
        secondary = targets[1:]

        def _stream_primary() -> None:
            try:
                engine.speak_streaming(text, primary)
            except Exception as exc:  # noqa: BLE001
                log.error("Streaming speak failed: %s", exc)

        def _play_secondary(dev: int | None) -> None:
            tts.speak_on_device(text, dev)

        threads: list[threading.Thread] = []
        t = threading.Thread(target=_stream_primary, daemon=True)
        t.start()
        threads.append(t)

        for dev in secondary:
            t2 = threading.Thread(target=_play_secondary, args=(dev,),
                                  daemon=True)
            t2.start()
            threads.append(t2)

        for t in threads:
            while t.is_alive() and not sd.shutdown_event.is_set():
                t.join(timeout=0.1)

    except Exception as exc:  # noqa: BLE001
        log.error("Error during streaming speech: %s", exc)


def _resolve_targets(cable_idx: int | None,
                     speaker_idx: int | None) -> list[int | None]:
    """Decide which output device(s) to play on, in order."""
    targets: list[int | None] = []
    if cable_idx is not None:
        targets.append(cable_idx)
    if config.PLAY_ON_SPEAKERS:
        targets.append(speaker_idx)
    if not targets:
        targets.append(speaker_idx)
    return targets


def _speak_parallel(text: str, targets: list[int | None]) -> None:
    """Play on all *targets* concurrently and wait for all to finish."""
    threads: list[threading.Thread] = []
    for device_index in targets:
        t = threading.Thread(
            target=tts.speak_on_device,
            args=(text, device_index),
            daemon=True,
        )
        t.start()
        threads.append(t)
    for t in threads:
        while t.is_alive() and not sd.shutdown_event.is_set():
            t.join(timeout=0.1)


def _speak_sequential(text: str, targets: list[int | None]) -> None:
    """Play on each target one after another."""
    for device_index in targets:
        if sd.shutdown_event.is_set():
            break
        tts.speak_on_device(text, device_index)
