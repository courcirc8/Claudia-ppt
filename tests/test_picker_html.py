"""Smoke tests for picker.html — JS parses, DOM IDs present, structure intact."""
from __future__ import annotations
import json
import re
import subprocess
from pathlib import Path

import pytest

TOOL_ROOT = Path(__file__).resolve().parent.parent
PICKER = TOOL_ROOT / "picker" / "picker.html"
THEMES_JSON = TOOL_ROOT / "picker" / "themes.json"
PROJ = TOOL_ROOT  # alias for backwards compat in TestImageStyleSamples


@pytest.fixture(scope="module")
def html():
    return PICKER.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def js(html):
    m = re.search(r"<script>(.*?)</script>", html, re.DOTALL)
    assert m, "no <script> block found"
    return m.group(1)


class TestStructure:
    def test_picker_exists(self):
        assert PICKER.exists()
        assert PICKER.stat().st_size > 1000

    def test_themes_json_valid(self):
        data = json.loads(THEMES_JSON.read_text())
        assert "themes" in data
        assert len(data["themes"]) >= 6

    def test_doctype(self, html):
        assert html.lstrip().lower().startswith("<!doctype html>")

    def test_french_lang(self, html):
        assert 'lang="fr"' in html


class TestRequiredDomIds:
    """All IDs the JS expects to find must exist in the HTML."""

    REQUIRED_IDS = [
        # Tabs (5 panels)
        "panel-styles", "panel-palettes", "panel-customs", "panel-slides", "panel-generation",
        "styles-list", "palettes-list", "font-pairs",
        "density-options", "ratio-options", "image-style-options",
        # Bottom bar
        "slide-cover", "slide-content",
        "cover-eyebrow", "cover-title", "cover-sub", "cover-img", "cover-badge", "cover-label",
        "content-title", "content-img", "content-body", "content-badge", "content-label",
        "sum-style", "sum-palette", "sum-font",
        # Tab 4 — Slides editor
        "slides-editor", "slides-edited-count", "slides-mod-count",
        "slides-expand-all-btn", "slides-collapse-all-btn", "slides-reset-btn",
        # Tab 5 — Generation
        "recap-rows", "flow-filename", "code-preview",
        "gen-md-btn", "copy-cmd-btn", "dl-json-btn",
        "gen-stats-images", "gen-stats-cost", "gen-cost-detail",
        # Status banner (live polling)
        "status-banner", "worker-status", "worker-meta", "worker-refresh-btn",
        # Presets
        "preset-select", "preset-name", "preset-save-btn",
        # Actions
        "export-btn", "reset-btn", "toast", "meta-date",
    ]

    @pytest.mark.parametrize("id_", REQUIRED_IDS)
    def test_id_present(self, html, id_):
        assert f'id="{id_}"' in html, f'Missing id="{id_}"'


class TestJsParse:
    def test_node_parses_js(self, js):
        """Use node's Function constructor to validate JS syntax."""
        result = subprocess.run(
            ["node", "-e", "new Function(require('fs').readFileSync('/dev/stdin', 'utf8'))"],
            input=js, capture_output=True, text=True,
        )
        assert result.returncode == 0, f"JS parse failed: {result.stderr}"

    def test_brackets_balanced(self, js):
        for o, c in [("{", "}"), ("(", ")"), ("[", "]")]:
            assert js.count(o) == js.count(c), f"Unbalanced {o}{c}"

    def test_no_console_log(self, js):
        # Production code shouldn't ship with debug console.log
        # (allow console.warn/error for genuine warnings)
        bad = re.findall(r"\bconsole\.log\b", js)
        assert not bad, f"Found {len(bad)} console.log — remove for production"


class TestDataDeclarations:
    def test_styles_count(self, js):
        # const STYLES = [ {...}, {...}, ... ]
        # Count top-level entries by looking for `id: "..."` inside STYLES block
        m = re.search(r"const STYLES = \[(.*?)\];", js, re.DOTALL)
        assert m
        ids = re.findall(r'id:\s*"(\w+)"', m.group(1))
        assert len(ids) == 6, f"Expected 6 styles, got {len(ids)}: {ids}"

    def test_palettes_count(self, js):
        m = re.search(r"const PALETTES = \[(.*?)\];", js, re.DOTALL)
        assert m
        ids = re.findall(r'id:\s*"(\w+)"', m.group(1))
        assert len(ids) == 7, f"Expected 7 palette presets, got {len(ids)}: {ids}"

    def test_font_pairs_count(self, js):
        m = re.search(r"const FONT_PAIRS = \[(.*?)\];", js, re.DOTALL)
        assert m
        ids = re.findall(r'id:\s*"(\w+)"', m.group(1))
        assert len(ids) >= 4

    def test_image_styles_have_samples(self, js):
        m = re.search(r"const IMG_STYLES = \[(.*?)\];", js, re.DOTALL)
        assert m
        block = m.group(1)
        for sid in ("illustrated", "photo", "abstract"):
            assert f'id: "{sid}"' in block
            # Each must have a sample path
            sample_pattern = rf'id: "{sid}".*?sample: "([^"]+)"'
            sm = re.search(sample_pattern, block, re.DOTALL)
            assert sm, f"{sid} has no sample"
            sample_path = TOOL_ROOT / "picker" / sm.group(1)
            assert sample_path.exists(), f"sample missing on disk: {sample_path}"


class TestSamples:
    def test_all_theme_samples_exist(self):
        data = json.loads(THEMES_JSON.read_text())
        for theme in data["themes"]:
            sp = TOOL_ROOT / "picker" / theme["sample"]
            assert sp.exists(), f"theme sample missing: {sp}"
            assert sp.stat().st_size > 1000

    def test_image_style_samples_exist(self):
        for name in ("illustrated", "photo", "abstract"):
            sp = TOOL_ROOT / "picker" / "samples" / "styles" / f"{name}.png"
            assert sp.exists(), f"style sample missing: {sp}"


class TestFunctionsDefined:
    REQUIRED_FUNCS = [
        "renderStyles", "renderPalettes", "renderCustoms",
        "renderGeneration", "renderBottomBar", "renderAll",
        "buildBrief", "downloadBriefMd", "copyClaudeCommand",
        "downloadJsonConfig", "updateCustomSwatch", "loadState",
        "textOn", "fmtDate", "nuancier", "toast",
        # New (slides editor)
        "renderSlides", "getSlides", "isSlideEdited", "escapeHtml",
        # New (presets)
        "loadPresets", "savePresets", "renderPresets",
        "loadPreset", "savePresetCurrent", "deletePreset",
        # New (cost)
        "computeCost", "renderCost",
        # New (polling)
        "startPolling", "stopPolling", "pollOnce",
    ]

    @pytest.mark.parametrize("fn", REQUIRED_FUNCS)
    def test_function_defined(self, js, fn):
        # match `function name(` or `const name = ` or `let name = `
        pattern = rf"(?:function\s+{fn}\s*\(|(?:const|let|var)\s+{fn}\s*=)"
        assert re.search(pattern, js), f"Function/var {fn} not defined"


class TestDefaultSlides:
    """The DEFAULT_SLIDES array drives Tab 4's editor. Must have 10 slides
    with non-empty title and body."""

    @pytest.fixture
    def default_slides_block(self, js):
        m = re.search(r"const DEFAULT_SLIDES = \[(.*?)\];", js, re.DOTALL)
        assert m, "DEFAULT_SLIDES not declared"
        return m.group(1)

    def test_ten_slides(self, default_slides_block):
        # Each slide entry has `idx: <n>`. Count those.
        idxs = re.findall(r"idx:\s*(\d+)", default_slides_block)
        assert len(idxs) == 10, f"Expected 10 slides, got {len(idxs)}"
        assert sorted(int(i) for i in idxs) == list(range(10))

    def test_each_slide_has_title_and_body(self, default_slides_block):
        title_count = len(re.findall(r"title:\s*\"", default_slides_block))
        body_count = len(re.findall(r"body:\s*\"", default_slides_block))
        assert title_count == 10
        assert body_count == 10

    def test_first_is_cover(self, default_slides_block):
        # First entry should have role: "cover"
        first = default_slides_block.split("},")[0]
        assert 'role: "cover"' in first

    def test_last_is_closing(self, default_slides_block):
        # Find the entry with idx: 9
        m = re.search(r"\{[^{}]*idx:\s*9[^{}]*\}", default_slides_block, re.DOTALL)
        assert m, "Slide with idx=9 not found"
        assert 'role: "closing"' in m.group(0)


class TestImgStyleCostMetadata:
    """Each IMG_STYLE must declare model + cost_per_img for the cost estimator."""

    @pytest.fixture
    def img_styles_block(self, js):
        m = re.search(r"const IMG_STYLES = \[(.*?)\];", js, re.DOTALL)
        assert m
        return m.group(1)

    def test_each_has_model_field(self, img_styles_block):
        # 3 styles, each with `model: "..."`
        models = re.findall(r'model:\s*"([^"]+)"', img_styles_block)
        assert len(models) == 3

    def test_each_has_cost_field(self, img_styles_block):
        costs = re.findall(r"cost_per_img:\s*([\d.]+)", img_styles_block)
        assert len(costs) == 3
        for c in costs:
            assert 0.01 < float(c) < 0.20, f"Cost {c} unrealistic"


class TestStateExtensions:
    """State must include slides + open_slides + custom_palette."""

    def test_initial_state_has_new_fields(self, js):
        m = re.search(r"const initialState = \{(.*?)\};", js, re.DOTALL)
        assert m
        block = m.group(1)
        for field in ("slides:", "open_slides:", "custom_palette:", "image_style:"):
            assert field in block, f"initialState missing {field}"

    def test_presets_storage_key_defined(self, js):
        assert 'PRESETS_KEY = "df_atelier_presets"' in js or "PRESETS_KEY=" in js


# Run with: pytest tests/test_picker_html.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
