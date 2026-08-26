from __future__ import annotations

import base64
import ctypes
import hashlib
import os
import platform
import subprocess
import tempfile
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
    os.startfile(url)  # type: ignore[attr-defined]
    return {'url': url, 'session': info, 'launched': True}


def screenshot(workspace: Path, *, quality: int = 55) -> dict[str, Any]:
    _require_windows()
    info = session_info()
    if not info['interactive']:
        raise RuntimeError(f"Thin Client is not in active interactive session: {info}")
    workspace = workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    target = workspace / 'agentos-desktop-current.jpg'
    quality = max(20, min(int(quality), 85))
    script = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds=[System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp=New-Object System.Drawing.Bitmap $bounds.Width,$bounds.Height
$g=[System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Left,$bounds.Top,0,0,$bmp.Size)
$enc=[System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object {$_.MimeType -eq 'image/jpeg'}
$ep=New-Object System.Drawing.Imaging.EncoderParameters 1
$ep.Param[0]=New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality,[long]$env:AGENTOS_JPEG_QUALITY)
$bmp.Save($env:AGENTOS_SCREENSHOT_PATH,$enc,$ep)
$g.Dispose(); $bmp.Dispose()
Write-Output ($bounds.Width.ToString()+','+$bounds.Height.ToString())
'''
    env = os.environ.copy()
    env['AGENTOS_SCREENSHOT_PATH'] = str(target)
    env['AGENTOS_JPEG_QUALITY'] = str(quality)
    cp = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], text=True, capture_output=True, timeout=20, env=env, check=False)
    if cp.returncode != 0 or not target.is_file():
        raise RuntimeError(f'screenshot failed rc={cp.returncode}: {cp.stderr[-2000:]}')
    raw = target.read_bytes()
    if len(raw) > 1_500_000:
        raise RuntimeError(f'screenshot exceeds evidence limit: {len(raw)} bytes')
    dims = (cp.stdout or '').strip().split(',')
    width = int(dims[-2]) if len(dims) >= 2 else None
    height = int(dims[-1]) if len(dims) >= 2 else None
    return {
        'path': str(target),
        'mime_type': 'image/jpeg',
        'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'width': width,
        'height': height,
        'image_base64': base64.b64encode(raw).decode('ascii'),
        'session': info,
    }


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
    # Use PowerShell SendKeys only inside the already-validated interactive user session.
    escaped = text.replace("'", "''")
    script = "Add-Type -AssemblyName System.Windows.Forms; [System.Windows.Forms.SendKeys]::SendWait('" + escaped.replace('{','{{}').replace('}','{}}') + "')"
    cp = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], text=True, capture_output=True, timeout=10, check=False)
    if cp.returncode != 0:
        raise RuntimeError(f'keyboard input failed rc={cp.returncode}: {cp.stderr[-2000:]}')
    return {'operation': op, 'characters': len(text), 'session': info}
