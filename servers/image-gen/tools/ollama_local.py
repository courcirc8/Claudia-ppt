"""Génération locale via Ollama (MLX backend, Apple Silicon).

Ollama 0.19+ supporte la génération d'image localement sur macOS via MLX.
Endpoint : POST http://localhost:11434/api/generate avec un modèle image-gen
(ex: x/flux2-klein:9b, x/z-image-turbo). Réponse = bytes PNG bruts.

Coût : $0. Vie privée : totale (aucun appel cloud).
"""
from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import time

import httpx
from PIL import Image

import cache


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Modèles image-gen connus exposés par Ollama. Le tag est indicatif ;
# l'utilisateur peut passer n'importe quel nom dispo dans `ollama list`.
KNOWN_IMAGE_MODELS = {
    "x/flux2-klein:9b": "FLUX.2 Klein 9B — qualité haute, ~30-60s sur M-series",
    "x/flux2-klein:4b": "FLUX.2 Klein 4B — plus rapide, qualité correcte",
    "x/z-image-turbo:bf16": "Z-Image Turbo bf16 — drafts ultra-rapides",
    "x/z-image-turbo:pf8": "Z-Image Turbo pf8 — drafts, mémoire réduite",
}

# Valeur par défaut : le 9B Flux.2 Klein si dispo.
DEFAULT_MODEL = "x/flux2-klein:9b"


def _is_ollama_running() -> bool:
    """Ping rapide du serveur Ollama. Retourne False si pas joignable."""
    try:
        with httpx.Client(timeout=2.0) as client:
            r = client.get(f"{OLLAMA_BASE_URL}/api/version")
            return r.status_code == 200
    except Exception:
        return False


def _ollama_running_or_raise() -> None:
    if not _is_ollama_running():
        raise RuntimeError(
            f"Serveur Ollama injoignable sur {OLLAMA_BASE_URL}.\n"
            "Marche à suivre :\n"
            "  1. Installer Ollama 0.19+ : https://ollama.com/download\n"
            "  2. Lancer le daemon : `ollama serve` (ou via l'app menubar)\n"
            "  3. Pull un modèle image : `ollama pull x/flux2-klein:9b`\n"
        )


def generate_image_ollama(
    prompt: str,
    model: str = DEFAULT_MODEL,
    size: str = "1024x1024",
    target_size: str | None = None,
    resize_mode: str = "fit",
    seed: int | None = None,
    steps: int | None = None,
    timeout: float = 600.0,
) -> dict:
    """Génère une image localement via Ollama MLX. Coût $0.

    Note résolution (Ollama 0.24) : le paramètre `size` est passé à Ollama mais
    actuellement ignoré côté serveur — la sortie native fait toujours ~1024×1024.
    Pour obtenir une résolution / aspect ratio différent, utiliser `target_size` :
    le MCP fera un resize PIL post-génération (rapide, lossless avant compression).

    Args:
        prompt: description texte
        model: nom de modèle Ollama image-gen (voir KNOWN_IMAGE_MODELS).
               Doit déjà être pullé : `ollama pull <model>`.
        size: 'WIDTHxHEIGHT' demandé à Ollama (souvent ignoré, défaut '1024x1024')
        target_size: 'WIDTHxHEIGHT' final post-resize PIL (ex '1536x864' pour 16:9)
        resize_mode: 'fit' (letterbox, conserve ratio), 'cover' (crop centré),
                     'stretch' (déforme). Défaut 'fit'.
        seed: graine pour reproductibilité (optionnel)
        steps: nombre de steps de diffusion (optionnel, dépend du modèle)
        timeout: secondes max pour l'inférence (défaut 600s = 10 min)

    Returns:
        dict avec image_id, prompt, model, cost_usd, gen_time_s, backend,
        native_size, final_size.
    """
    if not prompt or not isinstance(prompt, str):
        raise ValueError("Prompt requis")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model requis (ex: 'x/flux2-klein:9b')")
    def _parse_size(s: str, label: str) -> tuple[int, int]:
        try:
            w_s, h_s = s.lower().split("x", 1)
            w, h = int(w_s), int(h_s)
            if not (64 <= w <= 8192) or not (64 <= h <= 8192):
                raise ValueError
            return w, h
        except (ValueError, AttributeError):
            raise ValueError(f"{label} invalide: {s!r} (attendu 'WIDTHxHEIGHT', ex '1024x1024')")

    _parse_size(size, "size")
    target_wh: tuple[int, int] | None = None
    if target_size:
        target_wh = _parse_size(target_size, "target_size")
    if resize_mode not in ("fit", "cover", "stretch"):
        raise ValueError(f"resize_mode doit être 'fit'/'cover'/'stretch', reçu {resize_mode!r}")

    _ollama_running_or_raise()

    options: dict = {"size": size}
    if seed is not None:
        options["seed"] = int(seed)
    if steps is not None:
        options["steps"] = int(steps)

    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": options,
    }

    t0 = time.monotonic()
    with httpx.Client(timeout=timeout) as client:
        response = client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
        gen_time = time.monotonic() - t0

        if response.status_code != 200:
            # Surfacer l'erreur upstream telle quelle pour debug.
            try:
                err = response.json().get("error", response.text)
            except Exception:
                err = response.text or f"HTTP {response.status_code}"
            raise RuntimeError(
                f"Ollama a renvoyé une erreur (HTTP {response.status_code}): {err}\n"
                f"Modèle : {model}. Vérifie `ollama list` et `~/.ollama/logs/server.log`."
            )

        try:
            data = response.json()
        except Exception as e:
            raise RuntimeError(
                f"Ollama a renvoyé une réponse non-JSON ({e}). "
                f"Aperçu : {response.text[:300]!r}"
            )

    # Format Ollama 0.24+ : {model, image: <base64 PNG>, total_duration, ...}
    image_b64 = data.get("image")
    if not image_b64:
        raise RuntimeError(
            f"Champ 'image' absent de la réponse Ollama. "
            f"Clés présentes : {list(data.keys())}. "
            f"`done_reason`={data.get('done_reason')!r}"
        )
    try:
        image_bytes = base64.b64decode(image_b64)
    except Exception as e:
        raise RuntimeError(f"Décodage base64 échoué : {e}")

    # Lire l'image (Image.open puis verify détruit l'objet → on rouvre pour size)
    try:
        with Image.open(io.BytesIO(image_bytes)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(image_bytes)) as img:
            img.load()
            native_size = img.size  # (w, h)
            final_img = img
            # Resize si demandé et différent
            if target_wh and target_wh != native_size:
                final_img = _resize_image(img, target_wh, resize_mode)
            # Réencoder en PNG (toujours, pour cohérence cache + métadonnées)
            buf = io.BytesIO()
            final_img.save(buf, format="PNG", optimize=True)
            image_bytes = buf.getvalue()
            final_size = final_img.size
    except Exception as e:
        raise RuntimeError(f"Erreur traitement image Ollama: {e}")

    # Durées rapportées par Ollama (nanosecondes → secondes)
    total_ns = data.get("total_duration") or 0
    load_ns = data.get("load_duration") or 0
    ollama_total_s = round(total_ns / 1e9, 2) if total_ns else None
    ollama_load_s = round(load_ns / 1e9, 2) if load_ns else None

    image_id = cache.save_image(
        image_bytes,
        metadata={
            "model": f"ollama:{model}",
            "prompt": prompt,
            "operation": "generate_image_ollama",
            "backend": "ollama-mlx",
            "size": size,
            "target_size": target_size,
            "resize_mode": resize_mode if target_wh else None,
            "native_size": f"{native_size[0]}x{native_size[1]}",
            "final_size": f"{final_size[0]}x{final_size[1]}",
            "seed": seed,
            "steps": steps,
            "gen_time_s": round(gen_time, 2),
            "ollama_total_s": ollama_total_s,
            "ollama_load_s": ollama_load_s,
        },
    )
    cache.log_cost(f"ollama:{model}", 0.0, prompt, image_id)
    return {
        "image_id": image_id,
        "prompt": prompt,
        "model": f"ollama:{model}",
        "cost_usd": 0.0,
        "backend": "ollama-mlx",
        "native_size": f"{native_size[0]}x{native_size[1]}",
        "final_size": f"{final_size[0]}x{final_size[1]}",
        "gen_time_s": round(gen_time, 2),
        "ollama_total_s": ollama_total_s,
        "ollama_load_s": ollama_load_s,
    }


def _resize_image(img: Image.Image, target_wh: tuple[int, int], mode: str) -> Image.Image:
    """Redimensionne `img` vers `target_wh` selon le mode.

    - 'fit'    : letterbox blanc, préserve ratio, image entière visible
    - 'cover'  : crop centré, préserve ratio, remplit le canvas
    - 'stretch': déforme pour atteindre exactement la taille
    """
    tw, th = target_wh
    iw, ih = img.size
    if mode == "stretch":
        return img.resize((tw, th), Image.LANCZOS)

    if mode == "fit":
        # Scale pour rentrer dans le canvas, ajoute des bandes blanches
        scale = min(tw / iw, th / ih)
        nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
        scaled = img.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGB", (tw, th), (255, 255, 255))
        canvas.paste(scaled, ((tw - nw) // 2, (th - nh) // 2))
        return canvas

    # cover : scale pour remplir, crop centré
    scale = max(tw / iw, th / ih)
    nw, nh = max(1, int(round(iw * scale))), max(1, int(round(ih * scale)))
    scaled = img.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = (nh - th) // 2
    return scaled.crop((left, top, left + tw, top + th))


def list_ollama_image_models() -> dict:
    """Liste les modèles Ollama installés que l'on peut utiliser pour générer une image.

    Croise `ollama list` avec KNOWN_IMAGE_MODELS pour identifier les modèles
    image-gen. Tout modèle dont le nom commence par 'x/' est considéré comme
    candidat image-gen (convention upstream Ollama).
    """
    if not _is_ollama_running():
        return {
            "ollama_running": False,
            "installed": [],
            "known_image_models": KNOWN_IMAGE_MODELS,
            "hint": "Lance `ollama serve` puis `ollama pull x/flux2-klein:9b`.",
        }

    installed = []
    try:
        with httpx.Client(timeout=5.0) as client:
            r = client.get(f"{OLLAMA_BASE_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
        for m in data.get("models", []):
            name = m.get("name", "")
            # Convention Ollama : namespace 'x/' = modèles spécialisés (souvent image-gen).
            is_image = name in KNOWN_IMAGE_MODELS or name.startswith("x/")
            installed.append({
                "name": name,
                "size_bytes": m.get("size"),
                "modified_at": m.get("modified_at"),
                "is_image_candidate": is_image,
                "description": KNOWN_IMAGE_MODELS.get(name, ""),
            })
    except Exception as e:
        return {
            "ollama_running": True,
            "error": f"Impossible de lister les modèles : {e}",
            "installed": [],
            "known_image_models": KNOWN_IMAGE_MODELS,
        }

    image_candidates = [m for m in installed if m["is_image_candidate"]]
    return {
        "ollama_running": True,
        "installed": installed,
        "image_candidates": image_candidates,
        "known_image_models": KNOWN_IMAGE_MODELS,
        "default_model": DEFAULT_MODEL,
    }


def pull_ollama_model(model: str = DEFAULT_MODEL, timeout: float = 1800.0) -> dict:
    """Télécharge un modèle Ollama. Wrapper non-streaming sur `ollama pull`.

    Note : pour un grand modèle (Flux.2 Klein 9B ≈ 11 GB), le premier pull peut
    prendre 10-30 min selon la bande passante. timeout par défaut = 30 min.
    """
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model requis")
    if not shutil.which("ollama"):
        raise RuntimeError(
            "Binaire `ollama` introuvable dans le PATH. "
            "Installer depuis https://ollama.com/download."
        )

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            ["ollama", "pull", model],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"`ollama pull {model}` a dépassé {timeout}s")
    elapsed = time.monotonic() - t0

    if proc.returncode != 0:
        raise RuntimeError(
            f"`ollama pull {model}` a échoué (exit {proc.returncode}):\n"
            f"stderr: {proc.stderr.strip()}\n"
            f"stdout: {proc.stdout.strip()}"
        )
    return {
        "model": model,
        "pulled": True,
        "elapsed_s": round(elapsed, 1),
        "stdout_tail": proc.stdout.strip().splitlines()[-3:] if proc.stdout else [],
    }
