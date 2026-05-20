#!/usr/bin/env python3
"""Claudia-ppt picker server.

Serves picker.html and the project files under presentations/ over HTTP so
the picker can fetch JSON without hitting the file:// CORS wall, and POST
back its selected_theme.json.

Defaults
--------
* Port: 7878 (override with --port)
* Picker root:        ../picker  (relative to this script)
* Presentations root: ../../presentations  (sibling of Claudia-ppt repo)

Endpoints
---------
GET  /                                  → 302 → /picker.html
GET  /picker.html                       → picker HTML
GET  /samples/...  /themes.json         → static picker assets
GET  /api/project/<slug>/exists         → {"exists": bool}
GET  /api/project/<slug>/files          → list of {name, mtime}
GET  /api/project/<slug>/file/<name>    → raw JSON file content
POST /api/project/<slug>/selected_theme → write selected_theme.json (atomic)
GET  /api/health                        → {"ok": true, "version": ...}
GET  /api/shutdown                      → stops the server (local-only)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
DEFAULT_PORT = 7878

PICKER_DIR = Path(__file__).resolve().parent

# Resolution order:
#   1. CLI --presentations
#   2. env CLAUDIA_PPT_PRESENTATIONS
#   3. <picker>/../../presentations  (sibling of the Claudia-ppt repo)
#   4. /Users/courcirc8/Dev/Cursor/MCPs/presentations  (hard default)
def _default_presentations_dir() -> Path:
    env = os.environ.get("CLAUDIA_PPT_PRESENTATIONS")
    if env:
        return Path(env).resolve()
    sibling = (PICKER_DIR.parent.parent / "presentations").resolve()
    if sibling.is_dir():
        return sibling
    return Path("/Users/courcirc8/Dev/Cursor/MCPs/presentations").resolve()


PRESENTATIONS_DIR = _default_presentations_dir()

ALLOWED_PROJECT_FILES = {
    "slides_content.json",
    "manifest.json",
    "selected_theme.json",
}

# Picker assets the HTTP server is allowed to serve. Anything else inside
# PICKER_DIR (server.py, __init__.py, __pycache__, future helper scripts…)
# stays private. Top-level entries are matched literally against the first
# path component of the requested URL.
ALLOWED_STATIC_FILES = {"picker.html", "themes.json"}
ALLOWED_STATIC_DIRS = {"samples"}


def _safe_slug(slug: str) -> str | None:
    """Reject anything that looks like a path traversal."""
    if not slug or "/" in slug or "\\" in slug or slug in {".", ".."}:
        return None
    if not all(c.isalnum() or c in "_-" for c in slug):
        return None
    return slug


def _project_dir(slug: str) -> Path | None:
    safe = _safe_slug(slug)
    if not safe:
        return None
    return PRESENTATIONS_DIR / safe


class Handler(SimpleHTTPRequestHandler):
    # SimpleHTTPRequestHandler serves files from cwd by default.
    # We override the routing entirely.

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet by default
        if os.environ.get("PICKER_VERBOSE"):
            super().log_message(fmt, *args)

    # --- helpers -----------------------------------------------------------
    def _send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self.send_error(HTTPStatus.NOT_FOUND, f"Not found: {path.name}")
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # --- routing -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]

        if path == "/" or path == "":
            self.send_response(302)
            self.send_header("Location", "/picker.html")
            self.end_headers()
            return

        # API
        if path.startswith("/api/"):
            return self._handle_api_get(path[5:])

        # Static picker assets — serve from PICKER_DIR.
        # Two layers of defense:
        #   1. resolved target must stay inside PICKER_DIR (blocks ../../etc/passwd)
        #   2. its first component must be in the explicit allowlist (blocks
        #      requests like /samples/../server.py that resolve to a real file
        #      inside PICKER_DIR but outside the served subset).
        rel = path.lstrip("/")
        target = (PICKER_DIR / rel).resolve()
        try:
            rel_resolved = target.relative_to(PICKER_DIR)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Out of root")
            return
        first = rel_resolved.parts[0] if rel_resolved.parts else ""
        if first in ALLOWED_STATIC_DIRS:
            pass  # any file under an allowed dir is OK
        elif first in ALLOWED_STATIC_FILES and len(rel_resolved.parts) == 1:
            pass  # exact-match allowed top-level file
        else:
            self.send_error(HTTPStatus.FORBIDDEN, "Not in static allowlist")
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, f"No such asset: {rel}")
            return

        ctype = "application/octet-stream"
        ext = target.suffix.lower()
        if ext == ".html":
            ctype = "text/html; charset=utf-8"
        elif ext == ".json":
            ctype = "application/json; charset=utf-8"
        elif ext == ".png":
            ctype = "image/png"
        elif ext == ".jpg" or ext == ".jpeg":
            ctype = "image/jpeg"
        elif ext == ".svg":
            ctype = "image/svg+xml"
        elif ext == ".css":
            ctype = "text/css"
        elif ext == ".js":
            ctype = "application/javascript"
        self._send_file(target, ctype)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/"):
            return self._handle_api_post(path[5:])
        self.send_error(HTTPStatus.NOT_FOUND, "Unknown endpoint")

    # --- API: GET ----------------------------------------------------------
    def _handle_api_get(self, sub: str) -> None:
        parts = sub.strip("/").split("/")

        if parts == ["health"]:
            return self._send_json(200, {"ok": True, "version": VERSION,
                                         "presentations_root": str(PRESENTATIONS_DIR)})

        if parts == ["shutdown"]:
            self._send_json(200, {"shutdown": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return

        if len(parts) >= 2 and parts[0] == "project":
            slug = parts[1]
            pdir = _project_dir(slug)
            if pdir is None:
                return self._send_json(400, {"error": "invalid slug"})

            # /project/<slug>/exists
            if len(parts) == 3 and parts[2] == "exists":
                return self._send_json(200, {"exists": pdir.is_dir(), "slug": slug})

            # /project/<slug>/files
            if len(parts) == 3 and parts[2] == "files":
                if not pdir.is_dir():
                    return self._send_json(404, {"error": "project not found"})
                files = []
                for name in ALLOWED_PROJECT_FILES:
                    f = pdir / name
                    if f.is_file():
                        files.append({"name": name, "mtime": f.stat().st_mtime,
                                      "size": f.stat().st_size})
                return self._send_json(200, {"slug": slug, "files": files})

            # /project/<slug>/file/<name>
            if len(parts) == 4 and parts[2] == "file":
                name = parts[3]
                if name not in ALLOWED_PROJECT_FILES:
                    return self._send_json(403, {"error": "file not allowed"})
                f = pdir / name
                if not f.is_file():
                    return self._send_json(404, {"error": f"{name} not found"})
                return self._send_file(f, "application/json; charset=utf-8")

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown API endpoint")

    # --- API: POST ---------------------------------------------------------
    def _handle_api_post(self, sub: str) -> None:
        parts = sub.strip("/").split("/")

        if len(parts) == 3 and parts[0] == "project" and parts[2] == "selected_theme":
            slug = parts[1]
            pdir = _project_dir(slug)
            if pdir is None:
                return self._send_json(400, {"error": "invalid slug"})
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length > 0 else b""
            try:
                payload = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError as e:
                return self._send_json(400, {"error": f"invalid json: {e}"})
            pdir.mkdir(parents=True, exist_ok=True)
            target = pdir / "selected_theme.json"
            # Atomic write via tempfile + rename
            with tempfile.NamedTemporaryFile("w", delete=False, dir=pdir,
                                             prefix=".st-", suffix=".json") as tmp:
                json.dump(payload, tmp, ensure_ascii=False, indent=2)
                tmp_path = tmp.name
            shutil.move(tmp_path, target)
            return self._send_json(200, {"saved": str(target), "bytes": len(raw)})

        self.send_error(HTTPStatus.NOT_FOUND, "Unknown POST endpoint")


def serve(port: int) -> None:
    server = HTTPServer(("127.0.0.1", port), Handler)
    print(f"Claudia-ppt picker server v{VERSION} on http://127.0.0.1:{port}",
          file=sys.stderr)
    print(f"  picker dir:        {PICKER_DIR}", file=sys.stderr)
    print(f"  presentations dir: {PRESENTATIONS_DIR}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Stopped.", file=sys.stderr)


def main() -> None:
    global PRESENTATIONS_DIR
    p = argparse.ArgumentParser(description="Claudia-ppt picker HTTP server")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--presentations", type=Path, default=None,
                   help="Absolute path to the presentations/ directory")
    args = p.parse_args()
    if args.presentations is not None:
        PRESENTATIONS_DIR = args.presentations.resolve()
    serve(args.port)


if __name__ == "__main__":
    main()
