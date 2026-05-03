"""Tests for atelier_worker — brief parsing and file routing."""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

PROJ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ / "atelier"))

import atelier_worker as worker

SAMPLE_BRIEF = """# Atelier — Brief de génération

- **Code**: ATL-A4F2
- **Date**: 2026-05-03T14:32:01Z
- **Projet**: droit_des_familles
- **Action**: build_pptx
- **Source URL**: https://droitdesfamilles.ch/campagne/2546

## Composition

### Style visuel
- id: `elegant_editorial`
- name: Élégant éditorial
- image_prompt: Editorial illustration with refined motifs

### Palette
- id: `pink_violet`
- name: Pink Violet
- colors:
  - primary: `#501464`
  - accent:  `#E8B4D2`
  - gold:    `#C9A96E`
  - text:    `#321E3C`
  - bg:      `#FCF8FD`
- gradient_cover: [`#3C1450`, `#C882B4`]

### Typographie
- display: Fraunces
- body: Inter

### Layout
- ratio: 16 / 9 (16x9)
- density: Normal (Body 22pt · 8 lignes)
- image_style: Illustrée (illustrated)
"""


class TestParseBrief:
    def test_extracts_code(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["code"] == "A4F2"

    def test_extracts_date(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["date"] == "2026-05-03T14:32:01Z"

    def test_extracts_action(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["action"] == "build_pptx"

    def test_extracts_style(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["style"]["id"] == "elegant_editorial"
        assert "Élégant" in spec["style"]["name"]

    def test_extracts_palette_id(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["palette"]["id"] == "pink_violet"

    def test_extracts_all_colors(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        colors = spec["palette"]["colors"]
        assert colors["primary"] == "#501464"
        assert colors["accent"] == "#E8B4D2"
        assert colors["gold"] == "#C9A96E"
        assert colors["text"] == "#321E3C"
        assert colors["bg"] == "#FCF8FD"

    def test_extracts_fonts(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert spec["font"]["display"] == "Fraunces"
        assert spec["font"]["body"] == "Inter"

    def test_extracts_layout(self):
        spec = worker.parse_brief(SAMPLE_BRIEF)
        assert "16" in spec["layout"]["ratio"]
        assert spec["layout"]["density"] == "Normal"
        assert spec["layout"]["image_style_id"] == "illustrated"

    def test_handles_missing_fields_gracefully(self):
        minimal = "# Brief\n- **Code**: ATL-ABCD\n"
        spec = worker.parse_brief(minimal)
        assert spec["code"] == "ABCD"
        # Other fields absent but no exception
        assert "layout" in spec

    def test_handles_completely_empty_brief(self):
        spec = worker.parse_brief("")
        assert "raw" in spec
        # Should not raise


class TestExecuteBrief:
    def test_returns_status_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(worker, "OUTBOX", tmp_path)
        spec = worker.parse_brief(SAMPLE_BRIEF)
        status = worker.execute_brief(spec)
        assert status["code"] == "A4F2"
        assert status["status"] == "AWAITING_LLM"
        assert "next" in status
        assert len(status["next"]) > 0

    def test_writes_in_progress_marker(self, tmp_path, monkeypatch):
        monkeypatch.setattr(worker, "OUTBOX", tmp_path)
        spec = worker.parse_brief(SAMPLE_BRIEF)
        worker.execute_brief(spec)
        assert (tmp_path / "A4F2.in_progress.md").exists()


class TestProcessBrief:
    def test_full_round_trip(self, tmp_path, monkeypatch):
        # Set up isolated dirs
        inbox = tmp_path / "inbox"
        outbox = tmp_path / "outbox"
        watch = tmp_path / "watch"
        watch.mkdir(); inbox.mkdir(); outbox.mkdir()
        monkeypatch.setattr(worker, "INBOX", inbox)
        monkeypatch.setattr(worker, "OUTBOX", outbox)
        monkeypatch.setattr(worker, "PROCESSED", tmp_path / "processed")

        # Drop a brief into watch dir
        brief_path = watch / "atelier-droit_des_familles-2026-05-03T14-32-01-A4F2.md"
        brief_path.write_text(SAMPLE_BRIEF)

        worker.process_brief(brief_path)

        # Brief moved to inbox with canonical name
        assert (inbox / "A4F2.md").exists()
        assert not brief_path.exists()  # moved out
        # Done file written
        assert (outbox / "A4F2.done.md").exists()
        # In_progress cleaned up
        assert not (outbox / "A4F2.in_progress.md").exists()


# Run with: pytest tests/test_atelier_worker.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
