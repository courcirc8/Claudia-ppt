#!/usr/bin/env python
"""Image Generation MCP Server v2 — Replicate-backed avec 18 outils.

Backend principal : Replicate (8 modèles SOTA dont gpt-image-2).
Fallback gratuit : Pollinations (generate_image_free).

Voir README.md pour la liste complète des outils et leurs cas d'usage.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Permettre les imports absolus depuis le dossier server.py
_DIR = Path(__file__).parent
if str(_DIR) not in sys.path:
    sys.path.insert(0, str(_DIR))

from mcp.server.fastmcp import FastMCP  # noqa: E402

import config  # noqa: E402
import models  # noqa: E402
from tools.generate import generate_image, image_to_image, generate_batch  # noqa: E402
from tools.slide import generate_for_slide  # noqa: E402
from tools.free import generate_image_free  # noqa: E402
from tools.ollama_local import (  # noqa: E402
    generate_image_ollama,
    list_ollama_image_models,
    pull_ollama_model,
)
from tools.edit import inpaint, replace_background, outpaint, register_image  # noqa: E402
from tools.process import remove_background, upscale, vectorize, seamless_tile  # noqa: E402
from tools.manage import list_images, get_image, delete_image, get_costs  # noqa: E402
from tools.style import apply_style  # noqa: E402

# Lire la version
try:
    APP_VERSION = (_DIR / "VERSION").read_text(encoding="utf-8").strip()
except Exception:
    APP_VERSION = "?"

# Avertir si pas de token Replicate (mais ne pas bloquer — Pollinations marche sans)
config.warn_if_no_token()

app = FastMCP(name=f"image-gen v{APP_VERSION}")

# =============================================================================
# Génération (5 outils)
# =============================================================================

@app.tool()
def tool_generate_image(
    prompt: str,
    model: str = "auto",
    orientation: str = "auto",
    max_resolution: str = "medium",
    enhance: bool = True,
    seed: int | None = None,
) -> dict:
    """Génère une image depuis un prompt texte (text-to-image).

    **Modèle 'auto' (défaut, recommandé pour PPT)** :
    - prompt visuel simple → seedream-4.5 (2K, $0.06, qualité photo top)
    - prompt avec texte/infographie/diagramme → gpt-image-2 (suivi d'instructions)
    Le retour inclut `auto_select_reason` pour la transparence.

    Modèles explicites : gpt-image-2, flux-pro, seedream, seedream-4.5, seedream-5,
    nano-banana, nano-banana-pro.

    orientation : 'auto', 'square' (1:1), 'landscape_3_2', 'landscape_16_9',
                  'landscape_4_3', 'portrait_2_3', 'portrait_9_16', 'portrait_3_4'.
                  Note : gpt-image-2 ne supporte que 1:1, 3:2, 2:3.

    max_resolution : pour gpt-image-2 → 'low'/'medium'/'high'/'auto'.
                     Pour les autres → entier en pixels (1000-8000).
                     Pour seedream-4.5 → 1024 / 2048 / 4096 (1K/2K/4K).
                     2K (= medium) suffit pour PPT, 4K seulement pour print/cover.

    Retourne {image_id, prompt, model, cost_usd, [auto_select_reason]}.
    """
    # Convertir max_resolution string→int si numérique
    if isinstance(max_resolution, str) and max_resolution.isdigit():
        max_resolution = int(max_resolution)
    return generate_image(
        prompt=prompt, model=model, orientation=orientation,
        max_resolution=max_resolution, enhance=enhance, seed=seed,
    )


@app.tool()
def tool_image_to_image(
    image_id: str,
    prompt: str,
    model: str = "gpt-image-2",
    strength: float = 0.7,
    orientation: str = "auto",
    max_resolution: str = "medium",
    enhance: bool = True,
) -> dict:
    """Transforme une image existante via prompt. image_id provient de generate_image
    ou de register_image (upload utilisateur).

    **Défaut gpt-image-2** : excelle à préserver le sujet et suivre des instructions
    précises ('change uniquement le fond', 'ajoute X sans toucher Y'). L'image source
    est automatiquement passée en référence (input_images).

    Pour des transformations stylistiques globales (filtre, repaint), utilise
    seedream-4.5 ou nano-banana.

    strength (0-1) : intensité. 0 = quasi identique, 1 = très différent.
    """
    if isinstance(max_resolution, str) and max_resolution.isdigit():
        max_resolution = int(max_resolution)
    return image_to_image(
        image_id=image_id, prompt=prompt, model=model, strength=strength,
        orientation=orientation, max_resolution=max_resolution, enhance=enhance,
    )


@app.tool()
def tool_generate_batch(
    prompts: list[str],
    model: str = "auto",
    orientation: str = "landscape_3_2",
    max_resolution: str = "medium",
    style_ref_image_id: str | None = None,
    enhance: bool = True,
) -> dict:
    """Génère N images cohérentes pour un même deck PPT (cover + slides).

    model='auto' (défaut) : analyse les prompts concaténés pour choisir un seul
    modèle qui sera utilisé pour TOUT le batch (cohérence stylistique préservée).

    Si style_ref_image_id est fourni, chaque image est générée en référence à
    cette image-style → cohérence visuelle garantie.

    Maximum 20 images par appel pour limiter les coûts.
    """
    if isinstance(max_resolution, str) and max_resolution.isdigit():
        max_resolution = int(max_resolution)
    return generate_batch(
        prompts=prompts, model=model, orientation=orientation,
        max_resolution=max_resolution, style_ref_image_id=style_ref_image_id, enhance=enhance,
    )


@app.tool()
def tool_generate_for_slide(role: str, prompt: str) -> dict:
    """Génère une image avec les paramètres adaptés au rôle PPT.

    Rôles : 'cover' (16:9 high), 'section', 'icon' (1:1, flat),
            'photo' (3:2 photographique), 'illustration', 'background'
            (subtle pattern), 'infographic' (4:3 flat design),
            'headshot' (2:3 portrait studio).

    Le suffix style est ajouté automatiquement au prompt.
    """
    return generate_for_slide(role=role, prompt=prompt)


@app.tool()
def tool_generate_image_free(
    prompt: str,
    width: int = 1024,
    height: int = 1024,
    model: str = "flux",
) -> dict:
    """Génère une image gratuitement via Pollinations AI (pas de token requis).

    Qualité moindre que les modèles Replicate, idéal pour démos / itérations
    rapides. model='flux' (qualité) ou 'turbo' (vitesse).
    """
    return generate_image_free(prompt=prompt, width=width, height=height, model=model)


# =============================================================================
# Génération locale via Ollama MLX (3 outils, Apple Silicon, coût $0)
# =============================================================================

@app.tool()
def tool_generate_image_ollama(
    prompt: str,
    model: str = "x/flux2-klein:9b",
    size: str = "1024x1024",
    target_size: str | None = None,
    resize_mode: str = "fit",
    seed: int | None = None,
    steps: int | None = None,
) -> dict:
    """Génère une image **localement** via Ollama MLX (Apple Silicon, coût $0).

    Nécessite Ollama ≥ 0.23.3 (0.23.2 a un panic) avec un modèle image-gen pullé :
        ollama pull x/flux2-klein:9b   # FLUX.2 Klein 9B (~11 GB, qualité haute)
        ollama pull x/flux2-klein:4b   # FLUX.2 Klein 4B (plus rapide)
        ollama pull x/z-image-turbo    # Z-Image Turbo (drafts ultra-rapides)

    Avantages : 100% local (aucune donnée envoyée), coût zéro, illimité.
    Inconvénients : ~30-60s/image sur M-series (vs 5-15s cloud).

    **Résolutions** : Ollama 0.24 ignore `size` et sort toujours 1024×1024.
    Pour obtenir un autre format (16:9 pour cover PPT, 4:3 pour infographic),
    utiliser `target_size` — resize PIL post-génération.

    Exemples target_size : '1920x1080' (16:9 cover), '1024x768' (4:3),
    '768x1024' (portrait 3:4), '1280x720' (720p), '2048x2048' (carré upscalé).

    resize_mode :
      - 'fit'     : letterbox blanc, image entière visible (défaut)
      - 'cover'   : crop centré, remplit le canvas (perd des bords)
      - 'stretch' : déforme (déconseillé)
    """
    return generate_image_ollama(
        prompt=prompt, model=model, size=size,
        target_size=target_size, resize_mode=resize_mode,
        seed=seed, steps=steps,
    )


@app.tool()
def tool_list_ollama_image_models() -> dict:
    """Liste les modèles image-gen Ollama installés localement.

    Retourne {ollama_running, installed[], image_candidates[], known_image_models}.
    Utile pour choisir un model avant `generate_image_ollama`.
    """
    return list_ollama_image_models()


@app.tool()
def tool_pull_ollama_model(model: str = "x/flux2-klein:9b") -> dict:
    """Télécharge un modèle image-gen Ollama (peut prendre 10-30 min, ~11 GB).

    Wrapper synchrone sur `ollama pull <model>`. Préfère lancer ce pull depuis
    un terminal pour voir la progression.
    """
    return pull_ollama_model(model=model)


# =============================================================================
# Édition (4 outils)
# =============================================================================

@app.tool()
def tool_inpaint(image_id: str, mask_base64: str, prompt: str, enhance: bool = True) -> dict:
    """Repeint une zone masquée d'une image. mask_base64 = PNG noir (préservé) /
    blanc (à remplacer)."""
    return inpaint(image_id=image_id, mask_base64=mask_base64, prompt=prompt, enhance=enhance)


@app.tool()
def tool_replace_background(image_id: str, prompt: str, enhance: bool = True) -> dict:
    """Remplace l'arrière-plan d'une image, garde le sujet intact.

    Plus simple que inpaint (pas besoin de mask) mais moins précis.
    """
    return replace_background(image_id=image_id, prompt=prompt, enhance=enhance)


@app.tool()
def tool_outpaint(
    image_id: str,
    direction: str = "all",
    pixels: int = 256,
    prompt: str = "",
    enhance: bool = True,
) -> dict:
    """Étend le canvas d'une image. direction: 'top'/'right'/'bottom'/'left'/'all'."""
    return outpaint(image_id=image_id, direction=direction, pixels=pixels,
                    prompt=prompt, enhance=enhance)


@app.tool()
def tool_register_image(file_path: str | None = None, image_base64: str | None = None) -> dict:
    """Importe une image utilisateur dans le cache. Retourne un image_id utilisable
    par tous les autres outils. Fournir file_path OU image_base64."""
    return register_image(file_path=file_path, image_base64=image_base64)


# =============================================================================
# Post-traitement (4 outils)
# =============================================================================

@app.tool()
def tool_remove_background(image_id: str) -> dict:
    """Retire le fond, retourne un PNG transparent (idéal icônes / logos isolés)."""
    return remove_background(image_id=image_id)


@app.tool()
def tool_upscale(image_id: str, factor: int = 2, mode: str = "crisp") -> dict:
    """Upscale 2× ou 4×. mode: 'crisp' (réaliste) ou 'creative' (ajoute détails)."""
    return upscale(image_id=image_id, factor=factor, mode=mode)


@app.tool()
def tool_vectorize(image_id: str) -> dict:
    """Convertit une image raster en SVG (icônes éditables PowerPoint)."""
    return vectorize(image_id=image_id)


@app.tool()
def tool_seamless_tile(image_id: str, blend_pixels: int = 64) -> dict:
    """Rend l'image tilable pour fond de slide répétitif. Coût: $0 (local PIL)."""
    return seamless_tile(image_id=image_id, blend_pixels=blend_pixels)


# =============================================================================
# Gestion (4 outils)
# =============================================================================

@app.tool()
def tool_list_images(limit: int = 50, model_filter: str | None = None) -> dict:
    """Liste les N dernières images générées (métadonnées seulement)."""
    return list_images(limit=limit, model_filter=model_filter)


@app.tool()
def tool_get_image(image_id: str, include_base64: bool = True) -> dict:
    """Récupère une image (base64 + métadonnées). Pour passer l'image à un autre MCP."""
    return get_image(image_id=image_id, include_base64=include_base64)


@app.tool()
def tool_delete_image(image_id: str) -> dict:
    """Supprime une image du cache (image + métadonnées)."""
    return delete_image(image_id=image_id)


@app.tool()
def tool_get_costs() -> dict:
    """Retourne le total dépensé sur Replicate + breakdown par modèle."""
    return get_costs()


# =============================================================================
# Cohérence stylistique (1 outil)
# =============================================================================

@app.tool()
def tool_apply_style(
    style_ref_image_id: str,
    prompt: str,
    model: str = "seedream-4.5",
    enhance: bool = True,
) -> dict:
    """Génère une nouvelle image qui imite le style d'une image de référence."""
    return apply_style(style_ref_image_id=style_ref_image_id, prompt=prompt,
                       model=model, enhance=enhance)


# =============================================================================
# Outils d'introspection (bonus, gratuits)
# =============================================================================

@app.tool()
def tool_list_models() -> dict:
    """Liste les modèles Replicate disponibles + leurs capacités."""
    return {"models": models.list_user_models(), "count": len(models.MODELS)}


def main() -> None:
    """Entry point."""
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
