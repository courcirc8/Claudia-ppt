"""Post-traitement : remove_background, upscale, vectorize, seamless_tile."""
from __future__ import annotations

import io
from PIL import Image, ImageFilter

import cache
import models
from replicate_client import call_replicate, download_image, extract_url, to_data_uri
from safe import safe_image_id


def _load_cached(image_id: str) -> tuple[bytes, int, int]:
    sid = safe_image_id(image_id)
    if not sid:
        raise ValueError(f"image_id invalide: {image_id}")
    p = cache.get_image_path(sid)
    if not p:
        raise ValueError(f"Image introuvable: {image_id}")
    data = p.read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
    return data, w, h


def remove_background(image_id: str) -> dict:
    """Retire l'arrière-plan, retourne un PNG transparent.

    Backend : 851-labs/background-remover (Replicate, ~$0.01).
    """
    image_bytes, w, h = _load_cached(image_id)
    model_id = models.get_model_id("background_remove")

    api_input = {"image": io.BytesIO(image_bytes)}
    output = call_replicate(model_id, api_input)
    new_bytes = download_image(extract_url(output))

    cost_usd = models.estimate_cost("background_remove")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "background_remove",
            "model_id": model_id,
            "source_image_id": safe_image_id(image_id),
            "operation": "remove_background",
        },
    )
    cache.log_cost("background_remove", cost_usd, "remove background", new_id)
    return {"image_id": new_id, "source_image_id": image_id, "cost_usd": round(cost_usd, 4)}


def upscale(
    image_id: str,
    factor: int = 2,
    mode: str = "crisp",
) -> dict:
    """Upscale 2× ou 4× avec Clarity Upscaler.

    Args:
        factor: 2 ou 4
        mode: 'crisp' (préserve les détails, photoréaliste) ou 'creative' (ajoute des détails)
    """
    if factor not in (2, 4):
        raise ValueError("factor doit être 2 ou 4")
    if mode not in ("crisp", "creative"):
        raise ValueError("mode doit être 'crisp' ou 'creative'")

    image_bytes, w, h = _load_cached(image_id)
    model_id = models.get_model_id("upscale_clarity")

    api_input = {
        "image": io.BytesIO(image_bytes),
        "scale_factor": factor,
        "creativity": 0.35 if mode == "crisp" else 0.7,
        "resemblance": 0.8 if mode == "crisp" else 0.5,
    }
    output = call_replicate(model_id, api_input)
    new_bytes = download_image(extract_url(output))

    cost_usd = models.estimate_cost("upscale_clarity")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "upscale_clarity",
            "model_id": model_id,
            "source_image_id": safe_image_id(image_id),
            "factor": factor,
            "mode": mode,
            "operation": "upscale",
        },
    )
    cache.log_cost("upscale_clarity", cost_usd, f"upscale {factor}x {mode}", new_id)
    return {
        "image_id": new_id,
        "source_image_id": image_id,
        "factor": factor,
        "mode": mode,
        "cost_usd": round(cost_usd, 4),
    }


def vectorize(image_id: str) -> dict:
    """Convertit une image raster en SVG via Recraft V3.

    Idéal pour les icônes et logos qu'on veut garder éditables dans PowerPoint.
    """
    image_bytes, w, h = _load_cached(image_id)
    model_id = models.get_model_id("vectorize_recraft")

    api_input = {
        "prompt": "vectorize this image, clean SVG output, preserve shapes",
        "input_image": to_data_uri(image_bytes),
        "style": "vector_illustration",
        "size": "1024x1024",
    }
    output = call_replicate(model_id, api_input)
    new_bytes = download_image(extract_url(output))

    # Détecter si c'est SVG ou raster (Recraft peut retourner les deux)
    is_svg = new_bytes[:5].lower() == b"<?xml" or b"<svg" in new_bytes[:100].lower()
    suffix = "svg" if is_svg else "png"

    cost_usd = models.estimate_cost("vectorize_recraft")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "vectorize_recraft",
            "model_id": model_id,
            "source_image_id": safe_image_id(image_id),
            "operation": "vectorize",
            "is_svg": is_svg,
        },
        suffix=suffix,
    )
    cache.log_cost("vectorize_recraft", cost_usd, "vectorize", new_id)
    return {
        "image_id": new_id,
        "source_image_id": image_id,
        "format": suffix,
        "is_svg": is_svg,
        "cost_usd": round(cost_usd, 4),
    }


def seamless_tile(image_id: str, blend_pixels: int = 64) -> dict:
    """Rend une image tilable via mirroring symétrique des bords.

    Implémentation purement locale (PIL, pas d'API). Coût: $0.

    Args:
        blend_pixels: largeur de la zone de fondu sur les bords (défaut 64)
    """
    image_bytes, w, h = _load_cached(image_id)
    blend = max(8, min(int(blend_pixels), min(w, h) // 4))

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Crée une version qui tile en mirrorant les bords
    # Pour le bord droit, on prend les `blend` premiers pixels et on les fond avec les derniers
    # Idem pour le bas. Technique simple : crossfade horizontal + vertical.

    arr = img.copy()

    # Horizontal mirror sur les bords gauche/droit
    left = arr.crop((0, 0, blend, h))
    right = arr.crop((w - blend, 0, w, h))
    # Mélanger : la zone droite prend progressivement les pixels miroir du gauche
    blended_right = Image.blend(right, left.transpose(Image.FLIP_LEFT_RIGHT), 0.5)
    arr.paste(blended_right, (w - blend, 0))

    # Vertical
    top = arr.crop((0, 0, w, blend))
    bottom = arr.crop((0, h - blend, w, h))
    blended_bottom = Image.blend(bottom, top.transpose(Image.FLIP_TOP_BOTTOM), 0.5)
    arr.paste(blended_bottom, (0, h - blend))

    # Adoucir les coutures
    arr = arr.filter(ImageFilter.SMOOTH_MORE)

    out_buf = io.BytesIO()
    arr.save(out_buf, "PNG")
    new_bytes = out_buf.getvalue()

    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "local",
            "source_image_id": safe_image_id(image_id),
            "operation": "seamless_tile",
            "blend_pixels": blend,
        },
    )
    return {"image_id": new_id, "source_image_id": image_id, "cost_usd": 0.0}
