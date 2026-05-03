"""Path sandboxing for the image-gen MCP server.

`register_image(file_path=...)` reads bytes from the local filesystem and stores
them in the cache. Without sandboxing, an MCP caller can register any file the
process can read (e.g. ~/.ssh/id_rsa) and exfiltrate it via get_image.

Configuration:
  IMAGE_GEN_UPLOAD_ROOT  — absolute dir under which register_image may read.
                            Defaults to the current working directory.
  IMAGE_GEN_ALLOW_ANY    — set to "1" to disable sandboxing (NOT recommended).
"""
from __future__ import annotations

import os
from pathlib import Path


def upload_root() -> Path:
    root = os.environ.get("IMAGE_GEN_UPLOAD_ROOT") or os.getcwd()
    return Path(root).expanduser().resolve()


def sandbox_disabled() -> bool:
    return os.environ.get("IMAGE_GEN_ALLOW_ANY", "").strip() == "1"


def resolve_upload_path(file_path: str) -> Path:
    """Resolve a user-supplied upload path against upload_root and refuse traversal."""
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path requis")
    if sandbox_disabled():
        return Path(file_path).expanduser().resolve()

    root = upload_root()
    p = Path(file_path).expanduser()
    p = (root / p) if not p.is_absolute() else p
    p = p.resolve()
    try:
        p.relative_to(root)
    except ValueError:
        raise ValueError(
            f"file_path hors du répertoire autorisé ({root}). "
            "Définir IMAGE_GEN_UPLOAD_ROOT ou utiliser un chemin relatif."
        )
    return p
