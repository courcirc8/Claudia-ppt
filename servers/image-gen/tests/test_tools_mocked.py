"""Tests d'intégration mockés des 19 outils — zéro appel réseau."""
from __future__ import annotations

import base64
import io
import json
import pytest
from PIL import Image


# =============================================================================
# Fixture : ID factice d'une image dans le cache (pour les outils qui en exigent)
# =============================================================================

@pytest.fixture
def cached_image_id(sandbox):
    """Crée une image dans le cache et retourne son ID."""
    import cache
    return cache.save_image(
        sandbox["fake_png"],
        metadata={"prompt": "fixture", "operation": "fixture"},
    )


# =============================================================================
# generate.py
# =============================================================================

class TestGenerateImage:
    def test_basic_call(self, sandbox):
        from tools.generate import generate_image
        result = generate_image("a cat", model="gpt-image-2")
        assert "image_id" in result
        assert result["model"] == "gpt-image-2"
        assert result["cost_usd"] == 0.053  # medium par défaut
        assert sandbox["call_replicate"].called

    def test_passes_correct_model_id(self, sandbox):
        from tools.generate import generate_image
        generate_image("a dog", model="flux-pro")
        call_args = sandbox["call_replicate"].call_args
        assert call_args.args[0] == "black-forest-labs/flux-1.1-pro"

    @pytest.mark.parametrize("orient, expected_aspect", [
        ("square", "1:1"),
        ("landscape_3_2", "3:2"),
        ("portrait_2_3", "2:3"),
    ])
    def test_gpt_image_2_orientation(self, sandbox, orient, expected_aspect):
        from tools.generate import generate_image
        generate_image("subject", model="gpt-image-2", orientation=orient)
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert api_input["aspect_ratio"] == expected_aspect

    @pytest.mark.parametrize("q", ["low", "medium", "high", "auto"])
    def test_quality_propagated(self, sandbox, q):
        from tools.generate import generate_image
        generate_image("subject", model="gpt-image-2", max_resolution=q)
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert api_input["quality"] == q

    def test_seedream_45_size_enum(self, sandbox):
        from tools.generate import generate_image
        generate_image("subject", model="seedream-4.5", max_resolution=4096)
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert api_input["size"] == "4K"

    def test_unknown_model_raises(self, sandbox):
        from tools.generate import generate_image
        with pytest.raises(ValueError, match="Modèle inconnu"):
            generate_image("test", model="not-a-real-model")

    def test_empty_prompt_raises(self, sandbox):
        from tools.generate import generate_image
        with pytest.raises(ValueError):
            generate_image("", model="gpt-image-2")

    def test_nano_banana_text_to_image_blocked(self, sandbox):
        # nano-banana ne supporte pas text-to-image (que image-to-image)
        from tools.generate import generate_image
        with pytest.raises(ValueError, match="ne supporte pas"):
            generate_image("test", model="nano-banana")

    def test_flux_pro_uses_width_height(self, sandbox):
        from tools.generate import generate_image
        generate_image("test", model="flux-pro", orientation="landscape_3_2", max_resolution=2000)
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "width" in api_input
        assert "height" in api_input
        assert api_input["width"] == 2000

    def test_metadata_persisted(self, sandbox):
        from tools.generate import generate_image
        import cache
        result = generate_image("specific test prompt", model="gpt-image-2")
        meta = cache.get_metadata(result["image_id"])
        assert meta["prompt"] == "specific test prompt"
        assert meta["model"] == "gpt-image-2"
        assert meta["operation"] == "generate_image"

    def test_cost_logged(self, sandbox):
        from tools.generate import generate_image
        import cache
        generate_image("test", model="flux-pro")
        summary = cache.get_cost_summary()
        assert summary["count"] >= 1
        assert "flux-pro" in summary["by_model"]


class TestImageToImage:
    def test_with_cached_source(self, sandbox, cached_image_id):
        from tools.generate import image_to_image
        result = image_to_image(cached_image_id, "make it blue", model="gpt-image-2")
        assert result["source_image_id"] == cached_image_id
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "input_images" in api_input  # gpt-image-2 utilise input_images

    def test_invalid_image_id(self, sandbox):
        from tools.generate import image_to_image
        with pytest.raises(ValueError, match="invalide"):
            image_to_image("../etc/passwd", "test", model="gpt-image-2")

    def test_inexistent_image_id(self, sandbox):
        from tools.generate import image_to_image
        with pytest.raises(ValueError, match="introuvable"):
            image_to_image("0123456789abcdef", "test", model="gpt-image-2")


class TestGenerateBatch:
    def test_batch_3_images(self, sandbox):
        from tools.generate import generate_batch
        result = generate_batch(["cover", "slide 1", "slide 2"], model="seedream-4.5")
        assert len(result["images"]) == 3
        assert result["count"] == 3
        assert result["total_cost_usd"] > 0
        assert sandbox["call_replicate"].call_count == 3

    def test_with_style_ref(self, sandbox, cached_image_id):
        from tools.generate import generate_batch
        result = generate_batch(
            ["a", "b"],
            model="gpt-image-2",
            style_ref_image_id=cached_image_id,
        )
        # Le style_ref doit être passé dans chaque appel
        for call in sandbox["call_replicate"].call_args_list:
            api_input = call.args[1]
            assert "input_images" in api_input
            assert len(api_input["input_images"]) == 1  # juste la ref (pas de source)

    def test_empty_prompts_list(self, sandbox):
        from tools.generate import generate_batch
        with pytest.raises(ValueError):
            generate_batch([], model="gpt-image-2")

    def test_too_many_prompts(self, sandbox):
        from tools.generate import generate_batch
        with pytest.raises(ValueError, match="Maximum"):
            generate_batch(["x"] * 25, model="gpt-image-2")


class TestGenerateForSlide:
    def test_cover_role(self, sandbox):
        from tools.slide import generate_for_slide
        result = generate_for_slide(role="cover", prompt="climate change")
        assert result["slide_role"] == "cover"
        assert result["model"] == "gpt-image-2"
        # Cover est high quality
        assert result["cost_usd"] == 0.211

    def test_icon_role(self, sandbox):
        from tools.slide import generate_for_slide
        result = generate_for_slide(role="icon", prompt="fish")
        assert result["slide_role"] == "icon"
        # Icon est square 1:1
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert api_input["aspect_ratio"] == "1:1"

    def test_unknown_role_raises(self, sandbox):
        from tools.slide import generate_for_slide
        with pytest.raises(ValueError, match="role inconnu"):
            generate_for_slide(role="not-a-role", prompt="x")

    def test_all_roles_callable(self, sandbox):
        from tools.slide import generate_for_slide, SLIDE_ROLE_PRESETS
        for role in SLIDE_ROLE_PRESETS:
            result = generate_for_slide(role=role, prompt="test")
            assert result["slide_role"] == role


class TestGenerateImageFree:
    def test_pollinations_call(self, monkeypatch, sandbox):
        """Mock httpx.Client pour ne pas faire de vrai appel Pollinations."""
        from unittest.mock import MagicMock
        import httpx
        import tools.free as free_module

        fake_response = MagicMock()
        fake_response.content = sandbox["fake_png"]
        fake_response.raise_for_status = MagicMock()

        fake_client = MagicMock()
        fake_client.__enter__ = MagicMock(return_value=fake_client)
        fake_client.__exit__ = MagicMock(return_value=None)
        fake_client.get = MagicMock(return_value=fake_response)

        monkeypatch.setattr(httpx, "Client", lambda **kw: fake_client)

        result = free_module.generate_image_free("a cat")
        assert result["cost_usd"] == 0.0
        assert result["model"] == "pollinations-flux"
        assert "image_id" in result

    def test_invalid_dimensions(self, sandbox):
        from tools.free import generate_image_free
        with pytest.raises(ValueError):
            generate_image_free("test", width=10, height=10)

    def test_invalid_model(self, sandbox):
        from tools.free import generate_image_free
        with pytest.raises(ValueError):
            generate_image_free("test", model="invalid")


# =============================================================================
# edit.py
# =============================================================================

class TestInpaint:
    def test_basic(self, sandbox, cached_image_id):
        from tools.edit import inpaint
        # Créer un mask en base64
        mask = Image.new("L", (16, 16), 255)
        buf = io.BytesIO()
        mask.save(buf, "PNG")
        mask_b64 = base64.b64encode(buf.getvalue()).decode()

        result = inpaint(cached_image_id, mask_b64, "fill with sky")
        assert "image_id" in result
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "mask" in api_input
        assert "input_images" in api_input

    def test_data_uri_prefix_stripped(self, sandbox, cached_image_id):
        from tools.edit import inpaint
        mask = Image.new("L", (16, 16), 255)
        buf = io.BytesIO()
        mask.save(buf, "PNG")
        mask_b64 = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
        # Ne doit pas planter
        inpaint(cached_image_id, mask_b64, "test")


class TestReplaceBackground:
    def test_basic(self, sandbox, cached_image_id):
        from tools.edit import replace_background
        result = replace_background(cached_image_id, "white studio")
        assert result["source_image_id"] == cached_image_id
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "PRESERVE the subject" in api_input["prompt"]
        assert "white studio" in api_input["prompt"]


class TestOutpaint:
    @pytest.mark.parametrize("direction", ["top", "right", "bottom", "left", "all"])
    def test_directions(self, sandbox, cached_image_id, direction):
        from tools.edit import outpaint
        result = outpaint(cached_image_id, direction=direction, pixels=64)
        assert "image_id" in result

    def test_invalid_direction(self, sandbox, cached_image_id):
        from tools.edit import outpaint
        with pytest.raises(ValueError):
            outpaint(cached_image_id, direction="diagonal")


class TestRegisterImage:
    def test_register_from_file(self, sandbox, tmp_path):
        from tools.edit import register_image
        # Créer un PNG temporaire
        path = tmp_path / "user.png"
        Image.new("RGB", (50, 50), "red").save(path, "PNG")
        result = register_image(file_path=str(path))
        assert result["width"] == 50
        assert result["height"] == 50
        assert "image_id" in result

    def test_register_from_base64(self, sandbox):
        from tools.edit import register_image
        b64 = base64.b64encode(sandbox["fake_png"]).decode()
        result = register_image(image_base64=b64)
        assert "image_id" in result

    def test_neither_provided_raises(self, sandbox):
        from tools.edit import register_image
        with pytest.raises(ValueError):
            register_image()

    def test_inexistent_file_raises(self, sandbox):
        from tools.edit import register_image
        with pytest.raises(ValueError, match="introuvable"):
            register_image(file_path="/tmp/__nope__.png")


# =============================================================================
# process.py
# =============================================================================

class TestRemoveBackground:
    def test_basic(self, sandbox, cached_image_id):
        from tools.process import remove_background
        result = remove_background(cached_image_id)
        assert result["source_image_id"] == cached_image_id
        # Doit avoir appelé le bon model_id
        call_args = sandbox["call_replicate"].call_args
        assert "background-remover" in call_args.args[0]


class TestUpscale:
    @pytest.mark.parametrize("factor", [2, 4])
    @pytest.mark.parametrize("mode", ["crisp", "creative"])
    def test_factors_and_modes(self, sandbox, cached_image_id, factor, mode):
        from tools.process import upscale
        result = upscale(cached_image_id, factor=factor, mode=mode)
        assert result["factor"] == factor
        assert result["mode"] == mode
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert api_input["scale_factor"] == factor

    def test_invalid_factor(self, sandbox, cached_image_id):
        from tools.process import upscale
        with pytest.raises(ValueError):
            upscale(cached_image_id, factor=3)

    def test_invalid_mode(self, sandbox, cached_image_id):
        from tools.process import upscale
        with pytest.raises(ValueError):
            upscale(cached_image_id, mode="ultra")


class TestVectorize:
    def test_basic(self, sandbox, cached_image_id):
        from tools.process import vectorize
        result = vectorize(cached_image_id)
        assert "image_id" in result
        assert "format" in result


class TestSeamlessTile:
    def test_no_replicate_call(self, sandbox, cached_image_id):
        from tools.process import seamless_tile
        prev_calls = sandbox["call_replicate"].call_count
        result = seamless_tile(cached_image_id)
        # Doit être 100% local
        assert sandbox["call_replicate"].call_count == prev_calls
        assert result["cost_usd"] == 0.0
        assert "image_id" in result


# =============================================================================
# manage.py
# =============================================================================

class TestManagement:
    def test_list_images_empty(self, sandbox):
        from tools.manage import list_images
        result = list_images()
        assert result["count"] == 0
        assert result["images"] == []

    def test_list_after_generate(self, sandbox):
        from tools.generate import generate_image
        from tools.manage import list_images
        generate_image("img1", model="gpt-image-2")
        generate_image("img2", model="flux-pro")
        result = list_images()
        assert result["count"] == 2

    def test_get_image_with_base64(self, sandbox, cached_image_id):
        from tools.manage import get_image
        result = get_image(cached_image_id, include_base64=True)
        assert result["success"] is True
        assert "base64" in result
        assert result["mime_type"] == "image/png"

    def test_get_image_invalid_id(self, sandbox):
        from tools.manage import get_image
        result = get_image("../etc/passwd")
        assert result["success"] is False
        assert "invalide" in result["message"].lower()

    def test_delete_image_works(self, sandbox, cached_image_id):
        from tools.manage import delete_image
        result = delete_image(cached_image_id)
        assert result["success"] is True

    def test_get_costs(self, sandbox):
        from tools.generate import generate_image
        from tools.manage import get_costs
        generate_image("test", model="flux-pro")
        costs = get_costs()
        assert costs["count"] >= 1
        assert costs["total_usd"] > 0


# =============================================================================
# style.py
# =============================================================================

class TestApplyStyle:
    def test_basic(self, sandbox, cached_image_id):
        from tools.style import apply_style
        result = apply_style(cached_image_id, "a different subject", model="seedream-4.5")
        assert result["style_ref_image_id"] == cached_image_id
        api_input = sandbox["call_replicate"].call_args.args[1]
        assert "image_input" in api_input
        # Le prompt doit mentionner "same visual style"
        assert "same visual style" in api_input["prompt"]

    def test_invalid_ref_id(self, sandbox):
        from tools.style import apply_style
        with pytest.raises(ValueError):
            apply_style("../etc/passwd", "test")

    def test_inexistent_ref_id(self, sandbox):
        from tools.style import apply_style
        with pytest.raises(ValueError, match="introuvable"):
            apply_style("0123456789abcdef", "test")


# =============================================================================
# Edge cases : Replicate retours
# =============================================================================

class TestReplicateOutputFormats:
    def test_list_response_handled(self, sandbox):
        from tools.generate import generate_image
        sandbox["call_replicate"].return_value = ["http://fake.test/result.png"]
        result = generate_image("test", model="seedream-4.5")
        assert "image_id" in result

    def test_fileoutput_response_handled(self, sandbox):
        from tools.generate import generate_image
        sandbox["call_replicate"].return_value = sandbox["FakeFileOutput"](
            "http://fake.test/result.png"
        )
        result = generate_image("test", model="gpt-image-2")
        assert "image_id" in result


# =============================================================================
# Workflows end-to-end
# =============================================================================

class TestPPTWorkflows:
    def test_workflow_icon_to_svg(self, sandbox):
        """Workflow PPT : générer icône → remove BG → vectorize."""
        from tools.slide import generate_for_slide
        from tools.process import remove_background, vectorize
        # Étape 1 : générer
        r1 = generate_for_slide(role="icon", prompt="fish")
        # Étape 2 : remove BG
        r2 = remove_background(r1["image_id"])
        # Étape 3 : vectorize
        r3 = vectorize(r2["image_id"])
        # Vérifs : 3 images créées dans le cache, lignées
        from tools.manage import list_images
        listing = list_images()
        # generate_for_slide + remove_bg + vectorize = 3 nouvelles
        assert listing["count"] >= 3

    def test_workflow_batch_with_style(self, sandbox):
        """Workflow : générer la cover, puis le batch avec son style."""
        from tools.generate import generate_image, generate_batch
        cover = generate_image("ocean cover", model="gpt-image-2")
        batch = generate_batch(
            ["slide 1", "slide 2", "slide 3"],
            model="seedream-4.5",
            style_ref_image_id=cover["image_id"],
        )
        assert batch["count"] == 3
        # Le total cost = 1 cover + 3 slides
        from tools.manage import get_costs
        c = get_costs()
        assert c["count"] >= 4
