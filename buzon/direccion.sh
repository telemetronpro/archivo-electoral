#!/usr/bin/env bash
# Muestra las direcciones del buzón y la clave del equipo, y deja códigos QR para carteles.
# Uso: sudo bash direccion.sh
set -uo pipefail
CASA=/var/lib/buzon

ONION=$(cat /var/lib/tor/buzon/hostname 2>/dev/null || true)
NORMAL=""
if command -v tailscale >/dev/null; then
  NORMAL=$(tailscale funnel status 2>/dev/null | grep -oE 'https://[^ ]+\.ts\.net' | head -1 || true)
fi
CLAVE=$(grep '^BUZON_CLAVE=' /etc/buzon.env 2>/dev/null | cut -d= -f2-)

echo
if [ -n "$NORMAL" ]; then
  echo "Enlace del buzón (para cualquier persona):   $NORMAL"
  qrencode -s 10 -o "$CASA/qr-buzon.png" "$NORMAL" && echo "   Código QR para carteles: $CASA/qr-buzon.png"
fi
if [ -n "$ONION" ]; then
  echo "Dirección para el navegador Tor:             http://$ONION"
  qrencode -s 10 -o "$CASA/qr-buzon-tor.png" "http://$ONION" && echo "   Código QR: $CASA/qr-buzon-tor.png"
fi
echo
echo "Revisar lo que llega (solo el equipo):        ${NORMAL:-http://$ONION}/revisar"
echo "   Usuario: cualquiera.  Clave: $CLAVE"
