"""Outils de gestion : list/get/delete + tracking de coût."""
from __future__ import annotations

import cache
from replicate_client import to_base64
from safe import safe_image_id


def list_images(limit: int = 50, model_filter: str | None = None) -> dict:
    """Liste les N dernières images générées (métadonnées uniquement, pas les bytes).

    Args:
        limit: nombre max d'entrées (défaut 50, max 200)
        model_filter: ne garde que les images d'un modèle spécifique
    """
    limit = max(1, min(int(limit), 200))
    items = cache.list_images(limit=limit, model_filter=model_filter)
    # Champs résumés pour ne pas saturer la réponse MCP
    summary = [
        {
            "image_id": m.get("image_id"),
            "model": m.get("model"),
            "operation": m.get("operation"),
            "prompt": (m.get("prompt") or "")[:100],
            "saved_at": m.get("saved_at_iso"),
            "size_bytes": m.get("size_bytes"),
        }
        for m in items
    ]
    return {"count": len(summary), "images": summary}


def get_image(image_id: str, include_base64: bool = True) -> dict:
    """Renvoie une image (métadonnées + base64). Idéal pour passer l'image à un autre MCP."""
    sid = safe_image_id(image_id)
    if not sid:
        return {"success": False, "message": "image_id invalide"}
    metadata = cache.get_metadata(sid)
    if not metadata:
        return {"success": False, "message": f"Image introuvable: {image_id}"}
    path = cache.get_image_path(sid)
    # Don't echo absolute filesystem paths back to MCP callers — basename only.
    result = {
        "success": True,
        "image_id": sid,
        "metadata": metadata,
        "filename": path.name if path else None,
    }
    if include_base64 and path:
        result["base64"] = to_base64(path.read_bytes())
        result["mime_type"] = f"image/{metadata.get('suffix', 'png')}"
    return result


def delete_image(image_id: str) -> dict:
    sid = safe_image_id(image_id)
    if not sid:
        return {"success": False, "message": "image_id invalide"}
    deleted = cache.delete_image(sid)
    return {
        "success": deleted,
        "image_id": sid,
        "message": "Supprimée" if deleted else "Aucun fichier trouvé",
    }


def get_costs() -> dict:
    """Retourne {total_usd, by_model: {key: usd}, count}."""
    return cache.get_cost_summary()
