"""System-level microphone mute/unmute for Windows.

Used by Skin mode to mute the physical input device while TTS is playing back,
preventing the program from accidentally transcribing its own speech output.

Requires ``pycaw`` (and its ``comtypes`` dependency). If pycaw is unavailable
(e.g. on non-Windows platforms or missing install) all calls are silently
no-ops so the rest of the application continues to work.

Typical usage::

    token = mute(device_index)   # mute before TTS plays
    try:
        play_tts(...)
    finally:
        unmute(token)            # always restore, even on error
"""

from __future__ import annotations

from . import logutil

log = logutil.get(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_endpoint_volume(device_index: int | None):
    """Return the ``IAudioEndpointVolume`` COM pointer for the PortAudio input
    device at *device_index*, or ``None`` on any failure.

    PortAudio device names are truncated to ~31 characters.  We match them as
    a prefix against the full Windows ``FriendlyName`` of each capture
    endpoint.
    """
    try:
        import sounddevice as sd
        from pycaw.pycaw import AudioUtilities, EDataFlow  # type: ignore[import]
    except ImportError:
        return None

    try:
        # Resolve the PortAudio device name.
        if device_index is None:
            pa_name = ""
        else:
            pa_name = sd.query_devices(device_index).get("name", "").strip().lower()

        capture_devs = AudioUtilities.GetAllDevices(data_flow=EDataFlow.eCapture.value)

        # First pass: look for a device whose FriendlyName starts with the
        # (possibly truncated) PortAudio name.
        for dev in capture_devs:
            fn = (dev.FriendlyName or "").strip().lower()
            if pa_name and fn.startswith(pa_name):
                return dev.EndpointVolume

        # Second pass: substring match (less precise, avoids missing on
        # slightly different truncation boundaries).
        for dev in capture_devs:
            fn = (dev.FriendlyName or "").strip().lower()
            if pa_name and pa_name in fn:
                return dev.EndpointVolume

        # Fallback: mute the Windows default capture device.
        log.debug(
            "micmute: could not match PortAudio device %s to a Windows "
            "endpoint; falling back to system default microphone.",
            device_index,
        )
        default_mic = AudioUtilities.GetMicrophone()
        from pycaw.pycaw import IAudioEndpointVolume  # type: ignore[import]
        from comtypes import CLSCTX_ALL  # type: ignore[import]
        from ctypes import cast, POINTER
        iface = default_mic.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return cast(iface, POINTER(IAudioEndpointVolume))

    except Exception as exc:  # noqa: BLE001
        log.debug("micmute: failed to get endpoint volume: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class MuteToken:
    """Opaque token returned by :func:`mute`; pass to :func:`unmute`."""

    def __init__(self, endpoint_volume, was_already_muted: bool) -> None:
        self._vol = endpoint_volume
        self._was_already_muted = was_already_muted


def mute(device_index: int | None = None) -> MuteToken | None:
    """Mute the microphone endpoint corresponding to *device_index*.

    Returns a :class:`MuteToken` that should be passed to :func:`unmute` to
    restore the previous state.  Returns ``None`` if pycaw is unavailable or
    the device could not be found (the caller can still safely pass ``None``
    to :func:`unmute`).
    """
    vol = _get_endpoint_volume(device_index)
    if vol is None:
        return None
    try:
        was_already_muted = bool(vol.GetMute())
        if not was_already_muted:
            vol.SetMute(1, None)
            log.debug("micmute: muted device index=%s", device_index)
        else:
            log.debug(
                "micmute: device index=%s was already muted; skipping", device_index
            )
        return MuteToken(vol, was_already_muted)
    except Exception as exc:  # noqa: BLE001
        log.debug("micmute: SetMute failed: %s", exc)
        return None


def unmute(token: MuteToken | None) -> None:
    """Restore the microphone to its state before :func:`mute` was called.

    If the device was already muted before we touched it, we leave it muted.
    Safe to call with ``None`` (no-op).
    """
    if token is None:
        return
    if token._was_already_muted:
        log.debug("micmute: device was pre-muted; leaving muted")
        return
    try:
        token._vol.SetMute(0, None)
        log.debug("micmute: unmuted device")
    except Exception as exc:  # noqa: BLE001
        log.debug("micmute: SetMute(0) failed: %s", exc)
