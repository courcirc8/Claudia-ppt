"""Helpers de sécurité — validation des noms de fichiers / IDs."""
from __future__ import annotations

import re

_IMAGE_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


def safe_filename(name) -> str:
    """Retourne le nom validé (basename uniquement) ou '' s'il est invalide.

    Refuse: chaînes vides, séparateurs ('/', '\\'), '..', noms cachés ('.foo'),
    valeurs non-string. Défense en profondeur.
    """
    if not isinstance(name, str):
        return ""
    name = name.strip()
    if not name:
        return ""
    if "/" in name or "\\" in name:
        return ""
    if ".." in name:
        return ""
    if name.startswith("."):
        return ""
    return name


def safe_filename_list(names) -> list[str]:
    """Filtre une liste de noms — ne garde que les valides."""
    if not isinstance(names, list):
        return []
    return [safe_filename(n) for n in names if safe_filename(n)]


def safe_image_id(image_id) -> str:
    """Valide qu'un image_id est un hash hex (8-32 chars). Sinon ''."""
    if not isinstance(image_id, str):
        return ""
    image_id = image_id.strip().lower()
    if not _IMAGE_ID_RE.match(image_id):
        return ""
    return image_id
