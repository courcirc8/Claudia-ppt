# Atelier — file-based bridge HTML ↔ Claude

Pattern : le picker HTML écrit un brief markdown dans `~/Downloads`, un worker
Python le détecte, le parse et émet un signal que Claude (LLM en conversation
active) capte pour exécuter la génération.

Pas de clef API exposée dans le browser. Pas de serveur backend. Pas de
copy-paste manuel.

## Workflow

```
┌────────────┐  download .md   ┌─────────────┐    poll     ┌──────────────┐
│  Picker    │ ──────────────> │ ~/Downloads │ <────────── │   worker.py  │
│  (HTML)    │                 └─────────────┘    3s       └──────┬───────┘
└────────────┘                                                    │ move
                                                                  ▼
                                                          ┌────────────────┐
                                                          │ atelier/inbox/ │
                                                          │   {code}.md    │
                                                          └───────┬────────┘
                                                                  │ exec
                                                                  ▼
                                                          ┌────────────────┐
                                                          │ atelier/outbox/│
                                                          │  {code}.done.md│
                                                          └───────┬────────┘
                                                                  │ notify
                                                                  ▼
                                                          ┌────────────────┐
                                                          │  Claude (LLM)  │
                                                          │  reprend main  │
                                                          └────────────────┘
```

## Lancer le worker

Dans un terminal séparé :

```bash
python3 atelier/atelier_worker.py
```

Options :
- `--watch <dir>` : dossier à scruter (défaut `~/Downloads`)
- `--once` : un seul passage puis exit (utile pour test)

## Côté Claude

Le worker émet sur stdout :

```
>>> RESUME: code=A4F2 status=AWAITING_LLM brief=atelier/inbox/A4F2.md
```

Cette ligne est interceptée par Claude (via `Bash run_in_background=true` +
`Monitor`) qui :
1. Lit `atelier/inbox/{code}.md`
2. Lance la pipeline `pptx_kit` avec la composition extraite
3. Génère les images via `image-gen` MCP avec le `StyleAnchor` correspondant
4. Compose le `.pptx`, audite, écrit `atelier/outbox/{code}.done.md`
5. Confirme à l'utilisateur dans la conversation

## Format brief.md

Voir le template généré par le picker (Tab 4 → « Générer le brief ») —
champs structurés en markdown facilement parseables par regex côté worker
ET lisibles à l'œil nu pour debug.

## Pourquoi pas un LLM dans le browser ?

Pour avoir un chat embed dans un tab du picker, il faudrait soit :
- Une clef API exposée dans le HTML (faille de sécu critique)
- Un backend proxy local qui détient la clef (complexité serveur)

Le pattern file-based ci-dessus :
- ✅ Aucune clef à gérer
- ✅ Aucune surface d'attaque
- ✅ L'utilisateur paie déjà sa session Claude — pas de double facture
- ✅ HTML = sélection visuelle (son fort), Claude = exécution + fine-tune
- ✅ Audit trail complet (briefs horodatés, status persistants)
