"""Image-gen style anchoring + variations.

Wraps the ImageGen MCP via subprocess-able prompt patterns. Since we can't
call the MCP directly from pure python here, this module produces *prompt
contracts* the agent can execute, plus local helpers (cache, manifest)."""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import shutil


@dataclass
class StyleAnchor:
    """A reusable visual style spec.

    Once defined, pass `style_anchor.prefix` into every image prompt to enforce
    palette, mood and composition consistency without repeating yourself."""
    name: str
    palette_words: str  # e.g. "soft pink, mauve and deep violet with gold accents"
    mood: str  # e.g. "elegant editorial, refined and feminine"
    constraints: str = "NO TEXT, NO LETTERS, NO WORDS visible"
    reference_image: str | None = None  # path to anchor image (optional, for image-to-image flows)

    @property
    def prefix(self) -> str:
        """The prompt prefix that locks the style."""
        return (
            f"{self.mood}, refined palette of {self.palette_words}. "
            f"{self.constraints}. Subject:"
        )

    def prompt_for(self, subject: str) -> str:
        """Compose a full prompt for a subject under this style."""
        return f"{self.prefix} {subject}"

    def save(self, path: str | Path):
        Path(path).write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, path: str | Path) -> "StyleAnchor":
        data = json.loads(Path(path).read_text())
        return cls(**data)


# Pre-built anchors matching themes.json
THEMES = {
    "pink_violet": StyleAnchor(
        name="pink_violet",
        palette_words="soft pink, mauve and deep violet with gold accents",
        mood="Elegant minimalist editorial illustration",
    ),
    "navy_gold": StyleAnchor(
        name="navy_gold",
        palette_words="deep navy blue, ivory cream and warm gold",
        mood="Sophisticated corporate editorial illustration",
    ),
    "earth_terracotta": StyleAnchor(
        name="earth_terracotta",
        palette_words="warm terracotta, soft beige, deep brown and cream",
        mood="Warm earthy editorial illustration",
    ),
    "teal_coral": StyleAnchor(
        name="teal_coral",
        palette_words="deep teal, coral pink, light gray and white",
        mood="Modern fresh contemporary illustration",
    ),
    "mono_crimson": StyleAnchor(
        name="mono_crimson",
        palette_words="charcoal black, gray and a single accent of crimson red",
        mood="Strict monochrome graphic editorial illustration",
    ),
    "sage_rose": StyleAnchor(
        name="sage_rose",
        palette_words="soft sage green, warm cream, dusty rose and antique gold",
        mood="Botanical organic editorial illustration with delicate leaf motifs",
    ),
}


def request_variations(image_id: str, count: int = 4, variation_strength: float = 0.4) -> list[dict]:
    """Return a list of MCP tool-call specs the agent should execute to get N
    variations of an existing image. The agent runs them in parallel.

    Until the ImageGen MCP exposes a native variations endpoint, this leverages
    the existing image_to_image with low strength (semantic preservation +
    subtle redraw).
    """
    return [
        {
            "tool": "mcp__image-gen__tool_image_to_image",
            "input": {
                "image_id": image_id,
                "prompt": "subtle artistic variation, same subject and palette",
                "strength": variation_strength,
                "seed": 1000 + i,
            },
        }
        for i in range(count)
    ]


def manifest_for_project(project_root: str | Path) -> Path:
    """Return path to manifest.json (created if missing)."""
    p = Path(project_root) / "manifest.json"
    if not p.exists():
        p.write_text(json.dumps({"slides": [], "images": []}, indent=2))
    return p


def register_image(project_root: str | Path, slide_idx: int, image_path: str | Path,
                    prompt: str, model: str, theme_anchor: str | None = None):
    """Append image record to manifest.json for traceability/reuse."""
    mp = manifest_for_project(project_root)
    data = json.loads(mp.read_text())
    data.setdefault("images", []).append({
        "slide_index": slide_idx,
        "path": str(image_path),
        "prompt": prompt,
        "model": model,
        "theme_anchor": theme_anchor,
    })
    mp.write_text(json.dumps(data, indent=2, ensure_ascii=False))


_IMAGE_ID_RE = __import__("re").compile(r"^[A-Za-z0-9_-]+$")


def adopt_from_cache(image_id: str, project_root: str | Path,
                       cache_root: str = "~/.cache/image-gen") -> Path:
    """Copy an image-gen cached PNG into <project>/images/<image_id>.png.

    image_id is restricted to [A-Za-z0-9_-]+ to defeat path traversal
    (e.g. "../../etc/passwd").
    """
    if not isinstance(image_id, str) or not _IMAGE_ID_RE.match(image_id):
        raise ValueError(f"image_id invalide (must match [A-Za-z0-9_-]+): {image_id!r}")
    cache_root = Path(cache_root).expanduser().resolve()
    src = (cache_root / f"{image_id}.png").resolve()
    try:
        src.relative_to(cache_root)
    except ValueError:
        raise ValueError("image_id résout hors du cache root")
    if not src.exists():
        raise FileNotFoundError(src)
    dst_dir = Path(project_root) / "images"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{image_id}.png"
    shutil.copy2(src, dst)
    return dst
