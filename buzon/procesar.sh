#!/usr/bin/env bash
# Archiva lo que el equipo aprobó en el buzón, lo borra de la computadora y sube las piezas
# a GitHub. Lo corre buzon-procesar.timer cada 15 minutos.
set -euo pipefail
cd "$(dirname "$0")/.."
RECIBIDO="${RECIBIDO:-/var/lib/buzon/recibido}"

[ -n "$(ls -A "$RECIBIDO" 2>/dev/null)" ] || exit 0
git pull -q --rebase
python herramientas/archivar.py buzon "$RECIBIDO"

git add piezas
git diff --cached --quiet && exit 0
git commit -q -m "Piezas del buzón"
git push -q || { git pull -q --rebase && git push -q; }
