"""Sélection automatique du meilleur modèle selon la complexité du prompt.

Heuristique :
- Score les signaux qui indiquent un besoin de précision/texte → gpt-image-2
- Sinon, route vers seedream-4.5 (rapport qualité/prix optimal pour visuels)

Pas de LLM appelé — pure analyse de chaînes, gratuit et instantané.
"""
from __future__ import annotations

# Mots-clés qui signalent un besoin de fidélité à un brief précis
# (texte intégré, schémas, instructions strictes — gpt-image-2 excelle ici)
_TEXT_KEYWORDS = (
    "text", "texte", "label", "title", "titre", "caption", "headline",
    "infographic", "infographie", "diagram", "diagramme", "schema", "schéma",
    "chart", "graph", "graphique", "table", "tableau", "annotation", "callout",
    "lettering", "typography", "typographie", "word", "mot",
    "logo with", "logo avec", "writing", "written",
)

_LAYOUT_KEYWORDS = (
    "bullet", "puce", "numbered", "numéroté", "step ", "étape",
    "section", "left side", "right side", "à gauche", "à droite",
    "top of", "bottom of", "en haut", "en bas", "corner", "coin",
    "centered", "centré", "arranged", "agencé",
    "grid", "grille", "row", "rangée", "column", "colonne",
)

_CONSTRAINT_KEYWORDS = (
    "preserve", "préserver", "keep ", "garder",
    "must contain", "must include", "doit contenir", "doit inclure",
    "exactly", "exactement", "with the following", "avec les éléments suivants",
    "do not", "ne pas", "ne doit pas",
)


def score_complexity(prompt: str) -> int:
    """Retourne un score d'intensité texte/instruction du prompt.

    Score interprété par auto_select_model :
    - 0-1 : visuel pur → seedream
    - 2+  : instructions précises → gpt-image-2
    """
    if not isinstance(prompt, str):
        return 0
    p = prompt.lower()
    score = 0

    # Présence de keywords texte (signal le plus fort)
    if any(k in p for k in _TEXT_KEYWORDS):
        score += 3

    # Layout explicite (besoin de positionnement)
    if any(k in p for k in _LAYOUT_KEYWORDS):
        score += 1

    # Contraintes strictes
    if any(k in p for k in _CONSTRAINT_KEYWORDS):
        score += 2

    # Prompt long et détaillé
    if len(prompt) > 200:
        score += 1

    # Multi-clauses (>6 virgules → plusieurs éléments à gérer)
    if prompt.count(",") > 6:
        score += 1

    return score


def auto_select_model(prompt: str) -> tuple[str, str]:
    """Choisit le modèle optimal pour ce prompt.

    Retourne (model_key, raison) — la raison est utile pour le logging
    et la transparence côté agent.
    """
    score = score_complexity(prompt)

    if score >= 2:
        # Prompt complexe ou avec texte : gpt-image-2 excelle
        return ("gpt-image-2", f"prompt complexe (score={score}) → gpt-image-2")

    # Prompt visuel simple : seedream-4.5 (qualité/prix optimal pour PPT en 2K)
    return ("seedream-4.5", f"prompt visuel simple (score={score}) → seedream-4.5")


def auto_select_quality_for_role(role: str | None = None) -> str:
    """Suggère une qualité gpt-image-2 selon le rôle PPT.

    high réservé aux covers et infographies (lisibilité du texte critique).
    medium suffit pour le reste.
    """
    if role in ("cover", "infographic"):
        return "high"
    return "medium"
