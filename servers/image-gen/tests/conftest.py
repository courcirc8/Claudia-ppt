"""Fixtures partagées pour la suite de régression ImageGen."""
from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

# Ajouter le dossier parent au path pour pouvoir importer les modules
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# =============================================================================
# Helpers : modules
# =============================================================================

@pytest.fixture(scope="session")
def cache_module():
    import cache
    return cache


@pytest.fixture(scope="session")
def models_module():
    import models
    return models


@pytest.fixture(scope="session")
def safe_module():
    import safe
    return safe


@pytest.fixture(scope="session")
def dimensions_module():
    import dimensions
    return dimensions


@pytest.fixture(scope="session")
def prompt_enhancer_module():
    import prompt_enhancer
    return prompt_enhancer


# =============================================================================
# Sandbox : cache temporaire + mock Replicate
# =============================================================================

class _FakeFileOutput:
    """Imite l'objet FileOutput de Replicate (avec .url comme propriété)."""

    def __init__(self, url: str):
        self.url = url


def _tiny_png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), "white").save(buf, "PNG")
    return buf.getvalue()


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    """Sandbox d'intégration :
    - CACHE_DIR redirigé vers tmp_path
    - replicate.run mocké
    - requests.get mocké (renvoie un PNG factice)
    - REPLICATE_API_TOKEN défini avec valeur factice
    """
    import config
    import cache
    import replicate_client

    # Cache temporaire
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(config, "COSTS_PATH", tmp_path / "costs.jsonl")
    monkeypatch.setattr(cache, "config", config)

    # Sandbox d'upload : autoriser tmp_path pour register_image
    monkeypatch.setenv("IMAGE_GEN_UPLOAD_ROOT", str(tmp_path))
    # Pas de plafond de dépense pendant les tests
    monkeypatch.setattr(config, "MAX_DAILY_USD", 0.0)

    # Token factice (pour passer le require_replicate_token)
    monkeypatch.setattr(config, "REPLICATE_API_TOKEN", "r8_test_dummy_token")

    # Mock replicate.run via le client wrapper (seam unique)
    fake_url = "https://fake-replicate.test/result.png"
    mock_call = MagicMock(return_value=fake_url)
    monkeypatch.setattr(replicate_client, "call_replicate", mock_call)

    # Mock download_image — retourne un PNG différent à chaque appel pour que
    # le cache content-addressed génère des IDs distincts (sinon il déduplique)
    fake_png = _tiny_png_bytes()
    counter = {"n": 0}

    def _next_fake_png(*args, **kwargs):
        counter["n"] += 1
        # PNG unique par appel : on varie 1 pixel (la couleur)
        buf = io.BytesIO()
        Image.new("RGB", (16, 16), (counter["n"] % 256, 0, 0)).save(buf, "PNG")
        return buf.getvalue()

    mock_dl = MagicMock(side_effect=_next_fake_png)
    monkeypatch.setattr(replicate_client, "download_image", mock_dl)

    # Re-mocker dans les modules tools/ qui font `from replicate_client import ...`
    # (l'import a déjà figé la référence, donc il faut patcher chaque tool module)
    for mod_name in (
        "tools.generate", "tools.edit", "tools.process",
        "tools.style", "tools.free",
    ):
        try:
            __import__(mod_name)
            mod = sys.modules[mod_name]
            if hasattr(mod, "call_replicate"):
                monkeypatch.setattr(mod, "call_replicate", mock_call)
            if hasattr(mod, "download_image"):
                monkeypatch.setattr(mod, "download_image", mock_dl)
        except ImportError:
            pass

    return {
        "cache_dir": tmp_path,
        "call_replicate": mock_call,
        "download_image": mock_dl,
        "fake_png": fake_png,
        "fake_url": fake_url,
        "FakeFileOutput": _FakeFileOutput,
    }
