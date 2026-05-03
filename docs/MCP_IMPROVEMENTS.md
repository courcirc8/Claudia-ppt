# Améliorations MCP — pour génération PPT first-pass parfaite

Issues vécues sur cette session (7 itérations v1→v7) classées par criticité.

## P0 — Bloquants identifiés

### `mcp__powerpoint__create_presentation` — slide 4:3 par défaut
**Problème** : crée une slide 10×7.5" (4:3 standard) silencieusement. Sans vérifier, j'ai conçu tout pour 13.33×7.5" (16:9) → 6 itérations gâchées.

**Fix proposé** :
```python
create_presentation(
    id: str,
    aspect_ratio: Literal["16:9", "4:3"] = "16:9",  # NEW, défaut moderne
    width_inches: float = None,                       # override explicite
    height_inches: float = None,
)
```
Retour enrichi : `{"slide_width": 13.333, "slide_height": 7.5, "aspect": "16:9"}` pour bloquer toute supposition.

### `mcp__powerpoint__manage_image` — pas de delete/move/resize
**Problème** : seule `add` existe. Pour repositionner j'ai dû passer par python-pptx en bash. Impossible de corriger une image sans rebuild complet.

**Fix proposé** : opérations `move`, `resize`, `delete` avec `shape_index`.

### `mcp__ppt-analyzer__export_slides_to_png` — cassé sur macOS
**Problème** : dépend de `powershell.exe`. Inutilisable hors Windows.

**Fix proposé** : fallback automatique `soffice --convert-to pdf` + `pdftoppm` sur Mac/Linux.

## P1 — Forte amélioration first-pass

### `mcp__powerpoint__validate_layout` — nouvelle commande
Audit programmatique avant export. Pour chaque shape :
- Hors bounds (`L+W > slide_width` ou `T+H > slide_height`) → ERROR
- Marge < 0.5" → WARNING
- Texte font_size < seuil (18pt body, 24pt title) → WARNING
- Recouvrement entre shapes (overlap > 5%) → WARNING

Retour : liste structurée `[{slide, shape, severity, issue, fix_suggestion}]`. À appeler systématiquement avant `save_presentation`.

### `mcp__powerpoint__get_text_capacity` — nouvelle commande
Calcule combien de caractères/lignes tiennent dans une box donnée.
```python
get_text_capacity(width_inches, height_inches, font_size, font_name="Calibri")
# → {"chars_per_line": 54, "max_lines": 13, "wrap_safe_threshold": 50}
```
Permet de planifier le texte AVANT de l'ajouter, pas après débordement.

### `mcp__powerpoint__create_project`  — nouvelle commande
Scaffolding standard :
```python
create_project(
    name: str,
    parent_dir: str = ".",  # défaut cwd
)
# crée:
# parent_dir/name/
#   ├── name.pptx (vide, 16:9)
#   ├── images/
#   ├── icons/
#   ├── png_review/
#   ├── sources/
#   └── manifest.json
```
Force la structure propre dès le départ (sinon le user doit le rappeler à chaque fois).

### `mcp__powerpoint__manage_text` — `auto_fit` doit être respecté par `format`
**Problème** : `format(font_size=16)` n'a aucun effet visible si le shape avait `auto_fit=true` au create. Il faut soit reset auto_fit, soit forcer la taille.

**Fix proposé** : si `format` change `font_size`, désactiver auto_fit automatiquement (ou exposer un param `force=true`).

## P2 — Image-gen MCP

### `mcp__image-gen__tool_generate_image` — `negative_prompt` natif
**Problème** : on bricole « NO TEXT, NO LETTERS, NO WORDS » dans le prompt principal — pas fiable, gpt-image-2 ajoute parfois du texte EN quand même.

**Fix proposé** :
```python
tool_generate_image(
    prompt: str,
    negative_prompt: str = "",   # NEW — passé en paramètre dédié
    text_in_image: Literal["allow", "forbid"] = "allow",  # NEW — préréglé "no text" robuste
    text_language: str = None,   # NEW — pour cohérence FR/EN
)
```

### `mcp__image-gen__tool_generate_image` — `output_dir` + `name`
**Problème** : actuellement écrit dans `~/.cache/image-gen/{hash}.png`. Si le cache est purgé, le PPT casse. J'ai dû `cp` à la main vers `images/`.

**Fix proposé** :
```python
tool_generate_image(..., output_dir="<project>/images/", name="02_newsletter")
# → écrit /Users/.../droit_des_familles/images/02_newsletter.png
# manifest.json mis à jour automatiquement
```

## P3 — Boucle qualité intégrée

### `mcp__powerpoint__quality_loop` — nouvelle commande
Encapsule le pattern itératif :
```python
quality_loop(
    pptx_path: str,
    target_score: float = 8.0,
    max_iterations: int = 5,
    rubric: dict = DEFAULT_RUBRIC,  # text_fits/4, image_bounds/véto, font_size/3, etc.
)
```
Fait : export PNG → mesure programmatique (bounds + font sizes) + analyse multimodale → propose patches → re-applique → re-export. Stop quand score ≥ cible ou max_iterations.

## Récap priorités

| P | Item | Impact 1ère passe |
|---|---|---|
| P0 | `create_presentation` aspect_ratio param | -6 itérations |
| P0 | `manage_image` move/resize/delete | -2 itérations |
| P0 | `export_slides_to_png` cross-platform | utilisable du tout |
| P1 | `validate_layout` | -3 itérations (détecte bleed/clip avant export) |
| P1 | `get_text_capacity` | -2 itérations (sizing texte first-shot) |
| P1 | `create_project` | structure propre par défaut |
| P1 | `format` respecte font_size | -1 itération (v3 silencieuse) |
| P2 | `negative_prompt` natif | régen image inutile |
| P2 | `output_dir`+`name` image-gen | pas de `cp` manuel |
| P3 | `quality_loop` intégré | automatise toute la session |

**Estimation** : avec P0+P1 implémentés, cette présentation aurait été v1=v7 (≈10/10) en une passe au lieu de 7.

---

# Vague 2 — 10 propositions complémentaires

Au-delà du first-pass, ces évolutions réduisent l'orchestration manuelle et industrialisent la qualité.

## P1 — Réduction d'orchestration (gros gain Claude-side)

### 1. `mcp__powerpoint__create_theme` — thème projet
**Pain actuel** : j'ai répété 10× les RGB `[80,30,100]`, fontname `Georgia`, gradient `[[60,20,80],[200,130,180]]`. Si on change la palette, 50 appels à modifier.

**Proposé** :
```python
create_theme(name="droit_familles", palette={"primary":"#501464","accent":"#E8B4D2","gold":"#C9A96E","text":"#321E3C"},
             fonts={"title":"Georgia","body":"Calibri"},
             gradients={"cover":[[60,20,80],[200,130,180]]})
```
Puis `add_slide(theme="droit_familles", role="cover")` applique tout. Changement de palette = 1 ligne.

### 2. `mcp__powerpoint__add_content_slide` — préset haut-niveau
**Pain actuel** : pour chaque slide j'ai fait 4 appels (add_slide + add_image + add_title + add_body) avec 12 params chacun.

**Proposé** :
```python
add_content_slide(
    title="1. La newsletter en bref",
    body=["Publication mensuelle…", "Édition d'avril…", ...],  # liste = bullets auto
    image="images/02_newsletter.png",
    layout="image-left",  # ou "image-right", "image-fullbleed"
    theme="droit_familles",
)
```
Une slide = un appel. Mes 10 slides : 10 appels au lieu de 40.

### 3. `mcp__powerpoint__add_master_layout` — header/footer/numérotation partagés
**Pain actuel** : si je veux ajouter un footer "© 2026 droitdesfamilles.ch" sur 8 slides, c'est 8 appels manuels.

**Proposé** : layout master appliqué automatiquement aux slides taggées `inherits="master"`. Changement = 1 endroit.

## P2 — Industrialisation du texte

### 4. `mcp__powerpoint__manage_text` op `bulk_apply`
**Pain actuel** : pour passer body 15→22pt sur 8 slides, j'ai dû boucler en Python avec python-pptx. Le MCP n'a pas d'opération batch.

**Proposé** : `manage_text(operation="bulk_format", filter={"role":"body"}, font_size=22)` applique sur tous les body de toutes les slides en un appel.

### 5. Smart auto-wrap dans `manage_text(add)`
**Pain actuel** : j'ai inséré manuellement des `\n` dans les longues phrases ("Les contributions d'entretien fixées en mesures\nprovisionnelles…") pour forcer le wrap au bon endroit.

**Proposé** : option `auto_wrap=true` qui calcule les sauts optimaux selon `font_size` + `width` + langue (évite de couper "art. 198 CC" entre "art." et "198", garde les unités ensemble). Évite de raisonner sur des comptes de caractères.

## P3 — Productivité image-gen

### 6. `tool_generate_image` — `style_anchor`
**Pain actuel** : j'ai répété "elegant pink/violet/mauve palette with gold accents, refined editorial style" dans les 11 prompts. Cohérence fragile.

**Proposé** :
```python
set_style_anchor("editorial_pink_violet", reference_image_id="d67949e73044c3c1")
# puis :
tool_generate_image(prompt="a passport and a family", style_anchor="editorial_pink_violet")
```
La référence visuelle force la cohérence (palette, mood, composition). Plus besoin de répéter le style en mots.

### 7. `tool_generate_variations` — N alternatives sans réécrire
**Pain actuel** : si je n'aime pas l'image générée, je dois reformuler tout le prompt et regénérer. Pas de "donne-moi 3 versions".

**Proposé** : `tool_generate_variations(image_id, count=4, variation_strength=0.4)` → 4 PNG alternatives. Permet le pattern "génère 4, je choisis la meilleure" en 1 appel.

## P4 — Boucle de qualité plus rapide

### 8. Export PNG incrémental
**Pain actuel** : à chaque itération je re-rends les 10 slides en PDF, alors que j'en ai modifié 1. Lent et inutile.

**Proposé** : `export_slides_to_png(pptx_path, only_changed=true)` détecte les slides modifiées (via XML hash) depuis le dernier export et ne re-rend que celles-là. Boucle qualité 5× plus rapide sur grosses présentations.

### 9. `mcp__powerpoint__diff_presentations`
**Pain actuel** : pour comparer v6 vs v7 j'ai dû viewer manuellement les PNG côte à côte. Pas de diff structuré.

**Proposé** :
```python
diff_presentations(before="v6.pptx", after="v7.pptx")
# → [{slide:1, change:"font_size 15→22 on body"},
#    {slide:5, change:"image moved (8.5,0.5)→(8.33,0.75)"}, …]
```
Sortie structurée pour expliquer les changements ou rollback ciblé.

## P5 — Qualité automatisée

### 10. `mcp__ppt-analyzer__check_accessibility`
**Pain non vu cette session mais critique** :
- Contraste texte/fond (WCAG AA = 4.5:1 mini)
- Font size minimum lisibilité (≥16pt body en présentation projetée)
- Alt-text manquant sur images
- Hiérarchie de titres (un H1 par slide)
- Lisibilité des liens (URL en clair vs masqué)

**Proposé** : retour `{slide, issue, severity, fix}` exécuté avec `validate_layout` (P1 vague 1) pour un audit complet en 1 appel.

---

## Synthèse vagues 1+2

| Domaine | Items | Effet |
|---|---|---|
| Slide bounds & metadata | P0×3 vague1 | Élimine bugs invisibles |
| Layout planning & validation | P1×4 v1 + #2,#3,#10 v2 | Conception correcte du 1er coup |
| Édition multi-slide | #1, #4, #5 v2 | 10× moins d'appels Claude |
| Image-gen cohérence | P2×2 v1 + #6, #7 v2 | Style stable, choix rapide |
| Boucle qualité | P3 v1 + #8, #9 v2 | Itérations rapides et tracées |

