"""Registry des modèles Replicate — capacités, ratios supportés, tarifs."""
from __future__ import annotations

from typing import Literal

# =============================================================================
# Capacités par modèle (port direct depuis RetoucheImage simple_gui.py)
# =============================================================================

# Ratios supportés par modèle (subset des 8 ratios UI)
ALL_RATIOS = ("auto", "square", "landscape_3_2", "landscape_16_9", "landscape_4_3",
              "portrait_2_3", "portrait_9_16", "portrait_3_4")

MODELS: dict[str, dict] = {
    "gpt-image-2": {
        "id": "openai/gpt-image-2",
        "description": "GPT Image 2 — édition SOTA, instructions précises, texte fiable.",
        "ratios": ("auto", "square", "landscape_3_2", "portrait_2_3"),
        "resolution_type": "quality",  # enum low/medium/high/auto
        "resolution_default": "medium",
        "supports_image_input": True,
        "supports_text_to_image": True,
        "pricing": {"low": 0.006, "medium": 0.053, "high": 0.211, "auto": 0.053},
    },
    "flux-pro": {
        "id": "black-forest-labs/flux-1.1-pro",
        "description": "Flux Pro — photos réalistes, qualité commerciale.",
        "ratios": ALL_RATIOS,
        "resolution_type": "pixels",
        "resolution_default": 2000,
        "supports_image_input": True,
        "supports_text_to_image": True,
        "pricing": {"flat": 0.040},
    },
    "seedream": {
        "id": "bytedance/seedream-4",
        "description": "SeeDream-4 — qualité artistique.",
        "ratios": ALL_RATIOS,
        "resolution_type": "pixels",
        "resolution_default": 2000,
        "supports_image_input": True,
        "supports_text_to_image": True,
        "pricing": {"flat": 0.050},
    },
    "seedream-4.5": {
        "id": "bytedance/seedream-4.5",
        "description": "SeeDream-4.5 — image-to-image amélioré, jusqu'à 4K.",
        "ratios": ALL_RATIOS,
        "resolution_type": "size",  # enum 1K/2K/4K via int
        "resolution_default": 2048,
        "supports_image_input": True,
        "supports_text_to_image": True,
        "pricing": {"1024": 0.040, "2048": 0.060, "4096": 0.100},
    },
    "seedream-5": {
        "id": "bytedance/seedream-5-lite",
        "description": "SeeDream-5 Lite — rapide, économique.",
        "ratios": ALL_RATIOS,
        "resolution_type": "pixels",
        "resolution_default": 2000,
        "supports_image_input": True,
        "supports_text_to_image": True,
        "pricing": {"flat": 0.035},
    },
    "nano-banana": {
        "id": "google/nano-banana",
        "description": "Google Nano Banana — style transfer, retouche contextuelle.",
        "ratios": ("auto",),  # match_input_image
        "resolution_type": "pixels",
        "resolution_default": 2000,
        "supports_image_input": True,
        "supports_text_to_image": False,
        "pricing": {"flat": 0.020},
    },
    "nano-banana-pro": {
        "id": "google/nano-banana-pro",
        "description": "Google Nano Banana Pro — qualité premium, photoréalisme.",
        "ratios": ("auto",),
        "resolution_type": "pixels",
        "resolution_default": 2000,
        "supports_image_input": True,
        "supports_text_to_image": False,
        "pricing": {"flat": 0.134},
    },
}

# Modèles spécialisés (utilisés par les outils dédiés, pas exposés au choix utilisateur)
SPECIALIZED_MODELS = {
    "upscale_clarity": {
        "id": "philz1337x/clarity-upscaler",
        "description": "Clarity Upscaler — upscale 2x/4x avec préservation des détails.",
        "pricing_estimate": (0.020, 0.100),  # range time-based
    },
    "background_remove": {
        "id": "851-labs/background-remover",
        "description": "Suppresseur d'arrière-plan, sortie PNG transparent.",
        "pricing_estimate": (0.005, 0.020),
    },
    "vectorize_recraft": {
        "id": "recraft-ai/recraft-v3",
        "description": "Recraft V3 (mode vector_illustration) — sortie SVG éditable.",
        "pricing_estimate": (0.040, 0.080),
    },
}

# =============================================================================
# Helpers de tarification
# =============================================================================

def estimate_cost(model_key: str, max_resolution: int | str | None = None) -> float:
    """Retourne le coût estimé (USD) pour un appel à ce modèle.

    Pour les modèles à prix fixe : ignore max_resolution.
    Pour les modèles quality/size : utilise la valeur correspondante.
    """
    if model_key in SPECIALIZED_MODELS:
        lo, hi = SPECIALIZED_MODELS[model_key]["pricing_estimate"]
        return (lo + hi) / 2

    if model_key not in MODELS:
        return 0.0
    pricing = MODELS[model_key]["pricing"]
    if "flat" in pricing:
        return pricing["flat"]
    # quality enum (gpt-image-2)
    if isinstance(max_resolution, str) and max_resolution in pricing:
        return pricing[max_resolution]
    # size enum (seedream-4.5) — int
    key = str(max_resolution) if max_resolution else None
    if key and key in pricing:
        return pricing[key]
    # fallback : prendre la valeur par défaut du modèle
    default = MODELS[model_key]["resolution_default"]
    return pricing.get(str(default)) or pricing.get(default) or 0.0


def get_model_id(model_key: str) -> str:
    """Retourne l'ID Replicate complet (ex: 'openai/gpt-image-2'). Raise si inconnu."""
    if model_key in MODELS:
        return MODELS[model_key]["id"]
    if model_key in SPECIALIZED_MODELS:
        return SPECIALIZED_MODELS[model_key]["id"]
    raise ValueError(f"Modèle inconnu: {model_key}")


def list_user_models() -> list[dict]:
    """Liste publique des modèles exposés à l'utilisateur (sans les spécialisés)."""
    return [
        {
            "key": key,
            "id": m["id"],
            "description": m["description"],
            "supports_text_to_image": m["supports_text_to_image"],
            "ratios": list(m["ratios"]),
        }
        for key, m in MODELS.items()
    ]
