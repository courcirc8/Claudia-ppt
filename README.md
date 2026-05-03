# Claudia-ppt

> Compose, génère et audite des présentations PowerPoint avec Claude.
> Outil complet : sélection visuelle (HTML), librairie d'édition (Python),
> bridge file-based, et MCP servers bundlés (PowerPoint + Image generation).

---

## Architecture

```
Claudia-ppt/                          ← LE REPO (cet outil)
├── README.md                         ← ce fichier
├── LICENSE                           ← MIT
├── NOTICE                            ← attribution composants tiers
├── picker/                           ← front-end de composition
│   ├── picker.html                   ← lit ?project=<nom>
│   ├── themes.json                   ← 7 palettes éditoriales
│   └── samples/                      ← 6 styles + 3 image-styles
├── pptx_kit/                         ← lib Python (engine)
│   ├── text.py                       ← bulk_apply, smart_wrap
│   ├── image_style.py                ← StyleAnchor, themes
│   ├── quality.py                    ← incremental_export, diff
│   ├── accessibility.py              ← audit WCAG + bounds
│   └── README.md
├── atelier/                          ← worker file-based
│   ├── atelier_worker.py             ← prend --project <path>
│   └── README.md
├── tests/                            ← suite 150 tests
├── docs/
│   └── MCP_IMPROVEMENTS.md
└── servers/                          ← MCP servers bundlés (vendored)
    ├── powerpoint/                   ← PowerPoint MCP — © GongRzhe (MIT)
    │   ├── LICENSE                   ← MIT — à conserver
    │   └── UPSTREAM.md               ← origine + version
    └── image-gen/                    ← Image generation MCP
        ├── LICENSE                   ← MIT
        └── UPSTREAM.md

../presentations/                     ← PROJETS UTILISATEUR (hors repo)
└── <nom>/
    ├── <nom>.pptx
    ├── manifest.json
    ├── selected_theme.json
    ├── slides_content.json
    ├── images/
    ├── png_review/
    ├── sources/
    ├── briefs/
    └── outbox/
```

---

## Workflow

### 1. Composer dans le picker

```bash
open "Claudia-ppt/picker/picker.html?project=droit_des_familles"
```

5 onglets : Style → Palette → Personnalisations → Contenu slides → Génération.

### 2. Lancer le worker

```bash
python3 Claudia-ppt/atelier/atelier_worker.py \
        --project presentations/droit_des_familles
```

### 3. Cliquer « Générer brief » dans le picker

Le picker télécharge `atelier-<project>-<ISO>-<code>.md` dans `~/Downloads/`.
Le worker le détecte en 3s, le déplace dans `presentations/<project>/briefs/`,
émet `RESUME: code=<X>`.

### 4. Claude reprend la main

Sur réception, Claude lit le brief, lance la pipeline `pptx_kit` (image-gen
MCP + powerpoint MCP), audite via `accessibility.audit_accessibility`, écrit
`outbox/{code}.done.md`, confirme.

---

## MCP servers bundlés

Deux serveurs MCP au cœur du flow, déclarés dans `~/.claude.json` :

```json
{
  "mcpServers": {
    "image-gen": {
      "type": "stdio",
      "command": "<path>/python",
      "args": ["<path>/Claudia-ppt/servers/image-gen/server.py"]
    },
    "powerpoint": {
      "type": "stdio",
      "command": "<path>/python",
      "args": ["<path>/Claudia-ppt/servers/powerpoint/ppt_mcp_server.py"]
    }
  }
}
```

> ⚠️ Après tout déplacement de `Claudia-ppt`, mettre à jour ces chemins puis
> redémarrer Claude Code pour que les serveurs soient repris.

---

## Tests

```bash
cd Claudia-ppt
python3 -m pytest tests/ -v
# 150 tests · ~10s
```

Override du sample utilisé par les tests d'intégration :
```bash
SAMPLE_PPTX=../presentations/autre/autre.pptx pytest tests/
```

---

## Créer un nouveau projet

```bash
PROJ=mon_projet
mkdir -p presentations/$PROJ/{images,png_review,sources,briefs,outbox}

# slides_content.json (10 slides)
cat > presentations/$PROJ/slides_content.json << EOF
{
  "project": "$PROJ",
  "slides": [
    {"idx": 0, "role": "cover",   "title": "...", "body": "..."},
    ... (10 entrées au total)
    {"idx": 9, "role": "closing", "title": "...", "body": "..."}
  ]
}
EOF

open "Claudia-ppt/picker/picker.html?project=$PROJ"
python3 Claudia-ppt/atelier/atelier_worker.py --project presentations/$PROJ
```

---

## Architecture (résumé)

- **Pas de clef API exposée** dans le browser — bridge file-based
- **Pas de backend** — tout est statique HTML + Python local
- **Tool / Project clairement séparés** — le picker prend `?project=` en URL
- **Tests rigoureux** — 150 tests Python validés à chaque commit
- **Qualité par défaut** — auto_fit=false, smart_wrap atomique, a11y WCAG AA

---

## Roadmap

Voir [docs/MCP_IMPROVEMENTS.md](docs/MCP_IMPROVEMENTS.md) — 20 propositions
classées par priorité (P0-P5) : aspect ratio par défaut, validation layout,
capacités texte, presets, polling live, export incrémental, etc.

---

## Credits & Licenses

Claudia-ppt est sous licence **MIT** — voir [LICENSE](LICENSE).
Copyright (c) 2026 Eric Vandel.

Ce repo bundle des composants tiers, listés dans [NOTICE](NOTICE) :

| Composant | Origine | Licence | Auteur |
|---|---|---|---|
| `servers/powerpoint/` | [github.com/GongRzhe/Office-PowerPoint-MCP-Server](https://github.com/GongRzhe/Office-PowerPoint-MCP-Server) v2.0.6 | MIT | © 2025 GongRzhe |
| `servers/image-gen/` | [github.com/courcirc8/image_gen](https://github.com/courcirc8/image_gen) | MIT | © 2026 Eric Vandel |

Le serveur PowerPoint MCP de **GongRzhe** est le moteur de manipulation `.pptx`
sur lequel Claudia-ppt s'appuie. Tout crédit pour cette architecture
sous-jacente lui revient. Le LICENSE original est conservé tel quel dans
`servers/powerpoint/LICENSE`.

### Origine du nom

**Claudia** — *Claude + ia* (assistante).
**ppt** — la spécialité du projet.

Repo futur : `github.com/courcirc8/Claudia-ppt`.
