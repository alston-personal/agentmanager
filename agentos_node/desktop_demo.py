from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATE_NAME = "agentos-demo-state.json"
VIDEO_NAME = "agentos-demo-raw.mkv"


def _require_windows() -> None:
    if platform.system() != "Windows":
        raise RuntimeError("desktop demo recorder currently supports Windows only")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_workspace() -> Path:
    _require_windows()
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA_missing")
    root = (Path(local) / "AgentOS" / "evidence").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _dir(workspace: Path) -> Path:
    root = workspace.expanduser().resolve() / "agentos-demo"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _state_path(workspace: Path) -> Path:
    return _dir(workspace) / STATE_NAME


def _read_state(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_state(path: Path, doc: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def start(workspace: Path, *, label: str = "AgentOS Demo", stage: str = "Starting", max_seconds: int = 900) -> dict[str, Any]:
    _require_windows()
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        sharex = Path(os.environ.get("ProgramFiles") or r"C:\\Program Files") / "ShareX" / "ffmpeg.exe"
        if sharex.is_file():
            ffmpeg = str(sharex)
    if not ffmpeg:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            packages = Path(local) / "Microsoft" / "WinGet" / "Packages"
            candidates = sorted(packages.rglob("ffmpeg.exe")) if packages.is_dir() else []
            if candidates:
                ffmpeg = str(candidates[-1])
    if not ffmpeg:
        raise RuntimeError("ffmpeg_not_found")
    root = _dir(workspace)
    state_path = root / STATE_NAME
    video_path = root / VIDEO_NAME
    if state_path.exists():
        try:
            old = _read_state(state_path)
            if old.get("recording"):
                raise RuntimeError("demo_recording_already_active")
        except json.JSONDecodeError:
            pass
    if video_path.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        video_path.replace(root / f"agentos-demo-raw-{stamp}.mkv")
    max_seconds = max(30, min(int(max_seconds), 7200))
    now = time.time()
    state = {
        "schema": "agentos.desktop-demo/v1",
        "recording": True,
        "label": str(label)[:80],
        "stage": str(stage)[:120],
        "started_at": _utc_now(),
        "started_epoch": now,
        "video_path": str(video_path),
        "max_seconds": max_seconds,
        "stage_history": [{"stage": str(stage)[:120], "changed_at": _utc_now(), "elapsed_seconds": 0.0}],
    }
    _write_state(state_path, state)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    overlay = subprocess.Popen(
        [sys.executable, "-m", "agentos_node.desktop_demo", "overlay", str(state_path)],
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    recorder = subprocess.Popen(
        [sys.executable, "-m", "agentos_node.desktop_demo", "recorder", str(state_path), str(video_path), ffmpeg],
        creationflags=flags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    state["overlay_pid"] = overlay.pid
    state["recorder_pid"] = recorder.pid
    _write_state(state_path, state)
    return {
        "demo_recording": True,
        "state_path": str(state_path),
        "video_path": str(video_path),
        "overlay_pid": overlay.pid,
        "recorder_pid": recorder.pid,
        "started_at": state["started_at"],
        "max_seconds": state["max_seconds"],
    }


def set_stage(workspace: Path, stage: str) -> dict[str, Any]:
    _require_windows()
    path = _state_path(workspace)
    if not path.is_file():
        raise RuntimeError("demo_state_missing")
    state = _read_state(path)
    if not state.get("recording"):
        raise RuntimeError("demo_recording_not_active")
    state["stage"] = str(stage)[:120]
    state["stage_changed_at"] = _utc_now()
    elapsed = round(time.time() - float(state["started_epoch"]), 2)
    history = list(state.get("stage_history") or [])
    history.append({"stage": state["stage"], "changed_at": state["stage_changed_at"], "elapsed_seconds": elapsed})
    state["stage_history"] = history[-100:]
    _write_state(path, state)
    return {"demo_recording": True, "stage": state["stage"], "elapsed_seconds": elapsed, "stage_history": state["stage_history"]}


def stop(workspace: Path, *, final_stage: str = "Verified") -> dict[str, Any]:
    _require_windows()
    path = _state_path(workspace)
    if not path.is_file():
        raise RuntimeError("demo_state_missing")
    state = _read_state(path)
    state["stage"] = str(final_stage)[:120]
    state["recording"] = False
    state["completed_at"] = _utc_now()
    state["elapsed_seconds"] = round(time.time() - float(state["started_epoch"]), 2)
    history = list(state.get("stage_history") or [])
    history.append({"stage": state["stage"], "changed_at": state["completed_at"], "elapsed_seconds": state["elapsed_seconds"]})
    state["stage_history"] = history[-100:]
    _write_state(path, state)
    video = Path(str(state["video_path"]))
    deadline = time.time() + 8
    last_size = -1
    stable = 0
    while time.time() < deadline:
        if video.exists():
            size = video.stat().st_size
            stable = stable + 1 if size == last_size and size > 0 else 0
            last_size = size
            if stable >= 2:
                break
        time.sleep(0.5)
    sha256 = None
    if video.is_file():
        digest = hashlib.sha256()
        with video.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        sha256 = digest.hexdigest()
    return {
        "demo_recording": False,
        "video_path": str(video),
        "video_exists": video.is_file(),
        "video_bytes": video.stat().st_size if video.is_file() else 0,
        "video_sha256": sha256,
        "started_at": state.get("started_at"),
        "completed_at": state["completed_at"],
        "elapsed_seconds": state["elapsed_seconds"],
        "final_stage": state["stage"],
        "stage_history": state.get("stage_history") or [],
    }


def _overlay(state_path: Path) -> None:
    import tkinter as tk

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    frame = tk.Frame(root, bg="#101418", padx=12, pady=7)
    frame.pack()
    title = tk.Label(frame, text="", fg="#ffffff", bg="#101418", font=("Segoe UI", 13, "bold"))
    title.pack(anchor="w")
    sub = tk.Label(frame, text="", fg="#b8c2cc", bg="#101418", font=("Segoe UI", 9))
    sub.pack(anchor="w")
    root.update_idletasks()
    width, height = 390, 62
    x = max(0, root.winfo_screenwidth() - width - 16)
    root.geometry(f"{width}x{height}+{x}+16")

    def tick() -> None:
        try:
            state = _read_state(state_path)
        except Exception:
            root.after(100, tick)
            return
        elapsed = max(0.0, time.time() - float(state.get("started_epoch") or time.time()))
        mins = int(elapsed // 60)
        secs = elapsed - mins * 60
        title.config(text=f"● REC   {mins:02d}:{secs:04.1f}   {state.get('label') or 'AgentOS Demo'}")
        sub.config(text=str(state.get("stage") or ""))
        if not state.get("recording"):
            root.after(500, root.destroy)
            return
        root.after(100, tick)

    tick()
    root.mainloop()


def _recorder(state_path: Path, video_path: Path, ffmpeg: str) -> None:
    cmd = [
        ffmpeg, "-y", "-loglevel", "warning",
        "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1",
        "-i", "desktop",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-pix_fmt", "yuv420p", str(video_path),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    try:
        while proc.poll() is None:
            try:
                current = _read_state(state_path)
                if current.get("recording") and (time.time() - float(current.get("started_epoch") or time.time())) >= float(current.get("max_seconds") or 900):
                    current["recording"] = False
                    current["stage"] = "Auto-stop / max duration"
                    current["completed_at"] = _utc_now()
                    current["elapsed_seconds"] = round(time.time() - float(current.get("started_epoch") or time.time()), 2)
                    history = list(current.get("stage_history") or [])
                    history.append({"stage": current["stage"], "changed_at": current["completed_at"], "elapsed_seconds": current["elapsed_seconds"]})
                    current["stage_history"] = history[-100:]
                    _write_state(state_path, current)
                if not current.get("recording"):
                    if proc.stdin:
                        proc.stdin.write(b"q\n")
                        proc.stdin.flush()
                    break
            except Exception:
                pass
            time.sleep(0.2)
        try:
            proc.wait(timeout=6)
        except subprocess.TimeoutExpired:
            proc.terminate()
    finally:
        if proc.poll() is None:
            proc.kill()


def main() -> int:
    if len(sys.argv) < 3:
        return 2
    mode = sys.argv[1]
    if mode == "overlay":
        _overlay(Path(sys.argv[2]))
        return 0
    if mode == "recorder" and len(sys.argv) == 5:
        _recorder(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
