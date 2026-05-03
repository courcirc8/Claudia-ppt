"""Configuration globale — chargement env + chemins cache."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Charger .env si présent (au démarrage MCP, le user doit avoir configuré son token)
try:
    from dotenv import load_dotenv
    _ENV_PATH = Path(__file__).parent / ".env"
    if _ENV_PATH.exists():
        load_dotenv(_ENV_PATH)
except ImportError:
    pass

# Token Replicate (requis pour tous les outils backend Replicate)
REPLICATE_API_TOKEN = os.getenv("REPLICATE_API_TOKEN", "")

# Pollinations (free fallback) — pas de token nécessaire
POLLINATIONS_BASE_URL = "https://image.pollinations.ai/prompt"

# Cache content-addressed
CACHE_DIR = Path(os.getenv("IMAGE_GEN_CACHE", str(Path.home() / ".cache" / "image-gen")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Costs ledger (append-only JSONL)
COSTS_PATH = CACHE_DIR / "costs.jsonl"

# Désactiver l'enhancement automatique des prompts
AUTO_ENHANCE_PROMPT = os.getenv("AUTO_ENHANCE_PROMPT", "true").lower() in ("true", "1", "yes")


def require_replicate_token() -> str:
    """Retourne le token, ou raise une erreur claire avec marche-à-suivre."""
    if not REPLICATE_API_TOKEN:
        raise RuntimeError(
            "REPLICATE_API_TOKEN manquant.\n\n"
            "Marche à suivre :\n"
            "  1. Récupère un token sur https://replicate.com/account/api-tokens\n"
            "  2. cp env.example .env  (dans le dossier ImageGen/)\n"
            "  3. Éditer .env : REPLICATE_API_TOKEN=r8_xxx\n"
            "  4. Redémarrer le MCP\n\n"
            "Sinon, utilise generate_image_free (backend Pollinations gratuit, sans token)."
        )
    return REPLICATE_API_TOKEN


def warn_if_no_token() -> None:
    """Imprime un warning au démarrage si pas de token (mais ne bloque pas)."""
    if not REPLICATE_API_TOKEN:
        print(
            "⚠️  REPLICATE_API_TOKEN absent — seul `generate_image_free` (Pollinations) "
            "fonctionnera. Voir env.example pour configurer.",
            file=sys.stderr,
        )
