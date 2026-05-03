"""Regression tests for picker/server.py.

Spawns the picker server as a subprocess against an isolated tmp_path
presentations root (seeded with tests/fixtures/mini_project/). Exercises
every API endpoint, security boundaries (path traversal, file whitelist),
and the atomic POST round-trip for selected_theme.json.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_SCRIPT = REPO_ROOT / "picker" / "server.py"
PICKER_HTML = REPO_ROOT / "picker" / "picker.html"
THEMES_JSON = REPO_ROOT / "picker" / "themes.json"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "mini_project"

STARTUP_TIMEOUT_S = 5.0
SHUTDOWN_TIMEOUT_S = 3.0


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _free_port() -> int:
    """Bind to port 0 to let the OS hand out an unused port, then release it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
    finally:
        s.close()


def _wait_until_ready(port: int, deadline: float) -> None:
    url = f"http://127.0.0.1:{port}/api/health"
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=0.5) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, ConnectionError, OSError) as e:
            last_err = e
            time.sleep(0.05)
    raise RuntimeError(f"server didn't come up on :{port}: {last_err!r}")


def _get(port: int, path: str) -> tuple[int, dict, bytes]:
    """Return (status, headers_dict, body_bytes). Never raises on HTTPError —
    converts it to a normal response so tests can assert on status codes."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


def _post_json(port: int, path: str, payload) -> tuple[int, dict, bytes]:
    body = json.dumps(payload).encode("utf-8") if not isinstance(payload, bytes) else payload
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read() or b""


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def presentations_root(tmp_path_factory) -> Path:
    """Isolated presentations dir seeded with the mini_project fixture."""
    root = tmp_path_factory.mktemp("presentations")
    shutil.copytree(FIXTURE_DIR, root / "mini_project")
    return root


@pytest.fixture(scope="module")
def server(presentations_root: Path):
    """Spawn picker/server.py on a free port, scoped to presentations_root.
    Yields (proc, port). Cleans up via /api/shutdown then SIGTERM as fallback."""
    if not SERVER_SCRIPT.is_file():
        pytest.skip(f"server script missing: {SERVER_SCRIPT}")

    port = _free_port()
    env = {**os.environ, "CLAUDIA_PPT_PRESENTATIONS": str(presentations_root)}
    # Ensure deterministic stdio on macOS / weird locales
    env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT), "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        _wait_until_ready(port, time.monotonic() + STARTUP_TIMEOUT_S)
        yield proc, port
    finally:
        # Polite shutdown via API
        try:
            _get(port, "/api/shutdown")
        except Exception:
            pass
        try:
            proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=SHUTDOWN_TIMEOUT_S)
            except subprocess.TimeoutExpired:
                proc.kill()


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
class TestStaticServing:
    def test_root_redirects_to_picker(self, server):
        proc, port = server
        # urllib follows redirects by default; use a no-follow request
        req = urllib.request.Request(f"http://127.0.0.1:{port}/", method="GET")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def http_error_302(self, req, fp, code, msg, headers):
                return fp  # don't follow

        opener = urllib.request.build_opener(NoRedirect)
        with opener.open(req, timeout=2.0) as resp:
            assert resp.status == 302
            assert resp.headers.get("Location") == "/picker.html"

    def test_picker_html_served(self, server):
        _, port = server
        status, headers, body = _get(port, "/picker.html")
        assert status == 200
        assert "text/html" in headers.get("Content-Type", "")
        assert body.lstrip().lower().startswith(b"<!doctype html>")

    def test_themes_json_served(self, server):
        _, port = server
        status, headers, body = _get(port, "/themes.json")
        assert status == 200
        assert "application/json" in headers.get("Content-Type", "")
        data = json.loads(body)
        assert "themes" in data

    def test_static_path_traversal_outside_picker_blocked(self, server):
        """Paths that resolve outside PICKER_DIR must be 403/404. These are the
        attacks that actually leak host data (e.g. /etc/passwd)."""
        _, port = server
        for evil in [
            "/../../../../etc/passwd",
            "/../../../../etc/hosts",
            "/..%2F..%2F..%2Fetc%2Fpasswd",
        ]:
            status, _, _ = _get(port, evil)
            assert status in (403, 404), f"{evil!r} → {status}, expected 403/404"

    def test_static_traversal_within_picker_dir_blocks_source(self, server):
        """Even when path traversal resolves to a file INSIDE PICKER_DIR
        (e.g. picker/samples/../server.py → picker/server.py), the static
        allowlist must block it. Otherwise the server source code itself
        becomes web-readable."""
        _, port = server
        for evil in [
            "/samples/../server.py",
            "/server.py",
            "/__init__.py",
        ]:
            status, _, _ = _get(port, evil)
            assert status == 403, f"{evil!r} → {status}, expected 403"

    def test_allowed_subdir_still_works(self, server):
        """Allowlist must not break legitimate subdir reads from samples/."""
        _, port = server
        # /samples is whitelisted as a dir; a 404 is fine when the file isn't
        # there (we don't seed images), but it must NOT be 403.
        status, _, _ = _get(port, "/samples/anything.png")
        assert status in (200, 404), f"got {status}, expected 200 or 404"

    def test_unknown_static_rejected(self, server):
        """Unknown top-level files are rejected by the allowlist (403 — we
        don't even reveal whether the file exists)."""
        _, port = server
        status, _, _ = _get(port, "/does-not-exist.html")
        assert status in (403, 404)


class TestHealth:
    def test_health_payload(self, server, presentations_root):
        _, port = server
        status, headers, body = _get(port, "/api/health")
        assert status == 200
        data = json.loads(body)
        assert data["ok"] is True
        assert "version" in data
        assert Path(data["presentations_root"]) == presentations_root


class TestProjectExists:
    def test_existing_project(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/mini_project/exists")
        assert status == 200
        data = json.loads(body)
        assert data == {"exists": True, "slug": "mini_project"}

    def test_missing_project(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/inexistant/exists")
        assert status == 200
        data = json.loads(body)
        assert data == {"exists": False, "slug": "inexistant"}


class TestProjectFiles:
    def test_lists_seeded_files_only(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/mini_project/files")
        assert status == 200
        data = json.loads(body)
        assert data["slug"] == "mini_project"
        names = sorted(f["name"] for f in data["files"])
        # selected_theme.json not seeded → should NOT appear yet
        assert names == ["manifest.json", "slides_content.json"]
        # mtime + size present and sane
        for f in data["files"]:
            assert f["mtime"] > 0
            assert f["size"] > 0

    def test_files_404_for_missing_project(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/inexistant/files")
        assert status == 404
        assert "error" in json.loads(body)


class TestProjectFile:
    def test_get_manifest(self, server):
        _, port = server
        status, headers, body = _get(port, "/api/project/mini_project/file/manifest.json")
        assert status == 200
        assert "application/json" in headers.get("Content-Type", "")
        data = json.loads(body)
        assert data["project"] == "mini_project"
        assert len(data["slides"]) == 3

    def test_get_slides_content(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/mini_project/file/slides_content.json")
        assert status == 200
        data = json.loads(body)
        assert {s["role"] for s in data["slides"]} == {"cover", "content", "closing"}

    def test_non_whitelisted_file_403(self, server):
        _, port = server
        status, _, body = _get(port, "/api/project/mini_project/file/random.json")
        assert status == 403
        assert "not allowed" in json.loads(body)["error"].lower()

    def test_missing_whitelisted_file_404(self, server):
        _, port = server
        # selected_theme.json is whitelisted but not seeded
        status, _, body = _get(port, "/api/project/mini_project/file/selected_theme.json")
        assert status == 404


class TestSecurity:
    """Path-traversal / sketchy slug rejection at the API level."""

    @pytest.mark.parametrize("slug", [
        "..",
        ".",
        "foo%2Fbar",   # url-encoded /
        "foo.bar",     # dot is not in [alnum_-]
        "foo$bar",     # special char
        "foo+bar",     # plus
        "foo%2Ebar",   # url-encoded dot
    ])
    def test_invalid_slug_rejected(self, server, slug):
        _, port = server
        status, _, body = _get(port, f"/api/project/{slug}/exists")
        assert status == 400, f"slug={slug!r} → {status}"
        assert "invalid slug" in json.loads(body)["error"].lower()

    def test_slug_with_slash_404s_routing(self, server):
        """A slug with a literal `/` doesn't match the 3-part route — server
        treats it as an unknown endpoint (404), which is also acceptable."""
        _, port = server
        status, _, _ = _get(port, "/api/project/foo/bar/exists")
        assert status in (400, 404)


class TestSelectedThemeWrite:
    def test_post_creates_file(self, server, presentations_root):
        _, port = server
        payload = {"theme_id": "test-theme", "palette": "earth", "font_pair": "fraunces+inter"}
        status, _, body = _post_json(port, "/api/project/mini_project/selected_theme", payload)
        assert status == 200
        result = json.loads(body)
        assert result["bytes"] > 0

        # File actually exists on disk
        target = presentations_root / "mini_project" / "selected_theme.json"
        assert target.is_file()
        on_disk = json.loads(target.read_text(encoding="utf-8"))
        assert on_disk == payload

    def test_round_trip_via_get(self, server):
        """After POST, the file must be readable via /file/selected_theme.json."""
        _, port = server
        payload = {"round": "trip", "n": 42}
        status_p, _, _ = _post_json(port, "/api/project/mini_project/selected_theme", payload)
        assert status_p == 200

        status_g, _, body = _get(port, "/api/project/mini_project/file/selected_theme.json")
        assert status_g == 200
        assert json.loads(body) == payload

    def test_invalid_json_rejected(self, server):
        _, port = server
        status, _, body = _post_json(
            port, "/api/project/mini_project/selected_theme", b"{not valid json"
        )
        assert status == 400
        assert "invalid json" in json.loads(body)["error"].lower()

    def test_invalid_slug_rejected(self, server):
        _, port = server
        status, _, body = _post_json(
            port, "/api/project/foo.bar/selected_theme", {"x": 1}
        )
        assert status == 400
        assert "invalid slug" in json.loads(body)["error"].lower()

    def test_creates_project_dir_if_missing(self, server, presentations_root):
        """POST to an unknown but valid slug creates the dir on the fly."""
        _, port = server
        slug = "newly_created"
        payload = {"created": True}
        status, _, _ = _post_json(port, f"/api/project/{slug}/selected_theme", payload)
        assert status == 200
        assert (presentations_root / slug / "selected_theme.json").is_file()
