"""Demo: run the toolkit against the existing droit_des_familles.pptx."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pptx_kit.text import inspect, bulk_apply, smart_wrap, estimate_capacity
from pptx_kit.quality import incremental_export, diff_presentations
from pptx_kit.accessibility import audit_accessibility, format_issues
from pptx_kit.image_style import THEMES, request_variations

PROJ = Path(__file__).resolve().parent.parent
PPTX = PROJ / "droit_des_familles.pptx"


def section(title):
    print("\n" + "═" * 60)
    print(f" {title}")
    print("═" * 60)


def demo_inspect():
    section("inspect() — what's in the deck")
    shapes = inspect(str(PPTX))
    by_role = {}
    for s in shapes:
        by_role.setdefault(s.role, 0)
        by_role[s.role] += 1
    print(f"Total shapes: {len(shapes)}")
    print(f"By role: {by_role}")
    # Show first body shape per slide for clarity
    seen = set()
    for s in shapes:
        if s.role == "body" and s.slide_index not in seen:
            print(f"  slide {s.slide_index}: body @({s.left_in:.1f},{s.top_in:.1f}) "
                  f"{s.width_in:.1f}×{s.height_in:.1f} font={s.font_size_pt}pt")
            seen.add(s.slide_index)


def demo_capacity():
    section("estimate_capacity() — text budget per box")
    cap = estimate_capacity(width_in=8.13, height_in=5.4, font_size_pt=22, font_name="Calibri")
    print(f"Body box 8.13×5.4 @22pt Calibri:")
    print(f"  → {cap['chars_per_line']} chars/line, {cap['max_lines']} max lines")
    print(f"  → safe wrap threshold: {cap['wrap_safe_threshold']} chars")


def demo_smart_wrap():
    section("smart_wrap() — auto line breaks")
    txt = ("Les biens acquis avant le mariage avec une garantie juridique constituent "
           "des biens propres (art. 198 ch. 2 CC) selon l'arrêt TF 5A_54/2024 du 15 mars 2026.")
    out = smart_wrap(txt, width_in=8.13, font_size_pt=22, font_name="Calibri")
    print("Original (no breaks):")
    print(f"  {txt}")
    print("Wrapped:")
    for line in out.split("\n"):
        print(f"  | {line}")


def demo_diff():
    section("diff_presentations() — what changed v6 vs current")
    # Snapshot current to /tmp first then diff against itself for self-test
    import shutil
    snap = "/tmp/_snap.pptx"
    shutil.copy2(str(PPTX), snap)
    diff = diff_presentations(snap, str(PPTX))
    print(f"Self-diff (should be empty): {len(diff)} change(s)")


def demo_audit():
    section("audit_accessibility() — a11y + layout audit")
    issues = audit_accessibility(str(PPTX))
    by_sev = {}
    for i in issues:
        by_sev.setdefault(i.severity, 0)
        by_sev[i.severity] += 1
    print(f"Total issues: {len(issues)} — {by_sev}")
    print()
    print(format_issues(issues[:15]))
    if len(issues) > 15:
        print(f"... and {len(issues) - 15} more")


def demo_bulk_apply():
    section("bulk_apply() — would-modify count (dry, no save)")
    n = bulk_apply(str(PPTX), filter={"role": "body"}, save=False)
    print(f"Body shapes that would be modified: {n}")


def demo_themes():
    section("StyleAnchor — pre-built themes")
    for k, anchor in THEMES.items():
        print(f"  {k:20s} → {anchor.mood[:50]}")
    print()
    print("Sample full prompt for theme 'navy_gold':")
    print("  " + THEMES["navy_gold"].prompt_for("a passport and a family silhouette"))


def demo_variations():
    section("request_variations() — N alternatives spec")
    specs = request_variations("d67949e73044c3c1", count=3)
    print(f"Generated {len(specs)} tool-call specs the agent should run in parallel:")
    for i, s in enumerate(specs):
        print(f"  [{i}] tool={s['tool']} seed={s['input']['seed']} strength={s['input']['strength']}")


def demo_incremental_export():
    section("incremental_export() — only changed slides")
    out = PROJ / "png_review" / "v_incremental"
    res1 = incremental_export(str(PPTX), str(out))
    print(f"First run: rendered={len(res1['rendered'])}/{res1['total']}")
    res2 = incremental_export(str(PPTX), str(out))
    print(f"Second run (no changes): rendered={len(res2['rendered'])}/{res2['total']} "
          f"skipped={len(res2['skipped'])}")


if __name__ == "__main__":
    demo_inspect()
    demo_capacity()
    demo_smart_wrap()
    demo_themes()
    demo_variations()
    demo_diff()
    demo_bulk_apply()
    demo_audit()
    demo_incremental_export()
    print("\n" + "═" * 60)
    print(" DONE")
    print("═" * 60)
