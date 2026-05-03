#!/usr/bin/env python3
"""atelier_worker — polls ~/Downloads (and project inbox/) for new
'atelier-*.md' briefs, parses them, moves to inbox/, executes the build,
writes status to outbox/{code}.done.md, notifies macOS, and optionally
prints a Claude-ready resume line on stdout that the LLM can read.

Usage:
    python3 atelier_worker.py [--once] [--watch ~/Downloads]

Architecture:
    [HTML] download brief.md → ~/Downloads/atelier-*.md
            ↓ poll every 3s
    [worker] move to atelier/inbox/{code}.md
            ↓ parse (style/palette/font/layout)
    [worker] dispatch to pptx_kit + image-gen pipeline
            ↓ on completion
    [worker] write atelier/outbox/{code}.done.md (status)
            ↓
    [worker] notify macOS + emit `RESUME: code={code} pptx={path} score={N}`
            ↓
    [Claude]  reads resume line → confirms in conversation
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# PROJECT = the presentation project being processed (e.g. presentations/droit_des_familles)
# These are set by main() based on --project arg. The TOOL itself lives in PptxAtelier/.
PROJECT: Path | None = None
INBOX: Path | None = None
OUTBOX: Path | None = None
PROCESSED: Path | None = None
DEFAULT_WATCH = Path.home() / "Downloads"


def init_project_paths(project_dir: Path):
    """Initialize all paths under a specific project directory."""
    global PROJECT, INBOX, OUTBOX, PROCESSED
    PROJECT = project_dir.resolve()
    INBOX = PROJECT / "briefs"
    OUTBOX = PROJECT / "outbox"
    PROCESSED = PROJECT / "briefs" / ".processed"
    INBOX.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
POLL_SECONDS = 3
GLOB_TEMPLATE = "atelier-{project}-*.md"


def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {level:5s} {msg}", flush=True)


def notify_mac(title: str, message: str):
    """macOS notification via osascript. No-op on other platforms."""
    if sys.platform != "darwin":
        return
    try:
        subprocess.run([
            "osascript", "-e",
            f'display notification "{message}" with title "{title}" sound name "Glass"',
        ], check=False, capture_output=True)
    except Exception:
        pass


def parse_brief(md_text: str) -> dict:
    """Extract structured fields from a brief.md."""
    out = {"raw": md_text}
    code_match = re.search(r"\*\*Code\*\*:\s*ATL-([0-9A-F]+)", md_text)
    if code_match:
        out["code"] = code_match.group(1)
    date_match = re.search(r"\*\*Date\*\*:\s*(\S+)", md_text)
    if date_match:
        out["date"] = date_match.group(1)
    action_match = re.search(r"\*\*Action\*\*:\s*(\S+)", md_text)
    if action_match:
        out["action"] = action_match.group(1)
    # Style
    style_match = re.search(r"### Style visuel.*?id:\s*`([^`]+)`.*?name:\s*(.+?)$", md_text, re.DOTALL | re.MULTILINE)
    if style_match:
        out["style"] = {"id": style_match.group(1), "name": style_match.group(2).strip()}
    # Palette
    palette_match = re.search(r"### Palette.*?id:\s*`([^`]+)`.*?name:\s*(.+?)$", md_text, re.DOTALL | re.MULTILINE)
    if palette_match:
        out["palette"] = {"id": palette_match.group(1), "name": palette_match.group(2).strip()}
    # Colors
    colors = {}
    for role in ("primary", "accent", "gold", "text", "bg"):
        cm = re.search(rf"-\s*{role}:\s*`(#[0-9A-Fa-f]{{6}})`", md_text)
        if cm:
            colors[role] = cm.group(1)
    if colors:
        out.setdefault("palette", {})["colors"] = colors
    # Fonts
    display_match = re.search(r"display:\s*(.+?)$", md_text, re.MULTILINE)
    body_match = re.search(r"body:\s*(.+?)$", md_text, re.MULTILINE)
    if display_match and body_match:
        out["font"] = {"display": display_match.group(1).strip(), "body": body_match.group(1).strip()}
    # Layout
    ratio_match = re.search(r"ratio:\s*(.+?)$", md_text, re.MULTILINE)
    density_match = re.search(r"density:\s*(.+?)\s*\(", md_text, re.MULTILINE)
    img_match = re.search(r"image_style:\s*(.+?)\s*\(([^)]+)\)", md_text, re.MULTILINE)
    out["layout"] = {
        "ratio": ratio_match.group(1).strip() if ratio_match else "16/9",
        "density": density_match.group(1).strip() if density_match else "Normal",
        "image_style_id": img_match.group(2).strip() if img_match else "illustrated",
    }
    return out


def execute_brief(spec: dict) -> dict:
    """Dispatch on action. Returns status dict to write to outbox.

    NOTE: image generation and full pptx build require LLM/MCP access we don't
    have from this worker process. So this stub records the spec and emits a
    resume line for Claude (in the active conversation) to take over.
    """
    code = spec.get("code", "UNKNOWN")
    action = spec.get("action", "build_pptx")
    started = datetime.utcnow().isoformat() + "Z"

    log(f"Brief {code} — action={action}")
    log(f"  style={spec.get('style', {}).get('id')}, palette={spec.get('palette', {}).get('id')}, "
        f"font={spec.get('font', {}).get('display')}/{spec.get('font', {}).get('body')}")

    # Write in_progress marker
    in_prog = OUTBOX / f"{code}.in_progress.md"
    in_prog.write_text(f"# In progress\n\nStarted: {started}\n\n```json\n{json.dumps(spec, indent=2, ensure_ascii=False)}\n```\n")

    # Kick off the pipeline that requires LLM/MCP — we cannot do it from a pure
    # python worker. Emit a resume line that Claude (running in foreground) will
    # detect and act on.
    status = {
        "code": code,
        "action": action,
        "received_at": started,
        "status": "AWAITING_LLM",
        "spec": spec,
        "next": [
            "Claude: read this brief from atelier/inbox/{}.md".format(code),
            "Run pptx_kit pipeline with the spec",
            "Write atelier/outbox/{}.done.md when complete".format(code),
        ],
    }

    return status


def write_done(code: str, status: dict):
    done = OUTBOX / f"{code}.done.md"
    done.write_text(
        f"# Atelier — Brief {code} reçu\n\n"
        f"- **Status**: {status['status']}\n"
        f"- **Reçu**: {status['received_at']}\n"
        f"- **Action**: {status['action']}\n\n"
        f"## Spec\n\n```json\n{json.dumps(status['spec'], indent=2, ensure_ascii=False)}\n```\n\n"
        f"## Next steps\n\n"
        + "\n".join(f"{i+1}. {s}" for i, s in enumerate(status.get('next', [])))
    )
    in_prog = OUTBOX / f"{code}.in_progress.md"
    in_prog.unlink(missing_ok=True)


def emit_resume_line(status: dict):
    """A line on stdout that Claude (or a wrapper) can detect to wake up."""
    code = status["code"]
    print(f"\n>>> RESUME: code={code} status={status['status']} brief=atelier/inbox/{code}.md\n", flush=True)


def process_brief(md_path: Path):
    """Move brief to inbox, parse, execute, write status."""
    text = md_path.read_text(encoding="utf-8")
    spec = parse_brief(text)
    code = spec.get("code") or "UNKNOWN"

    # Move into inbox with canonical name
    target = INBOX / f"{code}.md"
    INBOX.mkdir(parents=True, exist_ok=True)
    OUTBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)

    if md_path.parent != INBOX:
        shutil.move(str(md_path), str(target))
        log(f"Brief {code} reçu → {target}")
    else:
        target = md_path

    notify_mac("Atelier — brief reçu", f"Code {code} prêt à exécuter")

    status = execute_brief(spec)
    write_done(code, status)
    emit_resume_line(status)


def watch(watch_dir: Path, glob: str, once: bool = False):
    """Main loop: poll watch_dir for new briefs matching glob."""
    log(f"atelier_worker démarré — watch={watch_dir} project={PROJECT}")
    log(f"Glob: {glob} | Poll: {POLL_SECONDS}s | Inbox: {INBOX}")

    seen = set()
    # Pre-populate seen with existing files so we don't re-process old briefs
    for p in watch_dir.glob(glob):
        seen.add(p.resolve())

    try:
        while True:
            for md in sorted(watch_dir.glob(glob)):
                rp = md.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                try:
                    process_brief(md)
                except Exception as e:
                    log(f"Erreur sur {md.name}: {e}", "ERROR")
            if once:
                break
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        log("Arrêt demandé (Ctrl-C)")


def main():
    ap = argparse.ArgumentParser(description="Atelier worker — polls Downloads for briefs")
    ap.add_argument("--project", type=Path, required=True,
                   help="Path to the presentation project directory (e.g. presentations/droit_des_familles)")
    ap.add_argument("--watch", type=Path, default=DEFAULT_WATCH,
                   help=f"Directory to watch (default: {DEFAULT_WATCH})")
    ap.add_argument("--once", action="store_true",
                   help="Process current files and exit (don't loop)")
    args = ap.parse_args()

    if not args.project.exists():
        sys.exit(f"❌ Project directory does not exist: {args.project}")

    init_project_paths(args.project)
    project_name = args.project.name
    glob = GLOB_TEMPLATE.format(project=project_name)
    watch(args.watch, glob, once=args.once)


if __name__ == "__main__":
    main()
