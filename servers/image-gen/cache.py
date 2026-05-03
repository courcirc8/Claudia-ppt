"""Cache content-addressed — chaque image est stockée sous son sha256."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import config
from safe import safe_image_id


def compute_image_id(data: bytes) -> str:
    """sha256 complet (64 hex chars) — élimine les collisions à 64 bits du tronqué."""
    return hashlib.sha256(data).hexdigest()


def save_image(image_bytes: bytes, metadata: dict, suffix: str = "png") -> str:
    """Sauve l'image + métadonnées dans le cache. Retourne l'image_id (sha256 hex).

    Écriture atomique : on écrit d'abord en .tmp puis rename, donc aucun reader
    ne peut observer un PNG/JSON partiellement écrit.
    """
    image_id = compute_image_id(image_bytes)
    img_path = config.CACHE_DIR / f"{image_id}.{suffix}"
    meta_path = config.CACHE_DIR / f"{image_id}.json"

    # Pas de doublon : si déjà présent ET bytes identiques, on incrémente le compteur.
    # Pour sha256 complet la probabilité de collision est négligeable, mais on vérifie
    # quand même les bytes par défense en profondeur.
    if img_path.exists() and meta_path.exists():
        try:
            existing_bytes = img_path.read_bytes()
            if existing_bytes == image_bytes:
                existing = json.loads(meta_path.read_text(encoding="utf-8"))
                existing["hit_count"] = existing.get("hit_count", 1) + 1
                _atomic_write_text(meta_path, json.dumps(existing, indent=2, ensure_ascii=False))
                return image_id
        except (OSError, json.JSONDecodeError) as e:
            print(f"[cache] avertissement metadata illisible {meta_path}: {e}", file=__import__("sys").stderr)

    _atomic_write_bytes(img_path, image_bytes)
    metadata = {
        **metadata,
        "image_id": image_id,
        "saved_at": time.time(),
        "saved_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "size_bytes": len(image_bytes),
        "suffix": suffix,
        "hit_count": 1,
    }
    _atomic_write_text(meta_path, json.dumps(metadata, indent=2, ensure_ascii=False))
    return image_id


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    import os as _os
    _os.replace(tmp, path)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    import os as _os
    _os.replace(tmp, path)


def get_image_path(image_id: str) -> Path | None:
    """Retourne le path image si présent (n'importe quel suffix), sinon None."""
    image_id = safe_image_id(image_id)
    if not image_id:
        return None
    for suffix in ("png", "jpg", "jpeg", "webp", "svg"):
        p = config.CACHE_DIR / f"{image_id}.{suffix}"
        if p.exists():
            return p
    return None


def get_metadata(image_id: str) -> dict | None:
    image_id = safe_image_id(image_id)
    if not image_id:
        return None
    p = config.CACHE_DIR / f"{image_id}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def delete_image(image_id: str) -> bool:
    """Supprime image + métadonnées. Retourne True si quelque chose a été supprimé."""
    image_id = safe_image_id(image_id)
    if not image_id:
        return False
    deleted = False
    for suffix in ("png", "jpg", "jpeg", "webp", "svg", "json"):
        p = config.CACHE_DIR / f"{image_id}.{suffix}"
        if p.exists():
            p.unlink()
            deleted = True
    return deleted


def list_images(limit: int = 50, model_filter: str | None = None) -> list[dict]:
    """Liste les N dernières images générées, triées par saved_at descendant."""
    metas = []
    for meta_file in config.CACHE_DIR.glob("*.json"):
        if meta_file.name == "costs.jsonl":
            continue
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            if model_filter and data.get("model") != model_filter:
                continue
            metas.append(data)
        except Exception:
            continue
    metas.sort(key=lambda m: m.get("saved_at", 0), reverse=True)
    return metas[:limit]


def log_cost(model_key: str, cost_usd: float, prompt: str, image_id: str | None = None) -> None:
    """Append une ligne au ledger costs.jsonl (atomic via fcntl lock)."""
    import fcntl
    entry = {
        "ts": time.time(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "model": model_key,
        "cost_usd": round(cost_usd, 4),
        "prompt": prompt[:200],
        "image_id": image_id,
    }
    line = json.dumps(entry, ensure_ascii=False) + "\n"
    with open(config.COSTS_PATH, "a", encoding="utf-8") as f:
        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            f.write(line)
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


def get_cost_summary() -> dict:
    """Retourne {total: float, by_model: {key: float}, count: int} depuis le ledger."""
    if not config.COSTS_PATH.exists():
        return {"total_usd": 0.0, "by_model": {}, "count": 0}
    total = 0.0
    by_model: dict[str, float] = {}
    count = 0
    with open(config.COSTS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            cost = float(e.get("cost_usd", 0))
            total += cost
            m = e.get("model", "unknown")
            by_model[m] = by_model.get(m, 0.0) + cost
            count += 1
    return {
        "total_usd": round(total, 4),
        "by_model": {k: round(v, 4) for k, v in by_model.items()},
        "count": count,
    }


def get_today_spend_usd() -> float:
    """Somme des coûts loggués depuis 00:00:00 UTC aujourd'hui."""
    if not config.COSTS_PATH.exists():
        return 0.0
    today = time.strftime("%Y-%m-%d", time.gmtime())
    total = 0.0
    with open(config.COSTS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except Exception:
                continue
            ts_iso = e.get("ts_iso") or ""
            if ts_iso.startswith(today):
                total += float(e.get("cost_usd", 0))
    return round(total, 4)


def enforce_daily_cap(estimated_cost_usd: float) -> None:
    """Lève RuntimeError si l'appel ferait dépasser MAX_DAILY_USD.

    MAX_DAILY_USD=0 désactive le plafond.
    """
    cap = float(getattr(config, "MAX_DAILY_USD", 0) or 0)
    if cap <= 0:
        return
    spent = get_today_spend_usd()
    projected = spent + max(0.0, float(estimated_cost_usd))
    if projected > cap:
        raise RuntimeError(
            f"Plafond journalier atteint : déjà ${spent:.2f} dépensés, "
            f"cet appel ajouterait ${estimated_cost_usd:.2f} → ${projected:.2f} "
            f"(plafond ${cap:.2f}). Définir MAX_DAILY_USD=0 pour désactiver, "
            "ou attendre minuit UTC."
        )
