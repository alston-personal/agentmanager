from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import platform
import struct
from pathlib import Path
from typing import Any


MAX_OUTPUT_PIXELS = 640 * 480
BI_RGB = 0
SRCCOPY = 0x00CC0020
DIB_RGB_COLORS = 0


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("semantic preview currently supports Windows only")


def _session_info() -> dict[str, Any]:
    kernel32 = ctypes.windll.kernel32
    pid = os.getpid()
    session_id = ctypes.c_uint32()
    if not kernel32.ProcessIdToSessionId(pid, ctypes.byref(session_id)):
        raise ctypes.WinError()
    active = int(kernel32.WTSGetActiveConsoleSessionId())
    current = int(session_id.value)
    return {
        "pid": pid,
        "process_session_id": current,
        "active_console_session_id": active,
        "interactive": current == active,
        "username": os.environ.get("USERNAME"),
        "session_name": os.environ.get("SESSIONNAME"),
    }


def _foreground_window() -> dict[str, Any]:
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    hwnd = int(user32.GetForegroundWindow())
    if not hwnd:
        raise RuntimeError("no foreground window")

    length = int(user32.GetWindowTextLengthW(hwnd))
    title_buf = ctypes.create_unicode_buffer(max(1, length + 1))
    user32.GetWindowTextW(hwnd, title_buf, len(title_buf))

    pid = ctypes.c_uint32()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

    rect = ctypes.wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        raise ctypes.WinError()

    process_name = None
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if handle:
        try:
            size = ctypes.c_uint32(32768)
            path_buf = ctypes.create_unicode_buffer(size.value)
            if kernel32.QueryFullProcessImageNameW(handle, 0, path_buf, ctypes.byref(size)):
                process_name = Path(path_buf.value).name
        finally:
            kernel32.CloseHandle(handle)

    return {
        "hwnd": hwnd,
        "title": title_buf.value.strip()[:500],
        "pid": int(pid.value),
        "process_name": process_name,
        "bounds": {
            "left": int(rect.left),
            "top": int(rect.top),
            "right": int(rect.right),
            "bottom": int(rect.bottom),
            "width": max(0, int(rect.right - rect.left)),
            "height": max(0, int(rect.bottom - rect.top)),
        },
    }


def _bounded_region(window: dict[str, Any], request: dict[str, Any]) -> dict[str, int]:
    b = window["bounds"]
    width = int(b["width"])
    height = int(b["height"])
    if width <= 0 or height <= 0:
        raise RuntimeError("foreground window has empty bounds")

    raw = request.get("region")
    if raw is None:
        left, top, right, bottom = 0, 0, width, height
    else:
        if not isinstance(raw, dict):
            raise ValueError("region must be an object")
        left = max(0, int(raw.get("left", 0)))
        top = max(0, int(raw.get("top", 0)))
        right = min(width, int(raw.get("right", width)))
        bottom = min(height, int(raw.get("bottom", height)))
        if right <= left or bottom <= top:
            raise ValueError("region must describe a non-empty area inside the foreground window")

    return {
        "left": int(b["left"]) + left,
        "top": int(b["top"]) + top,
        "width": right - left,
        "height": bottom - top,
        "relative_left": left,
        "relative_top": top,
    }


def _scaled_size(width: int, height: int, max_pixels: int) -> tuple[int, int]:
    max_pixels = max(16_384, min(int(max_pixels), MAX_OUTPUT_PIXELS))
    pixels = width * height
    if pixels <= max_pixels:
        return width, height
    scale = (max_pixels / float(pixels)) ** 0.5
    return max(1, int(width * scale)), max(1, int(height * scale))


def _capture_bmp(region: dict[str, int], *, max_pixels: int) -> tuple[bytes, int, int]:
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    src_w, src_h = region["width"], region["height"]
    out_w, out_h = _scaled_size(src_w, src_h, max_pixels)

    screen_dc = user32.GetDC(0)
    if not screen_dc:
        raise ctypes.WinError()
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    if not mem_dc:
        user32.ReleaseDC(0, screen_dc)
        raise ctypes.WinError()
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, out_w, out_h)
    if not bitmap:
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)
        raise ctypes.WinError()

    old_obj = gdi32.SelectObject(mem_dc, bitmap)
    try:
        if src_w == out_w and src_h == out_h:
            ok = gdi32.BitBlt(
                mem_dc, 0, 0, out_w, out_h, screen_dc,
                region["left"], region["top"], SRCCOPY,
            )
        else:
            gdi32.SetStretchBltMode(mem_dc, 4)
            ok = gdi32.StretchBlt(
                mem_dc, 0, 0, out_w, out_h, screen_dc,
                region["left"], region["top"], src_w, src_h, SRCCOPY,
            )
        if not ok:
            raise ctypes.WinError()

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", ctypes.c_uint32 * 3)]

        row_bytes = ((out_w * 3 + 3) // 4) * 4
        image_bytes = row_bytes * out_h
        buf = ctypes.create_string_buffer(image_bytes)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = out_w
        bmi.bmiHeader.biHeight = -out_h
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 24
        bmi.bmiHeader.biCompression = BI_RGB
        bmi.bmiHeader.biSizeImage = image_bytes

        lines = gdi32.GetDIBits(mem_dc, bitmap, 0, out_h, buf, ctypes.byref(bmi), DIB_RGB_COLORS)
        if lines != out_h:
            raise ctypes.WinError()

        file_header_size = 14
        info_header_size = 40
        offset = file_header_size + info_header_size
        total = offset + image_bytes
        file_header = struct.pack("<2sIHHI", b"BM", total, 0, 0, offset)
        info_header = struct.pack(
            "<IiiHHIIiiII",
            info_header_size, out_w, -out_h, 1, 24, BI_RGB,
            image_bytes, 0, 0, 0, 0,
        )
        return file_header + info_header + buf.raw, out_w, out_h
    finally:
        gdi32.SelectObject(mem_dc, old_obj)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(0, screen_dc)


def semantic_preview(task: dict[str, Any]) -> dict[str, Any]:
    """Return a bounded, read-only preview of only the foreground window.

    This capability deliberately does not enumerate other windows, execute a
    shell, inspect the filesystem, read the clipboard, or expose a UIA tree.
    """
    _require_windows()
    session = _session_info()
    if not session["interactive"]:
        raise RuntimeError(f"Thin Client is not in active interactive session: {session}")

    window = _foreground_window()
    region = _bounded_region(window, task)
    raw, width, height = _capture_bmp(
        region,
        max_pixels=int(task.get("max_pixels") or MAX_OUTPUT_PIXELS),
    )
    digest = hashlib.sha256(raw).hexdigest()
    state_material = (
        f'{window.get("process_name")}|{window.get("title")}|'
        f'{window["bounds"]}|{digest}'
    ).encode("utf-8", errors="replace")

    return {
        "schema": "agentos.desktop-semantic-preview/v0.1",
        "mode": "foreground-window-only",
        "read_only": True,
        "foreground": {
            "title": window["title"],
            "process_name": window["process_name"],
            "pid": window["pid"],
            "bounds": window["bounds"],
        },
        "preview": {
            "mime_type": "image/bmp",
            "width": width,
            "height": height,
            "bytes": len(raw),
            "sha256": digest,
            "image_base64": base64.b64encode(raw).decode("ascii"),
            "source_region": {
                "relative_left": region["relative_left"],
                "relative_top": region["relative_top"],
                "width": region["width"],
                "height": region["height"],
            },
        },
        "semantic_regions": [
            {
                "id": "foreground-window",
                "kind": "window",
                "label": window["process_name"] or "foreground",
                "bounds": window["bounds"],
            }
        ],
        "state_hash": hashlib.sha256(state_material).hexdigest(),
        "session": session,
        "denied_surfaces": [
            "shell",
            "filesystem",
            "clipboard",
            "full-window-enumeration",
            "uia-tree",
            "background-windows",
        ],
    }
