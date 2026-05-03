# Migration v1 → v2

## Résumé

| Aspect | v1 | v2 |
|--------|----|----|
| Backend | Pollinations gratuit | Replicate (8 modèles) + fallback Pollinations |
| Outils | 1 (`generate_image`) | **19** |
| Token requis | Non | Oui (mais fallback gratuit dispo) |
| Coût | $0 | $0.006-$0.21 / image |
| Cache | Aucun | Content-addressed (sha256) |
| Tracking coût | Non | `get_costs` |
| Tests | 0 | 122 |

## Compatibilité descendante

L'outil v1 `generate_image` (sans paramètres) avait cette signature :

```python
generate_image(prompt, width=1024, height=1024, model="flux", save_path=None)
```

En v2, l'équivalent direct est **`generate_image_free`** (Pollinations) :

```python
generate_image_free(prompt, width=1024, height=1024, model="flux")
```

⚠️ Différences :
- `save_path` retiré : v2 retourne un `image_id` ; pour sauver localement, utilise `get_image(image_id)` puis écris le base64 où tu veux. Plus sûr (pas de path traversal possible côté serveur).
- Retour : `{image_id, prompt, model, cost_usd}` au lieu d'un mix `TextContent + ImageContent`.

L'outil v2 **`generate_image`** (sans suffix `_free`) est plus puissant mais utilise Replicate (token requis).

## Steps de migration

1. **Récupérer un token Replicate** :
   - https://replicate.com/account/api-tokens
   - Crédit gratuit de démarrage
2. **Configurer `.env`** :
   ```bash
   cp env.example .env
   # éditer : REPLICATE_API_TOKEN=r8_xxx
   ```
3. **Installer les nouvelles dépendances** :
   ```bash
   pip install -r requirements.txt
   ```
4. **Tester** :
   ```bash
   ./run_tests.sh    # 122 tests, ~2.5s
   ```
5. **Aucun changement nécessaire dans `~/.cursor/mcp.json`** — le path et la commande sont identiques.

## L'ancien serveur reste accessible

Le fichier original est conservé sous [`server_v1_pollinations.py`](server_v1_pollinations.py). Si tu veux temporairement revenir à v1, dans `~/.cursor/mcp.json` :

```json
"args": ["<path-to-Claudia-ppt>/servers/image-gen/server_v1_pollinations.py"]
```

## Quoi faire de tes prompts existants ?

Si tu utilisais déjà `generate_image` v1 dans des workflows, deux options :

**Option A (recommandée)** : passer directement à v2 avec un meilleur modèle :
```python
# v1
generate_image("a sunset", width=1024, height=1024, model="flux")

# v2 équivalent qualité
generate_image("a sunset", model="gpt-image-2", max_resolution="medium")
# ou : model="flux-pro" pour rester proche du look v1 mais en pro
```

**Option B (zéro coût)** : utiliser le fallback Pollinations en v2 :
```python
# Comportement quasi identique à v1
generate_image_free("a sunset", width=1024, height=1024, model="flux")
```

## Coûts à anticiper

| Volume | Modèle médian (seedream-4.5 2K) | gpt-image-2 medium | Pollinations |
|--------|---------------------------------|--------------------|--------------|
| 10 images | $0.60 | $0.53 | $0.00 |
| 100 images | $6.00 | $5.30 | $0.00 |
| 1000 images | $60 | $53 | $0.00 |

Tu peux suivre la dépense en temps réel via `get_costs`.
