"""Wrapper autour de replicate.run + download — seam mockable pour les tests."""
from __future__ import annotations

import base64
from typing import Any

import replicate
import requests

import config


def call_replicate(model_id: str, input_dict: dict) -> Any:
    """Appel direct à replicate.run. Mockable via monkeypatch dans les tests."""
    config.require_replicate_token()
    import os
    os.environ["REPLICATE_API_TOKEN"] = config.REPLICATE_API_TOKEN
    return replicate.run(model_id, input=input_dict)


def extract_url(output: Any) -> str:
    """Normalise les différents formats de retour Replicate en string URL.

    Gère : list[str], list[FileOutput], FileOutput (.url property), str.
    Régression connue : FileOutput.url est une PROPRIÉTÉ, pas une méthode.
    """
    if isinstance(output, list):
        if not output:
            raise RuntimeError("Replicate a retourné une liste vide")
        first = output[0]
        return first.url if hasattr(first, "url") else str(first)
    if hasattr(output, "url"):
        return output.url  # property, pas méthode
    return str(output)


def download_image(url: str, timeout: int = 120) -> bytes:
    """Télécharge le résultat. Mockable pour les tests."""
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content


def to_data_uri(image_bytes: bytes, mime: str = "image/png") -> str:
    """Encode les bytes en data URI base64 — pour les modèles qui exigent ce format."""
    b64 = base64.b64encode(image_bytes).decode("utf-8")
    return f"data:{mime};base64,{b64}"


def to_base64(image_bytes: bytes) -> str:
    """Encode bytes → base64 plain (sans préfixe data: URI)."""
    return base64.b64encode(image_bytes).decode("utf-8")
