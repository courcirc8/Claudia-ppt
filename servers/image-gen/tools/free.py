"""Fallback gratuit via Pollinations AI — pas de token requis."""
from __future__ import annotations

import io
from urllib.parse import quote

import httpx
from PIL import Image

import cache
import config


def generate_image_free(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",
) -> dict:
    """Génère une image gratuitement via Pollinations AI (pas de token requis).

    Qualité moindre que Replicate mais utile pour démos / itérations rapides.

    Args:
        prompt: description texte
        width, height: dimensions (par défaut 1024×1024)
        model: 'flux' (qualité) ou 'turbo' (vitesse)
    """
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt requis")
    if model not in ("flux", "turbo"):
        raise ValueError("model doit être 'flux' ou 'turbo'")
    if not (64 <= int(width) <= 4096) or not (64 <= int(height) <= 4096):
        raise ValueError("Dimensions hors plage [64, 4096]")

    # Le prompt est interpolé dans le path → l'échapper sinon "/", "?", "#" cassent l'URL
    # ou permettent de cibler d'autres endpoints Pollinations.
    url = f"{config.POLLINATIONS_BASE_URL}/{quote(prompt, safe='')}"
    params = {
        "width": int(width),
        "height": int(height),
        "model": model,
        "nologo": "true",
    }
    with httpx.Client(timeout=120.0) as client:
        response = client.get(url, params=params, follow_redirects=True)
        response.raise_for_status()
        image_bytes = response.content

    # Vérifier que c'est bien une image (defense en profondeur contre upstream malicieux)
    ctype = response.headers.get("content-type", "").lower()
    if not ctype.startswith("image/"):
        raise RuntimeError(f"Pollinations a renvoyé un content-type non-image: {ctype!r}")
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.verify()
    except Exception as e:
        raise RuntimeError(f"Pollinations a renvoyé des bytes non-image: {e}")

    image_id = cache.save_image(
        image_bytes,
        metadata={
            "model": f"pollinations-{model}",
            "prompt": prompt,
            "operation": "generate_image_free",
            "backend": "pollinations",
        },
    )
    cache.log_cost("pollinations", 0.0, prompt, image_id)
    return {
        "image_id": image_id,
        "prompt": prompt,
        "model": f"pollinations-{model}",
        "cost_usd": 0.0,
    }
