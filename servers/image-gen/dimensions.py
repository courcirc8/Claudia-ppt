"""Helpers résolution / orientation — partagés avec RetoucheImage."""
from __future__ import annotations

# Map des orientations UI → (ratio_w, ratio_h)
_ORIENTATION_RATIOS = {
    "square":         (1, 1),
    "landscape_3_2":  (3, 2),
    "landscape_16_9": (16, 9),
    "landscape_4_3":  (4, 3),
    "portrait_2_3":   (2, 3),
    "portrait_9_16":  (9, 16),
    "portrait_3_4":   (3, 4),
}


def resolve_target_aspect(orientation: str, src_w: int, src_h: int) -> tuple[int, int]:
    """Retourne (rw, rh) du ratio cible. 'auto' = ratio image source."""
    if orientation in _ORIENTATION_RATIOS:
        return _ORIENTATION_RATIOS[orientation]
    return (max(src_w, 1), max(src_h, 1))


def gpt_image_2_aspect(orientation: str, src_w: int, src_h: int) -> str:
    """gpt-image-2 ne supporte que 1:1, 3:2, 2:3."""
    if orientation == "square":
        return "1:1"
    if orientation == "landscape_3_2":
        return "3:2"
    if orientation == "portrait_2_3":
        return "2:3"
    if src_w == src_h:
        return "1:1"
    return "3:2" if src_w > src_h else "2:3"


def parse_max_resolution(raw, fallback_int: int = 2000) -> tuple[int, str]:
    """Pour gpt-image-2, max_resolution = qualité ('low'/'medium'/'high'/'auto')."""
    try:
        return (int(raw), "medium")
    except (ValueError, TypeError):
        return (fallback_int, str(raw) if raw else "medium")


def compute_dimensions(orientation: str, max_res: int, src_w: int, src_h: int) -> tuple[int, int]:
    """Calcule (out_w, out_h) tels que max(out_w, out_h) ≈ max_res, ratio = orientation cible."""
    rw, rh = resolve_target_aspect(orientation, src_w, src_h)
    if rw >= rh:
        out_w = max_res
        out_h = int(round(max_res * rh / rw))
    else:
        out_h = max_res
        out_w = int(round(max_res * rw / rh))
    out_w = max(64, (out_w // 8) * 8)
    out_h = max(64, (out_h // 8) * 8)
    return out_w, out_h


def seedream_size_label(max_resolution: int) -> str:
    """Map int → '1K'/'2K'/'4K' pour seedream-4.5."""
    if max_resolution >= 4000:
        return "4K"
    if max_resolution >= 2000:
        return "2K"
    return "1K"
