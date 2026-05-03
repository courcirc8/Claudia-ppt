"""Outils de génération text→image et image→image."""
from __future__ import annotations

from PIL import Image
import io

import cache
import models
from dimensions import (
    compute_dimensions,
    gpt_image_2_aspect,
    parse_max_resolution,
    seedream_size_label,
)
from model_selector import auto_select_model
from prompt_enhancer import enhance_prompt
from replicate_client import call_replicate, download_image, extract_url, to_data_uri
from safe import safe_filename, safe_image_id


def _resolve_model(model: str, prompt: str) -> tuple[str, str | None]:
    """Convertit 'auto' en clé de modèle réelle. Retourne (key, reason_or_None)."""
    if model == "auto":
        return auto_select_model(prompt)
    return (model, None)


def _build_input_for_model(
    model_key: str,
    prompt: str,
    orientation: str,
    max_resolution: int,
    quality: str,
    source_image_bytes: bytes | None = None,
    source_w: int = 1024,
    source_h: int = 1024,
    refs: list[bytes] | None = None,
) -> dict:
    """Construit le dict `input` à passer à replicate.run, modèle par modèle."""
    refs = refs or []
    out_w, out_h = compute_dimensions(orientation, max_resolution, source_w, source_h)

    if model_key == "gpt-image-2":
        aspect = gpt_image_2_aspect(orientation, source_w, source_h)
        gpt_quality = quality if quality in ("low", "medium", "high", "auto") else "medium"
        api_input = {
            "prompt": prompt,
            "aspect_ratio": aspect,
            "quality": gpt_quality,
            "output_format": "png",
            "number_of_images": 1,
        }
        input_images = []
        if source_image_bytes:
            input_images.append(io.BytesIO(source_image_bytes))
        for r in refs:
            input_images.append(io.BytesIO(r))
        if input_images:
            api_input["input_images"] = input_images
        return api_input

    if model_key == "flux-pro":
        api_input = {
            "prompt": prompt,
            "guidance": 7.5,
            "num_inference_steps": 50,
            "output_format": "png",
            "width": out_w,
            "height": out_h,
        }
        if source_image_bytes:
            api_input["image"] = io.BytesIO(source_image_bytes)
        return api_input

    if model_key == "seedream":
        api_input = {
            "prompt": prompt,
            "width": out_w,
            "height": out_h,
            "enhance_prompt": True,
        }
        image_inputs = []
        if source_image_bytes:
            image_inputs.append(io.BytesIO(source_image_bytes))
        for r in refs:
            image_inputs.append(io.BytesIO(r))
        if image_inputs:
            api_input["image_input"] = image_inputs
        return api_input

    if model_key == "seedream-4.5":
        size = seedream_size_label(max_resolution)
        api_input = {
            "prompt": prompt,
            "size": size,
            "max_images": 1,
        }
        image_inputs = []
        if source_image_bytes:
            image_inputs.append(to_data_uri(source_image_bytes))
        for r in refs:
            image_inputs.append(to_data_uri(r))
        if image_inputs:
            api_input["image_input"] = image_inputs
            api_input["aspect_ratio"] = "match_input_image"
        return api_input

    if model_key == "seedream-5":
        api_input = {"prompt": prompt, "width": out_w, "height": out_h}
        if source_image_bytes:
            api_input["image"] = to_data_uri(source_image_bytes)
        return api_input

    if model_key in ("nano-banana", "nano-banana-pro"):
        api_input = {
            "prompt": prompt,
            "output_format": "png" if model_key == "nano-banana-pro" else "jpg",
        }
        image_inputs = []
        if source_image_bytes:
            image_inputs.append(io.BytesIO(source_image_bytes))
        for r in refs:
            image_inputs.append(io.BytesIO(r))
        if image_inputs:
            api_input["image_input"] = image_inputs
            api_input["aspect_ratio"] = "match_input_image"
        return api_input

    raise ValueError(f"Modèle non supporté: {model_key}")


def generate_image(
    prompt: str,
    model: str = "auto",
    orientation: str = "auto",
    max_resolution=None,
    enhance: bool = True,
    seed: int | None = None,
) -> dict:
    """Génère une image depuis un prompt texte. Retourne {image_id, prompt, model, cost_usd}.

    Args:
        prompt: description texte de l'image
        model: clé du modèle, ou 'auto' (défaut) pour sélection automatique :
               - prompt visuel simple → seedream-4.5 (2K, $0.06)
               - prompt complexe / texte / infographie → gpt-image-2
        orientation: 'auto', 'square', 'landscape_3_2', 'portrait_2_3', etc.
        max_resolution: int (pixels) ou string ('low'/'medium'/'high' pour gpt-image-2).
                        None = défaut du modèle (2K seedream / medium gpt-image-2).
        enhance: True (défaut) = enrichit les prompts courts. False = laisse tel quel.
        seed: optionnel, pour reproductibilité (non garanti par tous les modèles)
    """
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt requis (string non vide)")

    # Résolution du modèle 'auto' → modèle réel
    model, auto_reason = _resolve_model(model, prompt)
    if model not in models.MODELS:
        raise ValueError(f"Modèle inconnu: {model}. Disponibles : {list(models.MODELS)} ou 'auto'")

    cfg = models.MODELS[model]
    if not cfg["supports_text_to_image"]:
        raise ValueError(
            f"Le modèle {model} ne supporte pas text-to-image. "
            f"Utilise image_to_image ou choisis un autre modèle."
        )

    if max_resolution is None:
        max_resolution = cfg["resolution_default"]
    px, quality = parse_max_resolution(max_resolution)
    final_prompt = enhance_prompt(prompt, enhance)

    api_input = _build_input_for_model(
        model_key=model,
        prompt=final_prompt,
        orientation=orientation,
        max_resolution=px,
        quality=quality,
    )
    if seed is not None:
        api_input["seed"] = int(seed)

    output = call_replicate(cfg["id"], api_input)
    image_url = extract_url(output)
    image_bytes = download_image(image_url)

    cost_usd = models.estimate_cost(model, max_resolution if cfg["resolution_type"] == "quality" else px)
    image_id = cache.save_image(
        image_bytes,
        metadata={
            "model": model,
            "model_id": cfg["id"],
            "prompt": prompt,
            "prompt_enhanced": final_prompt if final_prompt != prompt else None,
            "orientation": orientation,
            "max_resolution": max_resolution,
            "quality": quality,
            "seed": seed,
            "operation": "generate_image",
        },
    )
    cache.log_cost(model, cost_usd, prompt, image_id)
    result = {
        "image_id": image_id,
        "prompt": final_prompt,
        "model": model,
        "cost_usd": round(cost_usd, 4),
    }
    if auto_reason:
        result["auto_select_reason"] = auto_reason
    return result


def image_to_image(
    image_id: str,
    prompt: str,
    model: str = "gpt-image-2",
    strength: float = 0.7,
    orientation: str = "auto",
    max_resolution=None,
    enhance: bool = True,
) -> dict:
    """Transforme une image existante via prompt. image_id = ID retourné par generate_image.

    Modèle par défaut : **gpt-image-2** — meilleur pour les édits ciblés (préservation
    du sujet, suivi d'instructions précises type 'change uniquement le fond', 'ajoute
    X sans toucher Y'). L'image source est automatiquement passée en référence.

    Pour des transformations stylistiques globales (filtre, repaint), passe
    explicitement model='seedream-4.5' ou model='nano-banana'.
    """
    image_id = safe_image_id(image_id)
    if not image_id:
        raise ValueError("image_id invalide")
    src_path = cache.get_image_path(image_id)
    if not src_path:
        raise ValueError(f"Image introuvable: {image_id}")
    source_bytes = src_path.read_bytes()
    with Image.open(io.BytesIO(source_bytes)) as img:
        src_w, src_h = img.size

    # 'auto' reste possible mais on biaise fortement vers gpt-image-2 en mode édition
    model, auto_reason = _resolve_model(model, prompt)
    if model not in models.MODELS:
        raise ValueError(f"Modèle inconnu: {model}")
    cfg = models.MODELS[model]
    if not cfg["supports_image_input"]:
        raise ValueError(f"{model} ne supporte pas image-to-image")

    if max_resolution is None:
        max_resolution = cfg["resolution_default"]
    px, quality = parse_max_resolution(max_resolution)
    final_prompt = enhance_prompt(prompt, enhance)

    api_input = _build_input_for_model(
        model_key=model,
        prompt=final_prompt,
        orientation=orientation,
        max_resolution=px,
        quality=quality,
        source_image_bytes=source_bytes,
        source_w=src_w,
        source_h=src_h,
    )
    # strength uniquement pertinent pour quelques modèles (ex: flux variations)
    if model in ("flux-pro",):
        api_input["prompt_strength"] = float(strength)

    output = call_replicate(cfg["id"], api_input)
    image_url = extract_url(output)
    image_bytes = download_image(image_url)

    cost_usd = models.estimate_cost(model, max_resolution if cfg["resolution_type"] == "quality" else px)
    new_id = cache.save_image(
        image_bytes,
        metadata={
            "model": model,
            "model_id": cfg["id"],
            "prompt": prompt,
            "source_image_id": image_id,
            "strength": strength,
            "operation": "image_to_image",
        },
    )
    cache.log_cost(model, cost_usd, prompt, new_id)
    result = {
        "image_id": new_id,
        "source_image_id": image_id,
        "prompt": final_prompt,
        "model": model,
        "cost_usd": round(cost_usd, 4),
    }
    if auto_reason:
        result["auto_select_reason"] = auto_reason
    return result


def generate_batch(
    prompts: list[str],
    model: str = "auto",
    orientation: str = "landscape_3_2",
    max_resolution=None,
    style_ref_image_id: str | None = None,
    enhance: bool = True,
) -> dict:
    """Génère N images cohérentes (mêmes ratio + style). Idéal cover + slides d'un même deck.

    model='auto' (défaut) : analyse les prompts concaténés pour choisir le meilleur
    modèle pour TOUT le batch (cohérence stylistique préservée — pas de mix).

    Si style_ref_image_id est fourni, il est passé en image de référence à chaque appel
    (cohérence visuelle). Tous les appels sont indépendants — pas de batch API native côté
    Replicate, mais la cohérence vient du style_ref + même prompt suffix.
    """
    if not isinstance(prompts, list) or not prompts:
        raise ValueError("prompts doit être une liste non vide de strings")
    if len(prompts) > 20:
        raise ValueError("Maximum 20 images par batch (sécurité coût)")

    # Résolution 'auto' : analyse les prompts concaténés et garde le même modèle
    # pour tout le batch (la cohérence visuelle est plus importante que l'optimum
    # par prompt). Aucun mix dans un même batch.
    model, auto_reason = _resolve_model(model, " ".join(prompts))

    style_bytes = None
    if style_ref_image_id:
        sid = safe_image_id(style_ref_image_id)
        if not sid:
            raise ValueError("style_ref_image_id invalide")
        sp = cache.get_image_path(sid)
        if sp:
            style_bytes = sp.read_bytes()

    results = []
    total_cost = 0.0
    for prompt in prompts:
        cfg = models.MODELS[model]
        if max_resolution is None:
            max_resolution = cfg["resolution_default"]
        px, quality = parse_max_resolution(max_resolution)
        final_prompt = enhance_prompt(prompt, enhance)

        refs = [style_bytes] if style_bytes else []
        api_input = _build_input_for_model(
            model_key=model,
            prompt=final_prompt,
            orientation=orientation,
            max_resolution=px,
            quality=quality,
            refs=refs,
        )
        output = call_replicate(cfg["id"], api_input)
        image_bytes = download_image(extract_url(output))
        cost = models.estimate_cost(model, max_resolution if cfg["resolution_type"] == "quality" else px)
        total_cost += cost
        new_id = cache.save_image(
            image_bytes,
            metadata={
                "model": model,
                "model_id": cfg["id"],
                "prompt": prompt,
                "style_ref_image_id": style_ref_image_id,
                "operation": "generate_batch",
            },
        )
        cache.log_cost(model, cost, prompt, new_id)
        results.append({"image_id": new_id, "prompt": final_prompt, "cost_usd": round(cost, 4)})
    return {
        "images": results,
        "total_cost_usd": round(total_cost, 4),
        "model": model,
        "count": len(results),
    }
