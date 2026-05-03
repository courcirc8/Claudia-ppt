"""Tests pour la sélection automatique de modèle."""
from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def selector():
    import model_selector
    return model_selector


# =============================================================================
# Score heuristique
# =============================================================================

class TestScoreComplexity:
    @pytest.mark.parametrize("prompt", [
        "a cat",
        "sunset over mountains",
        "modern living room with view on lake",
        "minimalist fish illustration",
        "a portrait of a woman",
    ])
    def test_simple_visual_prompts_low_score(self, selector, prompt):
        assert selector.score_complexity(prompt) < 2

    @pytest.mark.parametrize("prompt", [
        "infographic showing climate change data",
        "diagram of solar system with labels",
        "chart with text annotations",
        "pie chart showing market share",
        "table with headers and rows",
        "logo with text 'Acme Corp' on white background",
    ])
    def test_text_keywords_high_score(self, selector, prompt):
        assert selector.score_complexity(prompt) >= 2

    def test_french_keywords_detected(self, selector):
        assert selector.score_complexity("infographie sur le climat") >= 2
        assert selector.score_complexity("diagramme avec titre et texte") >= 2

    def test_long_detailed_prompt_increases_score(self, selector):
        short = "a cat in a garden"
        long_ = (
            "a photorealistic portrait of an elderly woman, her face shows years "
            "of experience, soft natural lighting from the left, shallow depth of "
            "field, professional photography, the background is a blurred forest "
            "with autumn colors, mood is contemplative and peaceful, captured "
            "with a 85mm lens at f/1.4, golden hour"
        )
        assert selector.score_complexity(long_) > selector.score_complexity(short)

    def test_constraint_keywords_increase_score(self, selector):
        assert selector.score_complexity("preserve the original face exactly") >= 2
        assert selector.score_complexity("doit contenir trois éléments précis") >= 2

    def test_layout_keywords_alone_dont_bump(self, selector):
        """Layout sans contenu texte ne suffit pas pour router vers gpt-image-2.
        C'est volontaire : 'grid', 'bullet' peuvent être des illustrations
        décoratives sans texte. Le score reste >= 1 (signal détecté) mais < 2."""
        s = selector.score_complexity("grid layout with bullet points")
        assert s >= 1
        assert s < 2

    def test_layout_with_text_routes_to_gpt(self, selector):
        """Layout + texte explicite → score >= 2 → gpt-image-2."""
        s = selector.score_complexity("grid layout with text labels in each cell")
        assert s >= 2


# =============================================================================
# Auto-select model
# =============================================================================

class TestAutoSelectModel:
    @pytest.mark.parametrize("prompt", [
        "a cat in a garden",
        "sunset over Lake Geneva",
        "cozy living room",
        "minimalist fish illustration",
        "vintage car on a country road",
    ])
    def test_visual_prompts_route_to_seedream(self, selector, prompt):
        model, reason = selector.auto_select_model(prompt)
        assert model == "seedream-4.5"
        assert "simple" in reason

    @pytest.mark.parametrize("prompt", [
        "infographic showing market share with labels",
        "diagram of the human heart with annotations",
        "chart comparing three products with text headers",
        "logo with text 'Acme' on white background",
        "schema of a database with table columns",
    ])
    def test_text_prompts_route_to_gpt_image_2(self, selector, prompt):
        model, reason = selector.auto_select_model(prompt)
        assert model == "gpt-image-2"
        assert "complexe" in reason or "complex" in reason.lower()

    def test_returns_tuple_of_strings(self, selector):
        model, reason = selector.auto_select_model("test")
        assert isinstance(model, str)
        assert isinstance(reason, str)
        assert len(reason) > 0


# =============================================================================
# Quality selection per role
# =============================================================================

class TestAutoSelectQualityForRole:
    @pytest.mark.parametrize("role", ["cover", "infographic"])
    def test_high_for_critical_roles(self, selector, role):
        assert selector.auto_select_quality_for_role(role) == "high"

    @pytest.mark.parametrize("role", ["icon", "photo", "background", "headshot",
                                       "section", "illustration", None])
    def test_medium_for_other_roles(self, selector, role):
        assert selector.auto_select_quality_for_role(role) == "medium"


# =============================================================================
# Intégration : generate_image avec model='auto'
# =============================================================================

class TestAutoModeIntegration:
    def test_auto_mode_picks_seedream_for_visual(self, sandbox):
        from tools.generate import generate_image
        result = generate_image("a cat in a garden", model="auto")
        assert result["model"] == "seedream-4.5"
        assert "auto_select_reason" in result

    def test_auto_mode_picks_gpt_for_text(self, sandbox):
        from tools.generate import generate_image
        result = generate_image(
            "infographic with text labels showing market data",
            model="auto",
        )
        assert result["model"] == "gpt-image-2"
        assert "auto_select_reason" in result

    def test_explicit_model_skips_auto(self, sandbox):
        from tools.generate import generate_image
        result = generate_image("a cat", model="flux-pro")
        assert result["model"] == "flux-pro"
        # Pas de raison auto puisque l'utilisateur a explicité
        assert "auto_select_reason" not in result


# =============================================================================
# Intégration : image_to_image défaut gpt-image-2 + ref image
# =============================================================================

class TestImageToImageDefaults:
    def test_default_model_is_gpt_image_2(self, sandbox):
        """Par défaut image_to_image utilise gpt-image-2 (édition précise)."""
        from tools.generate import image_to_image
        import cache
        src_id = cache.save_image(sandbox["fake_png"], metadata={})
        result = image_to_image(src_id, "make it brighter")
        assert result["model"] == "gpt-image-2"

    def test_source_image_passed_as_reference(self, sandbox):
        """L'image source DOIT être passée en input_images au modèle."""
        from tools.generate import image_to_image
        import cache
        src_id = cache.save_image(sandbox["fake_png"], metadata={})
        image_to_image(src_id, "edit this")
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "input_images" in api_input
        assert len(api_input["input_images"]) == 1


class TestReplaceBackgroundDefaults:
    def test_uses_gpt_image_2(self, sandbox):
        """replace_background utilise gpt-image-2 pour préserver le sujet."""
        from tools.edit import replace_background
        import cache
        src_id = cache.save_image(sandbox["fake_png"], metadata={})
        result = replace_background(src_id, "white studio")
        # Le coût correspond à gpt-image-2 medium ($0.053)
        assert result["cost_usd"] == 0.053

    def test_source_image_in_input_images(self, sandbox):
        from tools.edit import replace_background
        import cache
        src_id = cache.save_image(sandbox["fake_png"], metadata={})
        replace_background(src_id, "white studio")
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "input_images" in api_input
        assert len(api_input["input_images"]) == 1
