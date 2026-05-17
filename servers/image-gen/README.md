# 🎨 image-gen — MCP Génération d'Images v2.1

MCP serveur de génération d'image pour Claude Code / Cursor, backed par **Replicate** (8 modèles SOTA) **+ Ollama MLX local** (Apple Silicon, coût $0), conçu pour automatiser la production visuelle de présentations PowerPoint.

**22 outils** : génération cloud + local, retouche, post-traitement, gestion, cohérence stylistique.

## 🚀 Installation

```bash
# 1. Token Replicate (https://replicate.com/account/api-tokens)
cp env.example .env
# Éditer .env : REPLICATE_API_TOKEN=r8_xxx

# 2. Dépendances Python
pip install -r requirements.txt
```

## 🔌 Configuration MCP (Cursor)

Dans `~/.cursor/mcp.json` :

```json
"image-gen": {
  "command": "<path-to-venv>/bin/python",
  "args": ["<path-to-Claudia-ppt>/servers/image-gen/server.py"],
  "cwd": "<path-to-Claudia-ppt>/servers/image-gen"
}
```

> Remplace `<path-to-venv>` par le chemin de ton virtualenv Python et
> `<path-to-Claudia-ppt>` par le chemin où tu as cloné ce repo.

## 🧰 Les 19 outils

### Génération (5)

| Outil | Cas d'usage |
|-------|-------------|
| `generate_image` | Text → image (8 modèles, 8 ratios, qualité réglable) |
| `image_to_image` | Transforme une image existante via prompt |
| `generate_batch` | N images cohérentes avec optionnel style ref |
| `generate_for_slide` | Preset par rôle PPT : `cover`, `icon`, `photo`, `infographic`, `headshot`, `background`, `section`, `illustration` |
| `generate_image_free` | Fallback gratuit Pollinations (sans token) |
| `generate_image_ollama` | **Local Apple Silicon via Ollama MLX** ($0, FLUX.2 Klein 9B) |
| `list_ollama_image_models` | Liste les modèles image-gen Ollama installés |
| `pull_ollama_model` | Télécharge un modèle Ollama (wrapper `ollama pull`) |

### Édition (4)

| Outil | Cas d'usage |
|-------|-------------|
| `inpaint` | Repeint une zone masquée (mask PNG noir/blanc) |
| `replace_background` | Change le fond, garde le sujet |
| `outpaint` | Étend le canvas dans une direction |
| `register_image` | Importe une image utilisateur dans le cache |

### Post-traitement (4)

| Outil | Cas d'usage |
|-------|-------------|
| `remove_background` | PNG transparent (icônes/logos isolés) |
| `upscale` | 2× ou 4×, mode `crisp` ou `creative` |
| `vectorize` | Raster → SVG éditable PPT (via Recraft) |
| `seamless_tile` | Rend l'image tilable. $0, local PIL. |

### Gestion (4)

| Outil | Cas d'usage |
|-------|-------------|
| `list_images` | 50 dernières images générées |
| `get_image` | Récupère base64 + métadonnées d'une image |
| `delete_image` | Supprime du cache |
| `get_costs` | Total dépensé + breakdown par modèle |

### Cohérence stylistique (1)

| Outil | Cas d'usage |
|-------|-------------|
| `apply_style` | Génère en imitant le style d'une image de référence |

### Bonus (1)

| Outil | Cas d'usage |
|-------|-------------|
| `list_models` | Liste les 7 modèles + capacités |

## 🤖 Modèles supportés

| Clé | Description | Coût/image (USD) |
|-----|-------------|------------------|
| `auto` | **Sélection automatique** selon le prompt (défaut) | variable |
| `gpt-image-2` | OpenAI — qualité réglable, top pour texte/édition | $0.006 / $0.053 / $0.211 |
| `flux-pro` | Black Forest Labs — photo réaliste | $0.040 |
| `seedream` | ByteDance v4 | $0.050 |
| `seedream-4.5` | ByteDance — jusqu'à 4K | $0.040 / $0.060 / $0.100 |
| `seedream-5` | ByteDance v5 lite | $0.035 |
| `nano-banana` | Google | $0.020 |
| `nano-banana-pro` | Google premium | $0.134 |

## 🤖 Sélection automatique (`model="auto"`)

Heuristique pure-string (pas de LLM appelé) qui calcule un score :

| Signal | +Score |
|--------|--------|
| Mots-clés texte (`text`, `label`, `infographic`, `diagram`, `chart`...) | +3 |
| Mots-clés layout (`bullet`, `step`, `corner`, `centered`...) | +1 |
| Contraintes (`preserve`, `keep`, `must contain`...) | +2 |
| Prompt > 200 chars | +1 |
| > 6 virgules | +1 |

**Décision** : `score >= 2` → `gpt-image-2` (text-aware), sinon → `seedream-4.5` (photo/illustration top en 2K).

**Pour les édits d'images existantes** (`image_to_image`, `replace_background`, `inpaint`), le défaut est **toujours `gpt-image-2`** car il excelle à préserver le sujet et suivre des contraintes du type "ne touche pas au visage". L'image source est automatiquement passée en `input_images`.

Le retour inclut `auto_select_reason` pour savoir pourquoi tel modèle a été choisi.

## 🖥️ Génération locale via Ollama MLX (coût $0)

Sur Apple Silicon, **Ollama 0.23.3+** peut exécuter FLUX.2 Klein localement
via MLX. Aucune donnée n'est envoyée en cloud, coût zéro, illimité.

```bash
# 1. Installer Ollama ≥ 0.23.3 (0.23.2 a un panic dans le text-encoder Qwen3)
brew install --cask ollama-app
open -a Ollama

# 2. Pull le modèle (~11 GB, 5-15 min selon BP)
ollama pull x/flux2-klein:9b

# 3. Depuis Claude / Cursor :
#    generate_image_ollama(prompt="...", model="x/flux2-klein:9b")
```

**Modèles supportés** :

| Modèle Ollama | Taille | Vitesse (M-series) |
|---|---|---|
| `x/flux2-klein:9b` | ~11 GB | ~30-60s / image 1024² |
| `x/flux2-klein:4b` | plus petit | plus rapide |
| `x/z-image-turbo` | léger | drafts ultra-rapides |

**Limites actuelles** :
- L'option `size` est ignorée par Ollama 0.24 (sortie 1024×1024 par défaut).
  Pour redimensionner après coup : utiliser `upscale` ou un post-process PIL.
- Nécessite ~12-16 GB RAM unifiée pour Klein 9B.

## 🎨 Workflows PPT typiques

### Cover deck cohérent en 1 commande
```python
cover = generate_for_slide(role="cover", prompt="climate change impact")
slides = generate_batch(
    prompts=["arctic ice melt", "rising sea levels", "extreme weather", ...],
    style_ref_image_id=cover["image_id"],
    orientation="landscape_16_9",
    model="seedream-4.5",
)
# → 1 cover ($0.21) + 9 slides ($0.54) = $0.75 pour un deck complet
```

### Icône SVG éditable PowerPoint
```python
img = generate_for_slide(role="icon", prompt="minimalist fish")
no_bg = remove_background(img["image_id"])
svg = vectorize(no_bg["image_id"])
```

### Photo retouchée
```python
user = register_image(file_path="~/Downloads/portrait.jpg")
clean = replace_background(user["image_id"], "pure white studio backdrop")
hd = upscale(clean["image_id"], factor=2, mode="crisp")
```

### Fond tilable (gratuit)
```python
texture = generate_image("abstract geometric pattern", orientation="square")
tile = seamless_tile(texture["image_id"])
```

## 🛡️ Sécurité

- `safe_image_id` valide les IDs (hex 8-32)
- `safe_filename` rejette `..`, `/`, `\`, leading dots
- `.env` gitignored
- Cache restreint à `~/.cache/image-gen/`

## 🧪 Tests

**122 tests pytest, ~2.5s, zéro appel réseau** :

```bash
./run_tests.sh
```

## 💾 Cache content-addressed

`~/.cache/image-gen/<sha256>.png` + `<sha256>.json`. Déduplique automatiquement les bytes identiques.

## ⚙️ Variables d'environnement

| Var | Défaut | Effet |
|-----|--------|-------|
| `REPLICATE_API_TOKEN` | (requis pour cloud) | Token Replicate |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | URL daemon Ollama (local) |
| `IMAGE_GEN_CACHE` | `~/.cache/image-gen` | Dossier cache |
| `AUTO_ENHANCE_PROMPT` | `true` | Enrichit auto les prompts courts |

## 📦 Migration v1 → v2

Le serveur v1 Pollinations est conservé en [`server_v1_pollinations.py`](server_v1_pollinations.py). La gratuité est intégrée dans v2 via `generate_image_free`. Voir [MIGRATION.md](MIGRATION.md).

## 🔗 Synergies MCP

- **`powerpoint`** — insertion des images générées dans les slides
- **`icon-library`** — icônes templates pour design rapide
- **`ppt-analyzer`** — feedback sur les images insérées
- **RetoucheImage** (UI web) — retouche manuelle interactive

## Versioning

Source unique : fichier `VERSION`. Actuel : **v2.0.0**.
