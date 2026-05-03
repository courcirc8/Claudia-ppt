# pptx_kit

Toolkit Python implémentant les améliorations P2-P5 de [MCP_IMPROVEMENTS.md](../MCP_IMPROVEMENTS.md), au-dessus de `python-pptx`.

Conçu pour réduire l'orchestration manuelle Claude-side dans la génération de présentations.

## Modules

| Fichier | Fonctions clés | Pain résolu |
|---|---|---|
| `text.py` | `inspect`, `bulk_apply`, `smart_wrap`, `estimate_capacity` | éditer N slides en 1 appel ; calculer chars/ligne avant débordement ; wrap atomique (« art. 198 CC », dates, refs TF) |
| `image_style.py` | `StyleAnchor`, `THEMES`, `request_variations`, `register_image`, `adopt_from_cache` | cohérence visuelle sans répétition de prompt ; manifest réutilisable |
| `quality.py` | `incremental_export`, `diff_presentations` | re-render seulement les slides modifiées (5× plus rapide) ; diff structuré entre versions |
| `accessibility.py` | `audit_accessibility`, `contrast_ratio` | bounds, fonts mini, contraste WCAG AA, alt-text, hiérarchie titres |

## Installation

```bash
pip install python-pptx Pillow
```

`incremental_export` requiert `soffice` et `pdftoppm` (Homebrew sur macOS).

## Quick start

```python
from pptx_kit import (
    bulk_apply, smart_wrap, audit_accessibility,
    incremental_export, diff_presentations,
)
from pptx_kit.text import inspect, estimate_capacity
from pptx_kit.image_style import THEMES, request_variations

PPTX = "droit_des_familles.pptx"

# 1. Voir ce qu'il y a dans la deck
for s in inspect(PPTX):
    print(s)

# 2. Capacité texte d'une box avant de remplir
cap = estimate_capacity(width_in=8.13, height_in=5.4, font_size_pt=22)
# → {'chars_per_line': 51, 'max_lines': 14, 'wrap_safe_threshold': 45}

# 3. Wrap intelligent
wrapped = smart_wrap(
    "Les biens acquis avant le mariage (art. 198 ch. 2 CC) selon TF 5A_54/2024…",
    width_in=8.13, font_size_pt=22,
)

# 4. Bulk-format tous les body en 1 appel
n = bulk_apply(PPTX, filter={"role": "body"}, font_size=22, font_name="Calibri")

# 5. Style anchor pour image-gen (cohérence multi-image)
prompt = THEMES["navy_gold"].prompt_for("a passport and a family silhouette")
# → "Sophisticated corporate… palette of deep navy… NO TEXT… Subject: a passport…"

# 6. Variations d'une image existante (specs MCP à exécuter en parallèle)
specs = request_variations("d67949e73044c3c1", count=4)
# Claude appelle ensuite mcp__image-gen__tool_image_to_image avec chacun

# 7. Re-export incrémental (re-rend seulement les slides modifiées)
res = incremental_export(PPTX, "png_review/v8")
# → {'rendered': [3, 5], 'skipped': [0,1,2,4,6,7,8,9], 'total': 10}

# 8. Diff entre deux versions
changes = diff_presentations("v6.pptx", "v7.pptx")
# → [{'slide': 1, 'shape': 2, 'kind': 'font_size_changed', 'before': 15, 'after': 22}, …]

# 9. Audit accessibility + layout
issues = audit_accessibility(PPTX)
for i in issues:
    print(f"[{i.severity}] slide {i.slide}: {i.code} — {i.message}")
```

## Demo

```bash
python3 pptx_kit/demo.py
```

Roule les 8 fonctions principales contre `droit_des_familles.pptx` et imprime un résumé.

## Architecture

```
pptx_kit/
├── __init__.py        # exports publics
├── text.py            # inspect / bulk_apply / smart_wrap / estimate_capacity
├── image_style.py     # StyleAnchor / THEMES / variations / manifest
├── quality.py         # incremental_export / diff_presentations
├── accessibility.py   # audit + contrast WCAG
└── demo.py            # exemples runnables
```

## Limites connues

- `incremental_export` rend toujours toutes les slides via `pdftoppm` (1 appel) puis détecte celles qui ont changé. Le gain réel est sur le hash : si rien n'a changé depuis le dernier run, aucun export n'est lancé.
- `audit_accessibility` détecte le bg via `slide.background.fill` ; si le fond est une picture (gradient stocké comme image), il défaut à blanc → faux positifs sur cover/closing à fond image.
- `smart_wrap` utilise une largeur moyenne par caractère (Georgia ≠ Calibri ≠ Inter). Précision ±10%.

## Migration vers MCP natif

Chaque module ici est candidat à devenir un outil MCP officiel dans `PowerPoint/tools/`. La signature est gardée stable pour faciliter le port.
