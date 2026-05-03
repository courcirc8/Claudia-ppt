"""Path sandboxing for the PowerPoint MCP server.

All file_path arguments accepted from MCP callers MUST go through resolve_safe_path
so a malicious prompt cannot read/write outside the configured workspace root.

Configuration:
  PPT_WORKSPACE_ROOT  — absolute dir under which all reads/writes are allowed.
                         Defaults to the current working directory.
  PPT_ALLOW_ANY_PATH  — set to "1" to disable sandboxing (NOT recommended;
                         only for trusted local single-user setups).
"""
from __future__ import annotations

import os
from pathlib import Path

_ALLOWED_EXTS = {".pptx", ".potx", ".ppt", ".pps", ".ppsx"}


def workspace_root() -> Path:
    root = os.environ.get("PPT_WORKSPACE_ROOT") or os.getcwd()
    return Path(root).expanduser().resolve()


def sandbox_disabled() -> bool:
    return os.environ.get("PPT_ALLOW_ANY_PATH", "").strip() == "1"


def resolve_safe_path(file_path: str, *, must_exist: bool = False,
                      require_pptx_ext: bool = True) -> Path:
    """Resolve file_path against the workspace root and refuse traversal.

    Raises ValueError if the resolved path escapes the workspace, if the
    extension is not in the allowlist, or if must_exist=True and the file
    does not exist. Returns a resolved absolute Path.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path is required")
    if sandbox_disabled():
        p = Path(file_path).expanduser().resolve()
        if must_exist and not p.exists():
            raise ValueError(f"File not found: {file_path}")
        return p

    root = workspace_root()
    p = Path(file_path).expanduser()
    p = (root / p) if not p.is_absolute() else p
    p = p.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError(
            f"Path escapes workspace root ({root}). "
            "Set PPT_WORKSPACE_ROOT or use a relative path."
        )
    if require_pptx_ext and p.suffix.lower() not in _ALLOWED_EXTS:
        raise ValueError(
            f"Unsupported extension '{p.suffix}'. Allowed: {sorted(_ALLOWED_EXTS)}"
        )
    if must_exist and not p.exists():
        raise ValueError(f"File not found: {file_path}")
    return p
