"""Outils d'édition d'images existantes — inpaint, replace_background, outpaint."""
from __future__ import annotations

import io
from PIL import Image, ImageOps

import base64

import cache
import models
from prompt_enhancer import enhance_prompt
from replicate_client import call_replicate, download_image, extract_url, to_data_uri
from safe import safe_image_id


def _load_cached(image_id: str) -> tuple[bytes, int, int]:
    """Charge l'image depuis le cache. Retourne (bytes, w, h). Raise si absente."""
    sid = safe_image_id(image_id)
    if not sid:
        raise ValueError(f"image_id invalide: {image_id}")
    p = cache.get_image_path(sid)
    if not p:
        raise ValueError(f"Image introuvable dans le cache: {image_id}")
    data = p.read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        w, h = img.size
    return data, w, h


def inpaint(
    image_id: str,
    mask_base64: str,
    prompt: str,
    enhance: bool = True,
) -> dict:
    """Repeint une zone masquée. Le mask est PNG noir (préservé) / blanc (à remplacer).

    Args:
        image_id: ID retourné par generate_image
        mask_base64: PNG en base64 (peut inclure le préfixe 'data:image/png;base64,' ou pas)
        prompt: ce qu'il faut peindre dans la zone blanche
    """
    image_bytes, w, h = _load_cached(image_id)

    # Nettoyer le préfixe data URI si présent
    if mask_base64.startswith("data:"):
        mask_base64 = mask_base64.split(",", 1)[1]
    try:
        mask_bytes = base64.b64decode(mask_base64)
    except Exception as e:
        raise ValueError(f"mask_base64 invalide: {e}")

    final_prompt = enhance_prompt(prompt, enhance)
    # Utilise gpt-image-2 qui gère bien l'inpaint avec masque
    cfg = models.MODELS["gpt-image-2"]
    api_input = {
        "prompt": final_prompt,
        "input_images": [io.BytesIO(image_bytes)],
        "mask": io.BytesIO(mask_bytes),
        "quality": "medium",
        "output_format": "png",
        "number_of_images": 1,
    }
    output = call_replicate(cfg["id"], api_input)
    image_url = extract_url(output)
    new_bytes = download_image(image_url)

    cost_usd = models.estimate_cost("gpt-image-2", "medium")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "gpt-image-2",
            "prompt": prompt,
            "source_image_id": safe_image_id(image_id),
            "operation": "inpaint",
        },
    )
    cache.log_cost("gpt-image-2", cost_usd, prompt, new_id)
    return {"image_id": new_id, "source_image_id": image_id, "cost_usd": round(cost_usd, 4)}


def replace_background(
    image_id: str,
    prompt: str,
    enhance: bool = True,
) -> dict:
    """Remplace le fond, garde le sujet intact.

    Backend : **gpt-image-2** — bien meilleur que seedream pour suivre l'instruction
    'preserve the subject perfectly' (la préservation d'identité est sa force #1).
    L'image source est passée en input_images comme référence.
    """
    image_bytes, _, _ = _load_cached(image_id)
    final_prompt = (
        f"PRESERVE the subject perfectly, do NOT alter facial features or product details. "
        f"Replace ONLY the background with: {prompt}. "
        "The subject must remain identical, only the background changes."
    )

    cfg = models.MODELS["gpt-image-2"]
    api_input = {
        "prompt": final_prompt,
        "input_images": [io.BytesIO(image_bytes)],
        "aspect_ratio": "1:1",  # gpt-image-2 ratios limités, on prendra match si possible
        "quality": "medium",
        "output_format": "png",
        "number_of_images": 1,
    }
    output = call_replicate(cfg["id"], api_input)
    new_bytes = download_image(extract_url(output))
    cost_usd = models.estimate_cost("gpt-image-2", "medium")
    new_id = cache.save_image(
        new_bytes,
        metadata={
            "model": "gpt-image-2",
            "prompt": prompt,
            "source_image_id": safe_image_id(image_id),
            "operation": "replace_background",
        },
    )
    cache.log_cost("gpt-image-2", cost_usd, prompt, new_id)
    return {"image_id": new_id, "source_image_id": image_id, "cost_usd": round(cost_usd, 4)}


def outpaint(
    image_id: str,
    direction: str = "all",
    pixels: int = 256,
    prompt: str = "",
    enhance: bool = True,
) -> dict:
    """Étend le canvas dans une direction (top/right/bottom/left/all) puis demande à
    gpt-image-2 de remplir la nouvelle zone.

    Implémentation : on étend l'image avec PIL (zone vide), génère un mask qui couvre
    uniquement la nouvelle zone, puis utilise inpaint sous le capot.
    """
    if direction not in ("top", "right", "bottom", "left", "all"):
        raise ValueError("direction doit être top/right/bottom/left/all")
    pixels = max(32, min(int(pixels), 2048))

    image_bytes, w, h = _load_cached(image_id)
    src = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

    # Calcule les paddings selon direction
    if direction == "all":
        pad = (pixels, pixels, pixels, pixels)  # left, top, right, bottom
    elif direction == "top":
        pad = (0, pixels, 0, 0)
    elif direction == "bottom":
        pad = (0, 0, 0, pixels)
    elif direction == "left":
        pad = (pixels, 0, 0, 0)
    else:  # right
        pad = (0, 0, pixels, 0)

    extended = ImageOps.expand(src, border=pad, fill=(0, 0, 0, 0))
    new_w, new_h = extended.size
    # Mask : blanc (à remplir) sur la zone étendue, noir sur l'image originale
    mask = Image.new("L", (new_w, new_h), 255)  # tout blanc
    mask.paste(0, (pad[0], pad[1], pad[0] + w, pad[1] + h))  # noir sur l'original

    # Encode extended + mask en bytes pour inpaint
    ext_buf = io.BytesIO()
    extended.save(ext_buf, "PNG")
    ext_id = cache.save_image(
        ext_buf.getvalue(),
        metadata={
            "operation": "outpaint_extended",
            "source_image_id": safe_image_id(image_id),
            "direction": direction,
            "pixels": pixels,
        },
    )

    mask_buf = io.BytesIO()
    mask.save(mask_buf, "PNG")
    mask_b64 = base64.b64encode(mask_buf.getvalue()).decode("utf-8")

    extend_prompt = prompt or "naturally extend the scene to fill the new area"
    return inpaint(ext_id, mask_b64, extend_prompt, enhance=enhance)


def register_image(file_path: str | None = None, image_base64: str | None = None) -> dict:
    """Importe une image utilisateur dans le cache. Retourne un image_id utilisable
    par les autres outils (image_to_image, replace_background, etc.).

    Args:
        file_path: chemin local vers l'image (PNG/JPG/WEBP)
        image_base64: alternative — image encodée en base64
    """
    if file_path:
        from pathlib import Path
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            raise ValueError(f"Fichier introuvable: {file_path}")
        if not p.is_file():
            raise ValueError(f"Pas un fichier: {file_path}")
        # Limite à 50 Mo pour éviter abus
        if p.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Fichier trop gros (max 50 Mo)")
        image_bytes = p.read_bytes()
        suffix = p.suffix.lower().lstrip(".") or "png"
    elif image_base64:
        if image_base64.startswith("data:"):
            image_base64 = image_base64.split(",", 1)[1]
        try:
            image_bytes = base64.b64decode(image_base64)
        except Exception as e:
            raise ValueError(f"base64 invalide: {e}")
        suffix = "png"
    else:
        raise ValueError("Fournir file_path ou image_base64")

    # Vérifier que c'est une image valide
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            w, h = img.size
            fmt = (img.format or "PNG").lower()
            if fmt == "jpeg":
                fmt = "jpg"
            suffix = fmt
    except Exception as e:
        raise ValueError(f"Image illisible: {e}")

    image_id = cache.save_image(
        image_bytes,
        metadata={
            "operation": "register_image",
            "source": "user_upload",
            "width": w,
            "height": h,
            "original_path": file_path if file_path else None,
        },
        suffix=suffix,
    )
    return {"image_id": image_id, "width": w, "height": h, "format": suffix}
