"""pptx_kit — high-level helpers on top of python-pptx + ImageGen MCP.

Implements P2→P5 from MCP_IMPROVEMENTS.md:
- text: bulk_apply, smart_wrap
- image_style: style_anchor, generate_variations
- quality: incremental_export, diff_presentations
- accessibility: contrast, font_minimums, hierarchy

Usage:
    from pptx_kit import bulk_apply, smart_wrap, diff_presentations, audit_accessibility
"""
from .text import bulk_apply, smart_wrap
from .image_style import StyleAnchor, request_variations
from .quality import incremental_export, diff_presentations
from .accessibility import audit_accessibility

__all__ = [
    "bulk_apply", "smart_wrap",
    "StyleAnchor", "request_variations",
    "incremental_export", "diff_presentations",
    "audit_accessibility",
]
