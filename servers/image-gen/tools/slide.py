"""Helper haut niveau : generate_for_slide(role, ...) — preset PPT-friendly."""
from __future__ import annotations

from tools.generate import generate_image

# Presets adaptés à chaque rôle de visuel dans un deck PPT
SLIDE_ROLE_PRESETS = {
    "cover": {
        "model": "gpt-image-2",
        "orientation": "landscape_16_9",
        "max_resolution": "high",
        "prompt_suffix": ", striking cover image, bold composition, clear focal point",
    },
    "section": {
        "model": "seedream-4.5",
        "orientation": "landscape_16_9",
        "max_resolution": 2048,
        "prompt_suffix": ", clean section divider visual, moderate detail",
    },
    "icon": {
        "model": "gpt-image-2",
        "orientation": "square",
        "max_resolution": "medium",
        "prompt_suffix": ", minimalist flat icon, bold colors, centered, no background details",
    },
    "photo": {
        "model": "flux-pro",
        "orientation": "landscape_3_2",
        "max_resolution": 2000,
        "prompt_suffix": ", professional photography, sharp focus, natural lighting",
    },
    "illustration": {
        "model": "seedream-4.5",
        "orientation": "landscape_3_2",
        "max_resolution": 2048,
        "prompt_suffix": ", editorial illustration, cohesive style, clear narrative",
    },
    "background": {
        "model": "flux-pro",
        "orientation": "landscape_16_9",
        "max_resolution": 2000,
        "prompt_suffix": ", subtle background pattern, low contrast, suitable for text overlay",
    },
    "infographic": {
        "model": "gpt-image-2",
        "orientation": "landscape_4_3",
        "max_resolution": "high",
        "prompt_suffix": ", clean infographic style, flat design, clear data visualization, blue palette",
    },
    "headshot": {
        "model": "flux-pro",
        "orientation": "portrait_2_3",
        "max_resolution": 2000,
        "prompt_suffix": ", professional headshot, neutral background, soft studio lighting",
    },
}


def generate_for_slide(role: str, prompt: str, **overrides) -> dict:
    """Génère une image avec les paramètres adaptés au rôle PPT.

    Args:
        role: 'cover' | 'section' | 'icon' | 'photo' | 'illustration' | 'background'
              | 'infographic' | 'headshot'
        prompt: description du sujet (le suffix style est ajouté automatiquement)
        **overrides: surcharges optionnelles (model, orientation, max_resolution, enhance)

    Retourne le même dict que generate_image.
    """
    if role not in SLIDE_ROLE_PRESETS:
        raise ValueError(
            f"role inconnu: {role!r}. Disponibles : {list(SLIDE_ROLE_PRESETS)}"
        )
    preset = SLIDE_ROLE_PRESETS[role]
    final_prompt = prompt + preset["prompt_suffix"]
    params = {
        "prompt": final_prompt,
        "model": preset["model"],
        "orientation": preset["orientation"],
        "max_resolution": preset["max_resolution"],
        "enhance": False,  # déjà enrichi via le suffix preset
    }
    params.update(overrides)
    result = generate_image(**params)
    result["slide_role"] = role
    return result
