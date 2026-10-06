from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import platform
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def _require_windows() -> None:
    if platform.system() != 'Windows':
        raise RuntimeError('interactive desktop adapter currently supports Windows only')


def session_info() -> dict[str, Any]:
    _require_windows()
    kernel32 = ctypes.windll.kernel32
    pid = os.getpid()
    session_id = ctypes.c_uint32()
    if not kernel32.ProcessIdToSessionId(pid, ctypes.byref(session_id)):
        raise ctypes.WinError()
    active = int(kernel32.WTSGetActiveConsoleSessionId())
    current = int(session_id.value)
    return {
        'pid': pid,
        'process_session_id': current,
        'active_console_session_id': active,
        'interactive': current == active,
        'username': os.environ.get('USERNAME'),
        'session_name': os.environ.get('SESSIONNAME'),
    }


def open_url(url: str) -> dict[str, Any]:
    _require_windows()
    parsed = urlparse(url)
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        raise ValueError('desktop.open_url accepts only absolute http/https URLs')
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    rc = ctypes.windll.shell32.ShellExecuteW(None, 'open', url, None, None, 1)
    if int(rc) <= 32:
        raise ctypes.WinError(int(rc))
    return {'url': url, 'session': info, 'launched': True, 'shell_execute_result': int(rc)}


def inspect_windows() -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    windows: list[dict[str, Any]] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        title_buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buf, length + 1)
        title = title_buf.value.strip()
        if not title:
            return True
        pid = ctypes.c_uint32()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
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
        windows.append({
            'hwnd': int(hwnd),
            'title': title[:500],
            'pid': int(pid.value),
            'process_name': process_name,
        })
        return len(windows) < 100

    proc = EnumWindowsProc(callback)
    if not user32.EnumWindows(proc, 0):
        err = kernel32.GetLastError()
        if err:
            raise ctypes.WinError(err)
    return {'session': info, 'windows': windows, 'window_count': len(windows)}


def screenshot(workspace: Path, *, quality: int = 55) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / 'agentos-desktop-current.bmp'
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    x, y = int(user32.GetSystemMetrics(SM_XVIRTUALSCREEN)), int(user32.GetSystemMetrics(SM_YVIRTUALSCREEN))
    width, height = int(user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)), int(user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))
    if width <= 0 or height <= 0:
        raise RuntimeError(f'invalid virtual screen bounds: {x},{y} {width}x{height}')
    hdc = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
    old = gdi32.SelectObject(mem, bmp)
    try:
        if not gdi32.BitBlt(mem, 0, 0, width, height, hdc, x, y, 0x00CC0020):
            raise ctypes.WinError()
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_=[('biSize',ctypes.c_uint32),('biWidth',ctypes.c_int32),('biHeight',ctypes.c_int32),('biPlanes',ctypes.c_uint16),('biBitCount',ctypes.c_uint16),('biCompression',ctypes.c_uint32),('biSizeImage',ctypes.c_uint32),('biXPelsPerMeter',ctypes.c_int32),('biYPelsPerMeter',ctypes.c_int32),('biClrUsed',ctypes.c_uint32),('biClrImportant',ctypes.c_uint32)]
        row=((width*3+3)//4)*4
        size=row*height
        buf=ctypes.create_string_buffer(size)
        bih=BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER),width,height,1,24,0,size,0,0,0,0)
        if not gdi32.GetDIBits(mem,bmp,0,height,buf,ctypes.byref(bih),0):
            raise ctypes.WinError()
        import struct
        offset=14+40
        header=b'BM'+struct.pack('<IHHI',offset+size,0,0,offset)
        dib=struct.pack('<IiiHHIIiiII',40,width,height,1,24,0,size,0,0,0,0)
        raw=header+dib+buf.raw
        target.write_bytes(raw)
    finally:
        gdi32.SelectObject(mem,old); gdi32.DeleteObject(bmp); gdi32.DeleteDC(mem); user32.ReleaseDC(0,hdc)
    if len(raw) > 12_000_000:
        raise RuntimeError(f'screenshot exceeds evidence limit: {len(raw)} bytes')
    return {'path':str(target),'mime_type':'image/bmp','bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'width':width,'height':height,'image_base64':base64.b64encode(raw).decode('ascii'),'session':info}




def preview_capture(workspace: Path, *, max_width: int = 480, max_height: int = 270, quality: int = 30) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    max_width = max(160, min(640, int(max_width)))
    max_height = max(90, min(360, int(max_height)))
    quality = max(20, min(45, int(quality)))
    try:
        from PIL import Image
    except Exception as exc:
        raise RuntimeError('desktop preview requires Pillow') from exc

    shot = screenshot(workspace, quality=quality)
    raw = base64.b64decode(str(shot.get('image_base64') or ''), validate=True)
    import io
    source = Image.open(io.BytesIO(raw)).convert('RGB')
    source.thumbnail((max_width, max_height))
    current_quality = quality
    preview = b''
    while True:
        buf = io.BytesIO()
        source.save(buf, format='JPEG', quality=current_quality, optimize=True)
        preview = buf.getvalue()
        if len(preview) <= 40_000:
            break
        if source.width <= 160 or source.height <= 90:
            raise RuntimeError(f'preview exceeds transport limit: {len(preview)} bytes')
        source.thumbnail((max(160, source.width * 4 // 5), max(90, source.height * 4 // 5)))
        current_quality = max(20, current_quality - 5)
    return {
        'mime_type': 'image/jpeg',
        'bytes': len(preview),
        'sha256': hashlib.sha256(preview).hexdigest(),
        'width': int(source.width),
        'height': int(source.height),
        'image_base64': base64.b64encode(preview).decode('ascii'),
        'session': info,
    }



def tile_windows(task: dict[str, Any]) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    entries = list(task.get('windows') or [])
    if not entries or len(entries) > 4:
        raise ValueError('windows must contain 1..4 layout entries')
    reserve_top = max(0, min(160, int(task.get('reserve_top_px') or 80)))
    margin = max(0, min(40, int(task.get('margin_px') or 8)))
    user32 = ctypes.windll.user32
    screen_w = int(user32.GetSystemMetrics(0))
    screen_h = int(user32.GetSystemMetrics(1))
    usable_y = reserve_top + margin
    usable_h = max(200, screen_h - usable_y - margin)

    visible: list[tuple[int, str]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    def callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            visible.append((int(hwnd), title))
        return True
    proc = EnumWindowsProc(callback)
    user32.EnumWindows(proc, 0)

    zones = {
        'left': (margin, usable_y, max(300, screen_w * 2 // 5 - margin * 2), usable_h),
        'right': (screen_w * 2 // 5 + margin, usable_y, max(400, screen_w * 3 // 5 - margin * 2), usable_h),
        'full': (margin, usable_y, max(400, screen_w - margin * 2), usable_h),
    }
    moved: list[dict[str, Any]] = []
    for entry in entries:
        needle = str(entry.get('title_contains') or '').strip()
        zone = str(entry.get('zone') or '').strip().lower()
        if not needle or zone not in zones:
            raise ValueError('each window requires title_contains and zone=left|right|full')
        match = next(((hwnd, title) for hwnd, title in visible if needle.lower() in title.lower()), None)
        if match is None:
            moved.append({'title_contains': needle, 'zone': zone, 'matched': False})
            continue
        hwnd, title = match
        x, y, w, h = zones[zone]
        user32.ShowWindow(hwnd, 9)
        ok = bool(user32.MoveWindow(hwnd, int(x), int(y), int(w), int(h), True))
        moved.append({'title_contains': needle, 'zone': zone, 'matched': True, 'title': title[:200], 'hwnd': hwnd, 'moved': ok, 'rect': [int(x), int(y), int(w), int(h)]})
    return {'session': info, 'screen': [screen_w, screen_h], 'reserve_top_px': reserve_top, 'windows': moved}

def mouse(task: dict[str, Any]) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    op = str(task.get('operation') or '')
    user32 = ctypes.windll.user32
    if op == 'move':
        x, y = int(task['x']), int(task['y'])
        if not user32.SetCursorPos(x, y):
            raise ctypes.WinError()
        return {'operation': op, 'x': x, 'y': y, 'session': info}
    if op == 'click':
        button = str(task.get('button') or 'left')
        flags = {'left': (0x0002, 0x0004), 'right': (0x0008, 0x0010)}
        if button not in flags:
            raise ValueError('button must be left or right')
        if 'x' in task and 'y' in task:
            if not user32.SetCursorPos(int(task['x']), int(task['y'])):
                raise ctypes.WinError()
        down, up = flags[button]
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        return {'operation': op, 'button': button, 'x': task.get('x'), 'y': task.get('y'), 'session': info}
    raise ValueError('desktop.mouse operation must be move or click')


def keyboard(task: dict[str, Any]) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    op = str(task.get('operation') or '')
    if op != 'type':
        raise ValueError('desktop.keyboard v0.1 only supports operation=type')
    text = str(task.get('text') or '')
    if not text or len(text) > 1000:
        raise ValueError('text must contain 1..1000 characters')
    escaped = text.replace("'", "''")
    script = "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('" + escaped.replace('{','{{}').replace('}','{}}') + "')"
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    cp = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], text=True, capture_output=True, timeout=10, check=False, creationflags=flags)
    if cp.returncode != 0:
        raise RuntimeError(f'keyboard input failed rc={cp.returncode}: {cp.stderr[-2000:]}')
    return {'operation': op, 'characters': len(text), 'session': info}
