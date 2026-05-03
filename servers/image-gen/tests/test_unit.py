"""Tests unitaires des modules purs (safe, models, dimensions, cache, prompt_enhancer)."""
from __future__ import annotations

import json
import pytest


# =============================================================================
# safe_filename / safe_image_id
# =============================================================================

class TestSafeFilename:
    @pytest.mark.parametrize("name", ["photo.png", "image.jpg", "Image-File.WEBP"])
    def test_valid_passes(self, safe_module, name):
        assert safe_module.safe_filename(name) == name

    @pytest.mark.parametrize("name", [
        "../etc/passwd", "..foo.png", "/abs/path", "sub/file.png",
        "win\\path.png", ".hidden", "", None, 42, [],
    ])
    def test_invalid_rejected(self, safe_module, name):
        assert safe_module.safe_filename(name) == ""


class TestSafeImageId:
    @pytest.mark.parametrize("vid", [
        "abc12345", "abc12345def67890",
        "0000000000000000000000000000000a",  # 32 hex
    ])
    def test_valid_hex(self, safe_module, vid):
        assert safe_module.safe_image_id(vid) == vid.lower()

    @pytest.mark.parametrize("inv", ["xyz", "abc", "ABC123" * 10, "../etc", ""])
    def test_invalid(self, safe_module, inv):
        assert safe_module.safe_image_id(inv) == ""


# =============================================================================
# Models registry
# =============================================================================

class TestModels:
    def test_all_models_have_required_keys(self, models_module):
        required = {"id", "description", "ratios", "resolution_type",
                    "resolution_default", "supports_image_input",
                    "supports_text_to_image", "pricing"}
        for key, m in models_module.MODELS.items():
            missing = required - set(m.keys())
            assert not missing, f"{key} manque {missing}"

    def test_resolution_type_is_valid(self, models_module):
        for key, m in models_module.MODELS.items():
            assert m["resolution_type"] in ("pixels", "quality", "size"), key

    def test_estimate_cost_for_each_model(self, models_module):
        for key in models_module.MODELS:
            cost = models_module.estimate_cost(key)
            assert cost > 0, f"{key} a un coût nul"
            assert cost < 1, f"{key} a un coût > $1 (suspect)"

    def test_estimate_cost_quality_levels(self, models_module):
        # gpt-image-2 doit avoir 4 niveaux distincts
        low = models_module.estimate_cost("gpt-image-2", "low")
        med = models_module.estimate_cost("gpt-image-2", "medium")
        high = models_module.estimate_cost("gpt-image-2", "high")
        assert low < med < high

    def test_seedream_45_size_pricing(self, models_module):
        # 1K < 2K < 4K
        c1 = models_module.estimate_cost("seedream-4.5", 1024)
        c2 = models_module.estimate_cost("seedream-4.5", 2048)
        c4 = models_module.estimate_cost("seedream-4.5", 4096)
        assert c1 < c2 < c4

    def test_get_model_id_known(self, models_module):
        assert models_module.get_model_id("gpt-image-2") == "openai/gpt-image-2"
        assert models_module.get_model_id("flux-pro") == "black-forest-labs/flux-1.1-pro"

    def test_get_model_id_unknown_raises(self, models_module):
        with pytest.raises(ValueError):
            models_module.get_model_id("not-a-real-model")

    def test_specialized_models_are_separate(self, models_module):
        # Doivent exister
        assert "upscale_clarity" in models_module.SPECIALIZED_MODELS
        assert "background_remove" in models_module.SPECIALIZED_MODELS
        # Mais pas dans les MODELS user-facing
        assert "upscale_clarity" not in models_module.MODELS

    def test_list_user_models_excludes_specialized(self, models_module):
        user_models = models_module.list_user_models()
        keys = [m["key"] for m in user_models]
        assert "upscale_clarity" not in keys
        assert "gpt-image-2" in keys


# =============================================================================
# Dimensions
# =============================================================================

class TestDimensions:
    @pytest.mark.parametrize("orient, expected", [
        ("square", (1, 1)),
        ("landscape_3_2", (3, 2)),
        ("landscape_16_9", (16, 9)),
        ("portrait_2_3", (2, 3)),
    ])
    def test_resolve_aspect(self, dimensions_module, orient, expected):
        assert dimensions_module.resolve_target_aspect(orient, 100, 100) == expected

    def test_auto_uses_source(self, dimensions_module):
        assert dimensions_module.resolve_target_aspect("auto", 1920, 1080) == (1920, 1080)

    @pytest.mark.parametrize("orient, expected", [
        ("square", "1:1"),
        ("landscape_3_2", "3:2"),
        ("portrait_2_3", "2:3"),
    ])
    def test_gpt_image_2_explicit(self, dimensions_module, orient, expected):
        assert dimensions_module.gpt_image_2_aspect(orient, 100, 100) == expected

    def test_gpt_image_2_auto_landscape(self, dimensions_module):
        assert dimensions_module.gpt_image_2_aspect("auto", 1920, 1080) == "3:2"

    def test_compute_dimensions_multiples_of_8(self, dimensions_module):
        for orient in ["landscape_3_2", "portrait_9_16", "landscape_16_9"]:
            w, h = dimensions_module.compute_dimensions(orient, 2000, 100, 100)
            assert w % 8 == 0
            assert h % 8 == 0
            assert w >= 64
            assert h >= 64

    def test_seedream_size_label(self, dimensions_module):
        assert dimensions_module.seedream_size_label(1024) == "1K"
        assert dimensions_module.seedream_size_label(2048) == "2K"
        assert dimensions_module.seedream_size_label(4096) == "4K"

    def test_parse_max_resolution_int(self, dimensions_module):
        px, q = dimensions_module.parse_max_resolution("2000")
        assert px == 2000
        assert q == "medium"

    @pytest.mark.parametrize("q", ["low", "medium", "high", "auto"])
    def test_parse_max_resolution_quality(self, dimensions_module, q):
        _, qq = dimensions_module.parse_max_resolution(q)
        assert qq == q


# =============================================================================
# Cache
# =============================================================================

class TestCache:
    def test_save_and_retrieve(self, sandbox, cache_module):
        png_bytes = sandbox["fake_png"]
        image_id = cache_module.save_image(png_bytes, metadata={"prompt": "test"})
        assert len(image_id) == 16  # 16 hex chars
        # Retrieve
        path = cache_module.get_image_path(image_id)
        assert path is not None
        assert path.exists()
        assert path.read_bytes() == png_bytes
        # Metadata
        meta = cache_module.get_metadata(image_id)
        assert meta["prompt"] == "test"
        assert meta["image_id"] == image_id
        assert meta["hit_count"] == 1

    def test_save_same_bytes_increments_hit_count(self, sandbox, cache_module):
        png_bytes = sandbox["fake_png"]
        id1 = cache_module.save_image(png_bytes, metadata={"prompt": "first"})
        id2 = cache_module.save_image(png_bytes, metadata={"prompt": "second"})
        assert id1 == id2
        meta = cache_module.get_metadata(id1)
        assert meta["hit_count"] == 2

    def test_delete(self, sandbox, cache_module):
        image_id = cache_module.save_image(sandbox["fake_png"], metadata={})
        assert cache_module.delete_image(image_id) is True
        assert cache_module.get_image_path(image_id) is None
        assert cache_module.delete_image(image_id) is False  # déjà supprimé

    def test_delete_invalid_id(self, sandbox, cache_module):
        assert cache_module.delete_image("../etc/passwd") is False
        assert cache_module.delete_image("not-hex!") is False

    def test_list_images_recent_first(self, sandbox, cache_module):
        # Ajout dans un ordre, attente brève pour différents timestamps
        import time
        ids = []
        for i in range(3):
            from PIL import Image
            import io
            buf = io.BytesIO()
            Image.new("RGB", (16, 16), (i * 50, 0, 0)).save(buf, "PNG")
            ids.append(cache_module.save_image(buf.getvalue(), metadata={"prompt": f"img{i}"}))
            time.sleep(0.01)
        items = cache_module.list_images(limit=10)
        assert len(items) == 3
        # Le plus récent en premier
        assert items[0]["prompt"] == "img2"
        assert items[2]["prompt"] == "img0"

    def test_log_cost_and_summary(self, sandbox, cache_module):
        cache_module.log_cost("gpt-image-2", 0.053, "test prompt", "abc12345")
        cache_module.log_cost("flux-pro", 0.040, "another", "def67890")
        cache_module.log_cost("gpt-image-2", 0.211, "high quality", "ghijklmn")
        s = cache_module.get_cost_summary()
        assert s["count"] == 3
        assert abs(s["total_usd"] - (0.053 + 0.040 + 0.211)) < 0.001
        assert "gpt-image-2" in s["by_model"]
        assert s["by_model"]["gpt-image-2"] == round(0.053 + 0.211, 4)


# =============================================================================
# Prompt Enhancer
# =============================================================================

class TestPromptEnhancer:
    def test_short_prompt_enriched(self, prompt_enhancer_module):
        result = prompt_enhancer_module.enhance_prompt("a cat", enhance=True)
        assert len(result) > len("a cat")
        assert "professional" in result

    def test_long_prompt_unchanged(self, prompt_enhancer_module):
        long = "a serene mountain landscape at golden hour with mist rising from a lake, photographed with a wide angle lens"
        assert prompt_enhancer_module.enhance_prompt(long, enhance=True) == long

    def test_already_styled_prompt_unchanged(self, prompt_enhancer_module):
        styled = "a cat, photography style"
        assert prompt_enhancer_module.enhance_prompt(styled, enhance=True) == styled

    def test_disabled_returns_as_is(self, prompt_enhancer_module):
        assert prompt_enhancer_module.enhance_prompt("a cat", enhance=False) == "a cat"

    def test_empty_prompt(self, prompt_enhancer_module):
        assert prompt_enhancer_module.enhance_prompt("", enhance=True) == ""
