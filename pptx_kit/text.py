"""Text utilities: bulk_apply (multi-slide formatting) and smart_wrap (line breaks)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Iterable
from pptx import Presentation
from pptx.util import Pt, Inches, Emu

# Avg char width in points by font family (proxy — Calibri/Inter ~0.48em, Georgia ~0.52em)
_AVG_CHAR_WIDTH = {
    "Calibri": 0.50, "Calibri Light": 0.48,
    "Inter": 0.50, "Helvetica": 0.50, "Arial": 0.52,
    "Georgia": 0.55, "Times New Roman": 0.50,
    "default": 0.52,
}


@dataclass
class ShapeInfo:
    slide_index: int
    shape_index: int
    name: str
    role: str  # "title" | "body" | "image" | "other"
    left_in: float
    top_in: float
    width_in: float
    height_in: float
    font_size_pt: int | None
    text: str | None


def _classify(slide_idx: int, shape) -> str:
    """Heuristic role classifier based on position + type."""
    if shape.shape_type == 13:  # Picture
        return "image"
    if shape.shape_type != 17:  # not text box
        return "other"
    top = shape.top / 914400
    left = shape.left / 914400
    if top < 1.3:
        return "title"
    return "body"


def inspect(pptx_path: str) -> list[ShapeInfo]:
    """Return one ShapeInfo per shape in the deck. Useful for filter targeting."""
    p = Presentation(pptx_path)
    out = []
    for si, slide in enumerate(p.slides):
        for shi, shape in enumerate(slide.shapes):
            font_size = None
            text = None
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    for run in para.runs:
                        if run.font.size:
                            font_size = int(run.font.size.pt)
                            break
                    if font_size:
                        break
                text = shape.text_frame.text
            out.append(ShapeInfo(
                slide_index=si, shape_index=shi,
                name=shape.name,
                role=_classify(si, shape),
                left_in=shape.left/914400, top_in=shape.top/914400,
                width_in=shape.width/914400, height_in=shape.height/914400,
                font_size_pt=font_size, text=text,
            ))
    return out


def bulk_apply(
    pptx_path: str,
    *,
    filter: dict | Callable[[ShapeInfo], bool] | None = None,
    font_size: int | None = None,
    font_name: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    color_rgb: tuple[int, int, int] | None = None,
    save: bool = True,
) -> int:
    """Apply formatting in bulk to shapes matching `filter`.

    filter dict supports keys:
      - role: "title" | "body" | "image" | "other"
      - slide_indexes: iterable of int
      - min_top_in / max_top_in: float
      - text_contains: str

    Or pass a callable(ShapeInfo) -> bool for arbitrary logic.

    Returns number of shapes modified.
    """
    p = Presentation(pptx_path)
    shapes = inspect(pptx_path)

    def matches(info: ShapeInfo) -> bool:
        if filter is None:
            return True
        if callable(filter):
            return filter(info)
        if "role" in filter and info.role != filter["role"]:
            return False
        if "slide_indexes" in filter and info.slide_index not in filter["slide_indexes"]:
            return False
        if "min_top_in" in filter and info.top_in < filter["min_top_in"]:
            return False
        if "max_top_in" in filter and info.top_in > filter["max_top_in"]:
            return False
        if "text_contains" in filter and (info.text or "").find(filter["text_contains"]) < 0:
            return False
        return True

    modified = 0
    for info in shapes:
        if not matches(info):
            continue
        slide = p.slides[info.slide_index]
        shape = list(slide.shapes)[info.shape_index]
        if not shape.has_text_frame:
            continue
        for para in shape.text_frame.paragraphs:
            for run in para.runs:
                if font_size is not None:
                    run.font.size = Pt(font_size)
                if font_name is not None:
                    run.font.name = font_name
                if bold is not None:
                    run.font.bold = bold
                if italic is not None:
                    run.font.italic = italic
                if color_rgb is not None:
                    from pptx.dml.color import RGBColor
                    run.font.color.rgb = RGBColor(*color_rgb)
        modified += 1
    if save and modified:
        p.save(pptx_path)
    return modified


# ─── smart_wrap ─────────────────────────────────────────────────────────────

# Tokens that should never be split across line breaks (legal/typographic atomic units)
_KEEP_TOGETHER = [
    r"art\. ?\d+[a-z]?(?: ch\. ?\d+)?(?: al\. ?\d+)?(?: CC| CO| CP)?",  # art. 198 ch. 2 CC
    r"TF \d+[A-Z]_\d+/\d+",  # TF 5A_54/2024
    r"\d+ ?(?:CHF|EUR|USD|%|km|m|kg|h|min)",  # 5 CHF / 10%
    r"\d+\s+(?:janv|févr|mars|avril|mai|juin|juil|août|sept|oct|nov|déc)\w*\s*\d{2,4}",
]

import re as _re
_KEEP_RE = _re.compile("|".join(f"({pat})" for pat in _KEEP_TOGETHER), _re.IGNORECASE)


def smart_wrap(text: str, *, width_in: float, font_size_pt: int, font_name: str = "Calibri",
               max_lines: int | None = None) -> str:
    """Wrap `text` with explicit \\n at optimal positions.

    Strategy:
    - Estimate chars/line budget from box width and font.
    - Keep atomic tokens (art. 198 CC, TF refs, dates) together.
    - Prefer breaking at punctuation > spaces; never mid-word.
    - Returns text with \\n inserted; existing \\n preserved.
    """
    char_w = _AVG_CHAR_WIDTH.get(font_name, _AVG_CHAR_WIDTH["default"]) * font_size_pt
    # Usable width minus PowerPoint's ~0.1" inset on each side
    usable_pt = (width_in - 0.2) * 72
    chars_per_line = max(20, int(usable_pt / char_w))

    # Mark keep-together tokens with NBSP-equivalent so they stay atomic
    PLACEHOLDER = "⁠"  # word joiner (zero-width)

    def _atomize(line):
        return _KEEP_RE.sub(lambda m: m.group(0).replace(" ", PLACEHOLDER), line)

    def _restore(s):
        return s.replace(PLACEHOLDER, " ")

    out_paragraphs = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            out_paragraphs.append("")
            continue
        atomized = _atomize(paragraph)
        words = atomized.split(" ")
        lines = []
        cur = ""
        for w in words:
            candidate = w if not cur else cur + " " + w
            if len(candidate) <= chars_per_line:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        out_paragraphs.append("\n".join(_restore(line).rstrip() for line in lines))

    result = "\n".join(out_paragraphs)
    if max_lines and result.count("\n") + 1 > max_lines:
        # Soft warning — return as-is but log
        import sys
        print(f"[smart_wrap] text exceeds max_lines={max_lines}: got {result.count(chr(10))+1}", file=sys.stderr)
    return result


def estimate_capacity(width_in: float, height_in: float, font_size_pt: int,
                       font_name: str = "Calibri", line_spacing: float = 1.2) -> dict:
    """Return chars_per_line and max_lines for a given text box."""
    char_w = _AVG_CHAR_WIDTH.get(font_name, _AVG_CHAR_WIDTH["default"]) * font_size_pt
    usable_w_pt = (width_in - 0.2) * 72
    chars_per_line = int(usable_w_pt / char_w)
    line_h_pt = font_size_pt * line_spacing
    usable_h_pt = (height_in - 0.1) * 72
    max_lines = int(usable_h_pt / line_h_pt)
    return {
        "chars_per_line": chars_per_line,
        "max_lines": max_lines,
        "wrap_safe_threshold": int(chars_per_line * 0.9),  # buffer for char-width variance
    }
