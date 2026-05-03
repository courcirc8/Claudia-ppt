#!/usr/bin/env bash
# Lance la suite de régression ImageGen v2.
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HOME/.virtualenvs/retouche_image"

if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "❌ Venv introuvable : $VENV"
    echo "   Crée-le ou ajuste VENV dans ce script."
    exit 1
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

cd "$SCRIPT_DIR" || exit 1

# Installer pytest + mcp + python-dotenv si nécessaires
for pkg in pytest mcp python-dotenv replicate; do
    if ! python -c "import $(echo $pkg | tr '-' '_')" 2>/dev/null; then
        echo "📦 Installation de $pkg…"
        pip install --quiet "$pkg"
    fi
done

echo "──────────────────────────────────────────────────────────"
echo " 🧪 ImageGen v2 — suite de régression"
echo "──────────────────────────────────────────────────────────"
exec python -m pytest tests/ -v --tb=short "$@"
