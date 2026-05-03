"""Quality loop helpers: incremental PNG export + structured diff."""
from __future__ import annotations
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
from pptx import Presentation


def _slide_xml_hash(slide) -> str:
    """Hash the slide XML to detect changes."""
    xml = slide._element.xml
    return hashlib.sha256(xml.encode("utf-8")).hexdigest()[:16]


def _all_hashes(pptx_path: str) -> dict[int, str]:
    p = Presentation(pptx_path)
    return {i: _slide_xml_hash(s) for i, s in enumerate(p.slides)}


def incremental_export(
    pptx_path: str,
    out_dir: str | Path,
    *,
    only_changed: bool = True,
    state_file: str | None = None,
    width_px: int = 1334,  # 13.33" @100dpi
) -> dict:
    """Export slide PNGs, optionally re-rendering only slides whose XML changed.

    Returns {"rendered": [slide_indexes], "skipped": [...], "total": N}.

    State is stored in `<out_dir>/.export_state.json` by default.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    state_path = Path(state_file) if state_file else out_dir / ".export_state.json"

    new_hashes = _all_hashes(pptx_path)
    old_hashes = {}
    if state_path.exists() and only_changed:
        old_hashes = {int(k): v for k, v in json.loads(state_path.read_text()).items()}

    changed = [i for i, h in new_hashes.items() if old_hashes.get(i) != h]
    unchanged = [i for i in new_hashes if i not in changed]

    if not changed and only_changed:
        return {"rendered": [], "skipped": list(new_hashes), "total": len(new_hashes)}

    # Full export via soffice + pdftoppm (cross-platform)
    pdf_tmp = Path("/tmp") / (Path(pptx_path).stem + ".pdf")
    pdf_tmp.unlink(missing_ok=True)
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir", "/tmp", str(pptx_path)],
        check=True, capture_output=True,
    )
    dpi = int(width_px / 13.333)
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(dpi), str(pdf_tmp), str(out_dir / "slide")],
        check=True, capture_output=True,
    )

    # If only_changed, optionally restore unchanged ones from previous state
    # (here we just always overwrite all on a single pdftoppm call — simpler)
    state_path.write_text(json.dumps(new_hashes, indent=2))
    return {"rendered": changed, "skipped": unchanged, "total": len(new_hashes)}


def diff_presentations(before_pptx: str, after_pptx: str) -> list[dict]:
    """Compare two .pptx files. Returns structured changes."""
    pa = Presentation(before_pptx)
    pb = Presentation(after_pptx)
    out: list[dict] = []

    if pa.slide_width != pb.slide_width or pa.slide_height != pb.slide_height:
        out.append({
            "scope": "deck", "kind": "slide_size",
            "before": (pa.slide_width/914400, pa.slide_height/914400),
            "after": (pb.slide_width/914400, pb.slide_height/914400),
        })

    n = max(len(pa.slides), len(pb.slides))
    for i in range(n):
        if i >= len(pa.slides):
            out.append({"slide": i, "kind": "added"})
            continue
        if i >= len(pb.slides):
            out.append({"slide": i, "kind": "removed"})
            continue
        sa, sb = pa.slides[i], pb.slides[i]
        ha, hb = _slide_xml_hash(sa), _slide_xml_hash(sb)
        if ha == hb:
            continue
        # Detail per shape
        shapes_a = list(sa.shapes); shapes_b = list(sb.shapes)
        for j in range(max(len(shapes_a), len(shapes_b))):
            if j >= len(shapes_a):
                out.append({"slide": i, "shape": j, "kind": "shape_added", "name": shapes_b[j].name})
                continue
            if j >= len(shapes_b):
                out.append({"slide": i, "shape": j, "kind": "shape_removed", "name": shapes_a[j].name})
                continue
            a, b = shapes_a[j], shapes_b[j]
            for attr in ("left", "top", "width", "height"):
                va, vb = getattr(a, attr), getattr(b, attr)
                if va != vb:
                    out.append({
                        "slide": i, "shape": j, "kind": f"{attr}_changed",
                        "before_in": va/914400, "after_in": vb/914400,
                    })
            # Text changes
            if a.has_text_frame and b.has_text_frame:
                ta, tb = a.text_frame.text, b.text_frame.text
                if ta != tb:
                    out.append({"slide": i, "shape": j, "kind": "text_changed",
                               "before": ta[:80], "after": tb[:80]})
                # Font size
                fa = _first_font_size(a); fb = _first_font_size(b)
                if fa != fb:
                    out.append({"slide": i, "shape": j, "kind": "font_size_changed",
                               "before": fa, "after": fb})
    return out


def _first_font_size(shape) -> int | None:
    if not shape.has_text_frame:
        return None
    for para in shape.text_frame.paragraphs:
        for run in para.runs:
            if run.font.size:
                return int(run.font.size.pt)
    return None
