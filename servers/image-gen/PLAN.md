# Plan — Évolution `image-gen` v1 → v2

## Constat de départ

`image-gen` actuel : **141 lignes**, **un seul outil** (`generate_image`), backend Pollinations gratuit (pas de clé API). Sympa pour démarrer, insuffisant pour la création de PPT pro :
- pas de retouche d'image existante (inpaint, BG-remove…)
- pas d'upscale, pas de vectorisation (pas d'icônes SVG)
- pas de gestion de cohérence visuelle (style refs)
- pas de cache (chaque appel retape sur l'API)
- aucune métadonnée persistée (impossible de retravailler une image)
- 2 modèles seulement (Flux/Turbo, qualité Pollinations limitée)

Comparé aux MCPs pro identifiés ([Recraft 16 tools](https://github.com/BartWaardenburg/recraft-mcp-server), [Flux Studio](https://glama.ai/mcp/servers/jmanhype/mcp-flux-studio), [shinpr/mcp-image](https://github.com/shinpr/mcp-image)), on est très en retrait.

## Objectif v2

Un MCP qu'un agent peut utiliser pour **automatiser la création visuelle d'un deck PPT du début à la fin** : génération, retouche, déclinaisons stylistiques cohérentes, et toutes les opérations de post-traitement.

Backend **Replicate** (cohérent avec `RetoucheImage`, mêmes 8 modèles + token déjà configuré dans `.env`).

---

## 🧰 Inventaire des 15 outils proposés

Catégorisés en 5 groupes. Chaque outil a un nom court, des params nommés, retourne un `image_id` + base64 + métadonnées.

### A. Génération (3 outils)

| Outil | Rôle | Params clés |
|-------|------|-------------|
| `generate_image` | Text → image | `prompt`, `model`, `aspect_ratio`, `quality`/`max_resolution`, `style?`, `seed?` |
| `image_to_image` | Transform image existante via prompt | `image_id`, `prompt`, `strength` (0-1), `model` |
| `generate_batch` | N images cohérentes même style (cover + 8 slides) | `prompts[]`, `style_ref?`, `aspect_ratio`, `model` |

**Modèles dispo (port direct depuis RetoucheImage `def_prompt.json`) :**
- `gpt-image-2` (qualité éditable, défaut medium)
- `flux-pro`, `seedream-4`, `seedream-4.5`, `seedream-5-lite`
- `nano-banana`, `nano-banana-pro`
- `clarity-upscaler` (réservé pour `upscale`)

**Capacités enregistrées par modèle** (cf. table actuelle dans simple_gui.py) : ratios supportés, mode résolution (pixels libres / size enum / quality enum), prix unitaire.

### B. Édition (3 outils)

| Outil | Rôle | Params clés |
|-------|------|-------------|
| `inpaint` | Remplir une zone masquée d'une image | `image_id`, `mask` (PNG noir/blanc), `prompt` |
| `replace_background` | Changer le fond, garder le sujet | `image_id`, `prompt` (ou `transparent: true`) |
| `outpaint` | Étendre le canvas | `image_id`, `direction` (`top`/`right`/`bottom`/`left`/`all`), `pixels`, `prompt?` |

### C. Post-traitement (4 outils)

| Outil | Rôle | Params clés |
|-------|------|-------------|
| `remove_background` | PNG transparent (icônes, logos isolés) | `image_id` |
| `upscale` | 2× ou 4×, mode `crisp` (réaliste) ou `creative` (ajout détails) | `image_id`, `factor`, `mode` |
| `vectorize` | Raster → SVG (icônes vectorielles éditables PPT) | `image_id` |
| `seamless_tile` | Rend une image tilable pour fond de slide répétitif | `image_id` |

### D. Gestion (4 outils)

| Outil | Rôle | Params clés |
|-------|------|-------------|
| `list_images` | 50 dernières images avec IDs, prompts, timestamps, modèles | `since?`, `model_filter?` |
| `get_image` | Renvoie base64 + métadonnées complètes | `image_id` |
| `delete_image` | Supprime du cache + métadonnées | `image_id` |
| `get_costs` | Total dépensé + breakdown par modèle (depuis le démarrage) | aucun |

### E. Cohérence stylistique (1 outil)

| Outil | Rôle | Params clés |
|-------|------|-------------|
| `apply_style` | Reproduit le style d'une image de référence sur un nouveau prompt | `style_ref_image_id`, `prompt` |

---

## 📁 Architecture cible

```
ImageGen/
├── server.py                    # Entry FastMCP, register tools
├── config.py                    # Token loading, env_file pattern
├── models.py                    # Registry des 8 modèles + capacités + tarifs
├── cache.py                     # Cache content-addressed (sha256)
├── safe.py                      # safe_filename (réutilisé de RetoucheImage)
├── prompt_enhancer.py           # Optionnel : enrichit les prompts courts
├── tools/
│   ├── __init__.py
│   ├── generate.py              # generate_image, image_to_image, generate_batch
│   ├── edit.py                  # inpaint, replace_background, outpaint
│   ├── process.py               # remove_background, upscale, vectorize, seamless_tile
│   ├── manage.py                # list_images, get_image, delete_image, get_costs
│   └── style.py                 # apply_style
├── tests/
│   ├── conftest.py              # Mocked replicate.run, sandbox cache dir
│   ├── test_models.py           # Registry cohérent (capacités vs prix vs def_prompt)
│   ├── test_generate.py         # 3 outils generation, dispatch correct par modèle
│   ├── test_edit.py             # 3 outils édition
│   ├── test_process.py          # 4 outils post-traitement
│   ├── test_manage.py           # cache hit/miss, list, delete, costs
│   ├── test_security.py         # path traversal sur tout filename input
│   └── test_integration.py      # End-to-end mocked : generate → upscale → save
├── README.md                    # 15 outils documentés + workflows PPT
├── MIGRATION.md                 # Migration v1 → v2 (générateur Pollinations toujours dispo via flag)
├── env.example                  # REPLICATE_API_TOKEN
├── requirements.txt             # mcp, httpx, replicate, pillow, python-dotenv, pytest
└── run_tests.sh
```

**Cache** : `~/.cache/image-gen/<sha256>.png` + `~/.cache/image-gen/<sha256>.json` (métadonnées). ID = 16 premiers chars du sha256 (collision quasi-nulle, lisible).

**Coût tracking** : `~/.cache/image-gen/costs.jsonl` — append-only, une ligne par appel, total recalculé à la volée.

---

## 🎨 Workflows PPT que ça débloque

Avec ces 15 outils + le MCP `powerpoint` + `icon-library` existants, un agent peut produire un deck complet en **un seul prompt utilisateur** :

### Workflow 1 — "Crée un deck de 10 slides sur les fisheries"
1. `generate_batch(prompts=["fisheries cover", "ocean warming", "boat fleet", ...], style_ref=None, aspect_ratio="16:9", model="seedream-4.5")` → 10 IDs
2. `apply_style(style_ref=cover_id, prompt=...)` pour homogénéiser
3. PowerPoint MCP insère chaque image à la bonne slide

### Workflow 2 — "Icône de poisson stylisée pour la slide 4"
1. `generate_image(prompt="minimalist fish icon, flat design, blue", aspect_ratio="1:1", model="recraft-v3")` 
2. `remove_background(image_id)` → PNG transparent
3. `vectorize(image_id)` → SVG éditable
4. PowerPoint MCP insère le SVG (qui reste éditable)

### Workflow 3 — "Photo de produit retouchée pour le slide cover"
1. User upload → `register_image(file)` → `image_id`
2. `replace_background(image_id, prompt="pure white studio")`
3. `upscale(image_id, factor=2, mode="crisp")`
4. PowerPoint cover

### Workflow 4 — "Fond de slide répétitif pour template"
1. `generate_image(prompt="abstract geometric pattern", aspect_ratio="1:1", model="flux-pro")`
2. `seamless_tile(image_id)` → motif tilable
3. PowerPoint set_slide_background

---

## 💰 Estimation de coût (USD/image, port depuis RetoucheImage)

| Modèle | Coût | Usage typique PPT |
|--------|------|-------------------|
| `nano-banana` | $0.020 | Brouillons, itérations rapides |
| `seedream-5-lite` | $0.035 | Photos + illustrations standard |
| `flux-pro` | $0.040 | Photos réalistes pro |
| `gpt-image-2 medium` | $0.053 | Édition + texte précis sur image |
| `seedream-4.5 (2K)` | $0.060 | Slides en haute qualité |
| `nano-banana-pro` | $0.134 | Photos premium |
| `gpt-image-2 high` | $0.211 | Cover slide finale |
| `clarity` | ~$0.020-0.10 | Upscale |

**Deck typique 10 slides en seedream-4.5 = ~$0.60.** Tracking via `get_costs`.

---

## 🛡️ Sécurité (port depuis RetoucheImage)

- `safe_filename()` réutilisé pour tout `image_id`/`save_path` côté outils
- `REPLICATE_API_TOKEN` lu via `python-dotenv` depuis `.env` (gitignored)
- Validation des params via JSON Schema dans MCP `inputSchema`
- Cache écrit uniquement sous `~/.cache/image-gen/` (vérif `path.resolve().is_relative_to`)

---

## 🧪 Tests cibles (~120 tests)

Même architecture que la suite RetoucheImage :
- **test_models.py** (~15) : Cohérence registry, capacités, prix
- **test_generate.py** (~25) : Dispatch par modèle, ratios, qualités, batch
- **test_edit.py** (~15) : Inpaint masque, replace_bg, outpaint directions
- **test_process.py** (~20) : Remove BG, upscale factors, vectorize, tile
- **test_manage.py** (~15) : Cache hit/miss, IDs, list, delete, costs
- **test_security.py** (~15) : Path traversal sur tous les inputs filename
- **test_integration.py** (~15) : Workflows end-to-end mockés (ex: generate → upscale → BG-remove)

Tous mockent `replicate.run` (zéro appel réseau, zéro crédit).

CI GitHub Actions clonée depuis RetoucheImage.

---

## 📋 Phases d'exécution (estimation)

| Phase | Contenu | Effort CC+gstack |
|-------|---------|------------------|
| **1. Scaffolding** | Layout modulaire, FastMCP, env loading, models.py registry, cache.py | ~30 min |
| **2. Generation** | `generate_image`, `image_to_image`, `generate_batch` + tests | ~45 min |
| **3. Édition** | `inpaint`, `replace_background`, `outpaint` + tests | ~30 min |
| **4. Post-traitement** | `remove_background`, `upscale`, `vectorize`, `seamless_tile` + tests | ~45 min |
| **5. Gestion + Style** | `list/get/delete_images`, `get_costs`, `apply_style` + tests cache | ~30 min |
| **6. Tests + CI** | Suite pytest complète, CI GitHub Actions, README/MIGRATION | ~30 min |
| **7. Migration mcp.json** | Switch user de v1 → v2, garde fallback Pollinations en flag | ~10 min |

**Total : ~3h30** d'effort actif. Compression vs équipe humaine : **~30×** (qui prendrait ~2 semaines).

---

## ⚖️ Trade-offs explicites

**On gagne :**
- ✅ 15 outils vs 1 → couvre 100 % du workflow PPT visuel
- ✅ Backend Replicate = qualité 8 modèles SOTA + qualité réglable
- ✅ Cache = pas de re-coût si même prompt
- ✅ Tests = pas de régression silencieuse
- ✅ Cohérent avec RetoucheImage (réutilisation de helpers, mental model partagé)

**On perd :**
- ❌ Le mode "gratuit sans clé" (Pollinations). Solution : garder un outil `generate_free` qui pointe sur Pollinations, ~50 lignes, fallback démo.
- ❌ Une image coûte maintenant ~$0.04 au lieu de $0.00. Mitigation : cache + `get_costs` qui prévient.
- ❌ Un fichier `.env` à configurer. Mitigation : message d'erreur clair au démarrage MCP comme dans RetoucheImage.

**On NE fait PAS (out of scope v2) :**
- ❌ Génération vidéo (existe déjà dans `videogen` MCP désactivé)
- ❌ Edition de masques côté UI (l'agent doit fournir le mask en bytes)
- ❌ Animations / GIFs (pas de besoin PPT)
- ❌ Watermark / signature (peut être ajouté en v3 si besoin)

---

## 🚀 Quick wins immédiats (avant phases lourdes)

Si tu veux valider l'approche avant de tout coder :
1. **Phase 1 + Phase 2 (`generate_image` Replicate-only) en 1h** — déjà 80 % de la valeur.
2. Tester sur un vrai deck PPT manuellement.
3. Valider que les modèles répondent à tes besoins avant de coder le reste.

C'est l'option "MVP" si tu préfères livrer en plusieurs vagues plutôt qu'un big bang.

---

## ❓ Décisions ouvertes (à valider avec toi)

1. **Garder Pollinations en fallback gratuit ?** (oui = +50 lignes, non = MCP plus simple)
2. **`generate_for_slide(role)` helper de haut niveau ?** (pratique mais risque de fragiliser — l'agent peut composer les outils bas niveau lui-même)
3. **Auto-prompt-enhancement on/off par défaut ?** (cf. shinpr/mcp-image qui le fait — gain qualité énorme mais consomme 1 appel LLM en plus)
4. **MVP en 1h ou full v2 en 3h30 d'un coup ?**

Je propose de répondre à ces 4 questions juste après ton approbation du plan.

---

Sources :
- [Recraft MCP Server (16 outils)](https://github.com/BartWaardenburg/recraft-mcp-server)
- [Flux Studio MCP](https://glama.ai/mcp/servers/jmanhype/mcp-flux-studio)
- [shinpr/mcp-image (Gemini Nano Banana 2)](https://github.com/shinpr/mcp-image)
- [Replicate Image Gen MCP](https://github.com/GongRzhe/Image-Generation-MCP-Server)
- [Microsoft PowerPoint Copilot AI](https://powerpoint.cloud.microsoft/create/en/ai-presentation-designer/)
- [Plus AI for presentations](https://plusai.com/features/ai-image-generator)
- [Beautiful.ai](https://www.beautiful.ai/)
