"""Win32 helpers (pure ctypes): find the game window and its screen rectangle."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int


def make_dpi_aware() -> None:
    """Report physical pixels (needed so capture offsets match the screen)."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:  # noqa: BLE001
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:  # noqa: BLE001
            pass


def find_window(title_part: str = "BeamNG") -> tuple[int, str] | None:
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title_part.lower() in buf.value.lower():
                    found.append((hwnd, buf.value))
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else None


def client_rect(hwnd: int) -> Rect | None:
    """Screen coordinates of the window's drawable area (no borders/title)."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    r = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(r)):
        return None
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = r.right - r.left, r.bottom - r.top
    # Encoders need even sizes.
    return Rect(pt.x, pt.y, w - w % 2, h - h % 2)


def bring_to_front(hwnd: int) -> None:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        ctypes.windll.user32.SetForegroundWindow(hwnd)
