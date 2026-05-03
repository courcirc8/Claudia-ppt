"""Enrichissement automatique des prompts courts.

Heuristique simple (pas de LLM appelé pour rester rapide et gratuit) :
- ajoute des qualificatifs photo si le prompt est très court
- préserve les prompts longs/détaillés tels quels
- désactivable via AUTO_ENHANCE_PROMPT=false ou enhance=False param
"""
from __future__ import annotations

# Suffix professionnel ajouté aux prompts courts
_PRO_SUFFIX = (
    ", professional photography, sharp focus, high detail, "
    "studio lighting, commercial quality, 8k"
)

# Mots-clés signalant que l'utilisateur a déjà donné des instructions stylistiques
_STYLE_MARKERS = (
    "photography", "photo", "cinematic", "anime", "illustration", "painting",
    "rendered", "render", "3d", "vector", "logo", "icon", "minimalist", "flat",
    "studio", "lighting", "watercolor", "oil painting", "sketch", "concept art",
)


def enhance_prompt(prompt: str, enhance: bool = True) -> str:
    """Retourne le prompt enrichi si enhance=True et qu'il est court/générique.

    - prompt court (< 40 chars) sans markers stylistiques → ajoute le suffix pro
    - sinon retourne tel quel
    """
    if not enhance or not isinstance(prompt, str):
        return prompt or ""

    prompt = prompt.strip()
    if not prompt:
        return prompt

    lowered = prompt.lower()

    # Si l'utilisateur a déjà des markers de style, ne pas toucher
    if any(marker in lowered for marker in _STYLE_MARKERS):
        return prompt

    # Si le prompt est déjà long et détaillé, l'utilisateur sait ce qu'il veut
    if len(prompt) > 80:
        return prompt

    return prompt + _PRO_SUFFIX
