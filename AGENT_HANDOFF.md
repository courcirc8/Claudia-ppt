# 📨 Status handoff — Claudia-ppt repo

**Pour l'agent travaillant sur l'autre copie de `Claudia-ppt`.**
**Date** : 2026-05-03

⚠️ Le user a édité le repo depuis **deux endroits différents** sans synchroniser. Avant de continuer ton travail, lis ce message en entier et **vérifie l'état de tes propres modifications** par rapport à ce qui suit.

## État du repo de mon côté

- **Path** : `/Users/courcirc8/Documents/Cursor/MCPs/Claudia-ppt`
- **Branche** : `main`, **4 commits ahead of `origin/main`**, **pas pushé**
- **Working tree** : clean
- **Tests** : `pytest tests/` → **178 passed, 0 fail, 0 xfail**

## Mes 4 commits (du plus ancien au plus récent)

```
8871b11  test(picker): align HTML/JS smoke tests with current picker.html
d9f1a82  feat(picker): regression suite + static-allowlist hardening
9327803  feat(picker): updated UI — eyebrow/title/sub mocks, 6 style samples, IIFE defaults
3279610  chore(gitignore): exclude regenerated picker samples + Claude Code session data
```

### Détail par commit

**`8871b11` — alignement test_picker_html.py**
- Suppression de `test_brackets_balanced` (faux positif structurel : compte brut `(`/`)` ne distingue pas les parens dans les strings).
- Regex `DEFAULT_SLIDES` mis à jour pour la forme IIFE (`const DEFAULT_SLIDES = (function () { ... return [...] })();`).
- Pattern `title:` / `body:` accepte string OU identifier (cas de `title: cover`).
- `PRESETS_KEY` : accepte la nouvelle template literal `` `claudia_ppt_presets:${PROJECT_NAME}` ``.

**`d9f1a82` — regression suite + fix sécurité**
- 🆕 `tests/test_picker_server.py` : 29 tests, 7 classes (TestStaticServing, TestHealth, TestProjectExists, TestProjectFiles, TestProjectFile, TestSecurity, TestSelectedThemeWrite). Spawn du serveur en subprocess sur port libre, `CLAUDIA_PPT_PRESENTATIONS` pointé sur `tmp_path` seedé avec la fixture.
- 🆕 `tests/fixtures/mini_project/` : `manifest.json` + `slides_content.json` (3 slides cover/content/closing).
- 🔒 **Fix sécurité dans `picker/server.py`** : ajout d'une **allowlist statique explicite** (`ALLOWED_STATIC_FILES = {picker.html, themes.json}`, `ALLOWED_STATIC_DIRS = {samples}`). Avant le fix, `/samples/../server.py` renvoyait **200** et servait le code source. Maintenant 403.

**`9327803` — picker.html UI**
- Mocks DOM eyebrow / title / sub pour la cover preview.
- 6 styles d'images (elegant_editorial, corporate_classic, earth_warm, modern_fresh, graphic_strict, botanical_soft) référençant `samples/styles/*.png` (cover + content).
- `DEFAULT_SLIDES` en IIFE qui injecte `PROJECT_NAME` dans le titre cover.
- `STATE_KEY` et `PRESETS_KEY` en template literals scopés par projet.

**`3279610` — .gitignore**
- Exclut `picker/samples/{styles,themes}/*.{png,jpg,webp}` (regénérés par image-gen, pas committés).
- Exclut `.claude/` (session locale Claude Code).

## Points d'attention pour ta réconciliation

1. **Si tu as touché `picker/picker.html`** → conflit probable. Mon `9327803` a 241 insertions / 51 suppressions sur ce fichier. Diff la version mainline contre ta version, fusionne à la main.

2. **Si tu as touché `picker/server.py`** → conflit possible sur le bloc de routage statique (lignes ~130-155) à cause du fix sécurité. Garde l'allowlist (`ALLOWED_STATIC_FILES`, `ALLOWED_STATIC_DIRS`) — c'est un fix de vraie vulnérabilité.

3. **Si tu as touché `tests/test_picker_html.py`** → conflit possible. Mon commit a fixé 3 tests obsolètes. Vérifie que tes modifs sont compatibles.

4. **Si tu as ajouté des PNGs sous `picker/samples/styles/` ou `themes/`** → ils sont maintenant gitignorés. Pour les ajouter quand même il faut `git add -f`. Mais le user a explicitement demandé que ces previews soient **regénérées par le flow** et pas committées.

5. **Anomalie git observée au début** : `picker/server.py` était dans un état "untracked" (le user a réparé un `git rm -r --cached` resté en plan plus tôt dans la session). Je l'ai re-stagé via `9327803`. Si ton historique git a aussi été perturbé par ça, vérifie `git ls-files | grep server.py`.

## Réparations système faites en début de session (à savoir)

Le venv `/Users/courcirc8/Documents/Cursor/MCPs/venv_mac` était corrompu (`pydantic`, `pydantic_core`, `mcp` à moitié installés). Réparé via `pip install --no-cache-dir --force-reinstall pydantic pydantic_core "mcp[cli]"`. Conséquence : les 5 MCP servers qui partagent ce venv (`powerpoint`, `image-gen`, `ppt-analyzer`, `icon-library`, `timeline`) sont tous ✓ Connected.

⚠️ Si une session Claude Code était ouverte avant la réparation, **les outils MCP du serveur `powerpoint` ne sont pas chargés dans cette session** — un redémarrage de Claude Code est nécessaire pour les voir.

## Pas de push

Je n'ai **pas pushé**. Si tu as aussi des commits locaux non-pushés, on doit décider ensemble de la stratégie : merge, rebase, ou cherry-pick. **Ne push pas avant qu'on se soit aligné** — sinon force-push war.

## TL;DR

> 4 commits prêts en local sur `main` côté A. Suite tests verte (178/178). Avant push, l'agent côté B doit comparer son état et résoudre les conflits éventuels sur `picker.html`, `server.py`, `test_picker_html.py`. Aucun PNG ni `.claude/` ne doit revenir dans le repo.
