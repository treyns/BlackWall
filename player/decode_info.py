"""Report whether Qt Multimedia really uses hardware video decoding.

Qt's FFmpeg backend logs its hardware-acceleration decision; we capture those
messages (through the application's Qt message handler) and expose the real
state instead of guessing.
"""
from __future__ import annotations

from core.logger import add_qt_message_hook

_STATE: dict[str, object] = {"hardware": None, "decoder": "", "checked": False}


def _hook(message: str, category: str) -> None:
    lower = message.lower()
    if "hw accel" not in lower and "d3d11" not in lower and "hardware" not in lower:
        return
    if "selected format" in lower and "d3d11" in lower:
        _STATE["hardware"] = True
        _STATE["decoder"] = "D3D11VA (GPU)"
        _STATE["checked"] = True
    elif "hw device is ok" in lower:
        _STATE["hardware"] = True
        if not _STATE["decoder"]:
            _STATE["decoder"] = "D3D11VA (GPU)"
        _STATE["checked"] = True
    elif ("could not" in lower or "cannot" in lower or "failed" in lower
          or "no hw" in lower or "not supported" in lower) and "hw" in lower:
        _STATE["hardware"] = False
        _STATE["decoder"] = "Software (CPU)"
        _STATE["checked"] = True


def install() -> None:
    add_qt_message_hook(_hook)


def hardware_active() -> bool | None:
    """True = GPU decoding in use, False = software, None = not measured yet."""
    value = _STATE.get("hardware")
    return value if isinstance(value, bool) else None


def decoder_label() -> str:
    return str(_STATE.get("decoder") or "")


def reset() -> None:
    _STATE["hardware"] = None
    _STATE["decoder"] = ""
    _STATE["checked"] = False
