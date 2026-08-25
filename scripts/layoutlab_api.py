#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

LAYOUTLIB_ROOT = Path(os.environ.get("LAYOUTLIB_ROOT", "/home/agentos-node/projects/layoutlib"))
if str(LAYOUTLIB_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(LAYOUTLIB_ROOT / "src"))

from layoutlib import parse_floorplan  # type: ignore  # noqa: E402

MAX_BODY = 12 * 1024 * 1024


def _float(q: dict, key: str, default: float, lo: float, hi: float) -> float:
    try:
        value = float(q.get(key, [default])[0])
    except Exception:
        value = default
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def _int(q: dict, key: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(q.get(key, [default])[0])
    except Exception:
        value = default
    if not lo <= value <= hi:
        raise ValueError(f"{key} must be between {lo} and {hi}")
    return value


def parse_pgm_bytes(body: bytes, query: str) -> dict:
    if not body.startswith((b"P2", b"P5")):
        raise ValueError("Layout Lab v0.1 API accepts PGM (P2/P5) input")
    q = parse_qs(query)
    scale = _float(q, "meters_per_pixel", 0.02, 0.0001, 10.0)
    height = _float(q, "wall_height_m", 2.7, 0.5, 20.0)
    threshold = _int(q, "threshold", 128, 0, 255)
    min_length = _int(q, "min_wall_length_px", 16, 2, 5000)
    max_thickness = _int(q, "max_wall_thickness_px", 16, 1, 512)

    with tempfile.NamedTemporaryFile(suffix=".pgm", delete=False) as f:
        f.write(body)
        temp = Path(f.name)
    try:
        ir = parse_floorplan(
            temp,
            meters_per_pixel=scale,
            threshold=threshold,
            min_wall_length_px=min_length,
            max_wall_thickness_px=max_thickness,
            wall_height_m=height,
        )
        return {
            "ok": True,
            "engine": "layoutlib",
            "engine_version": getattr(__import__("layoutlib"), "__version__", "unknown"),
            "ir": ir.to_dict(),
            "warnings": [
                "v0.1 targets high-contrast, mostly orthogonal floor plans.",
                "Detected wall geometry is not a structural/load-bearing determination.",
            ],
        }
    finally:
        temp.unlink(missing_ok=True)


class Handler(BaseHTTPRequestHandler):
    server_version = "LayoutLabAPI/0.1"

    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")
        if path in ("", "/healthz"):
            self._json(200, {"ok": True, "service": "layoutlab-api", "layoutlib_root": str(LAYOUTLIB_ROOT)})
        else:
            self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") not in ("/parse", "/layout-lab/api/parse"):
            self._json(404, {"ok": False, "error": "not found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError(f"request body must be 1..{MAX_BODY} bytes")
            body = self.rfile.read(length)
            self._json(200, parse_pgm_bytes(body, parsed.query))
        except ValueError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:
            self._json(500, {"ok": False, "error": f"layoutlib parse failed: {exc}"})

    def log_message(self, fmt, *args):
        sys.stderr.write("layoutlab-api: " + fmt % args + "\n")


def main() -> int:
    p = argparse.ArgumentParser(description="Layout Lab API backed by LayoutLib")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=int(os.environ.get("PORT", "0")))
    args = p.parse_args()
    if not args.port:
        raise SystemExit("--port or PORT is required; allocate it through AgentOS Port Manager")
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(json.dumps({"service":"layoutlab-api","host":args.host,"port":args.port,"layoutlib_root":str(LAYOUTLIB_ROOT)}), flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
