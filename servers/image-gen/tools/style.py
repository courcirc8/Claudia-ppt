"""apply_style — reproduit le style d'une image de référence sur un nouveau prompt."""
from __future__ import annotations

import io

import cache
import models
from prompt_enhancer import enhance_prompt
from replicate_client import call_replicate, download_image, extract_url, to_data_uri
from safe import safe_image_id


def apply_style(
    style_ref_image_id: str,
    prompt: str,
    model: str = "seedream-4.5",
    enhance: bool = True,
) -> dict:
    """Génère une nouvelle image en imitant le style d'une image de référence.

    Args:
        style_ref_image_id: ID d'une image existante (générée ou registered)
                            qui sert de référence visuelle
        prompt: description du nouveau sujet (le style sera celui de la référence)
        model: 'seedream-4.5' (défaut, supporte ref images via image_input)
               ou 'gpt-image-2' / 'nano-banana'
    """
    sid = safe_image_id(style_ref_image_id)
    if not sid:
        raise ValueError("style_ref_image_id invalide")
    p = cache.get_image_path(sid)
    if not p:
        raise ValueError(f"Image de référence introuvable: {style_ref_image_id}")
    ref_bytes = p.read_bytes()

    if model not in models.MODELS:
        raise ValueError(f"Modèle inconnu: {model}")
    cfg = models.MODELS[model]

    final_prompt = enhance_prompt(prompt, enhance) + ", in the same visual style as the reference image"

    # Construction par modèle (chacun a une convention différente pour les refs)
    if model == "seedream-4.5":
        api_input = {
            "prompt": final_prompt,
            "size": "2K",
            "max_images": 1,
            "image_input": [to_data_uri(ref_bytes)],
            "aspect_ratio": "match_input_image",
        }
    elif model == "gpt-image-2":
        api_input = {
            "prompt": final_prompt,
            "input_images": [io.BytesIO(ref_bytes)],
            "aspect_ratio": "1:1",
            "quality": "medium",
            "output_format": "png",
            "number_of_images": 1,
        }
    elif model in ("nano-banana", "nano-banana-pro"):
        api_input = {
            "prompt": final_prompt,
            "image_input": [io.BytesIO(ref_bytes)],
            "aspect_ratio": "match_input_image",
            "output_format": "png",
        }
    else:
        raise ValueError(
            f"{model} ne supporte pas les style references. "
            "Utilise seedream-4.5, gpt-image-2 ou nano-banana."
        )

    output = call_replicate(cfg["id"], api_input)
    new_bytes = download_image(extract_url(output))

    cost_usd = models.estimate_cost(model, 2048 if model == "seedream-4.5" else "medium")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": model,
            "model_id": cfg["id"],
            "prompt": prompt,
            "style_ref_image_id": sid,
            "operation": "apply_style",
        },
    )
    cache.log_cost(model, cost_usd, prompt, new_id)
    return {
        "image_id": new_id,
        "style_ref_image_id": sid,
        "model": model,
        "cost_usd": round(cost_usd, 4),
    }
