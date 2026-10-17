#!/usr/bin/env bash
# Instala el buzón en una computadora con Debian, Ubuntu o Raspberry Pi OS que quede prendida.
# El buzón es una página web sencilla con dos direcciones: un enlace normal (Tailscale Funnel)
# para cualquier persona, y una dirección .onion (Tor) para quien quiera el máximo anonimato.
# Instrucciones completas en docs/buzon.md.
#
# Uso: sudo bash instalar.sh https://github.com/USUARIO/archivo-electoral
set -euo pipefail

REPO_URL="${1:?Falta el enlace del repositorio, por ejemplo https://github.com/USUARIO/archivo-electoral}"
REPO="${REPO_URL#https://github.com/}"; REPO="${REPO%.git}"; REPO="${REPO%/}"
CASA=/var/lib/buzon
PUERTO=8080

echo "== Instalando programas"
apt-get update -q
apt-get install -y -q tor ffmpeg git python3-venv gh qrencode curl

id buzon >/dev/null 2>&1 || useradd --system --create-home --home-dir "$CASA" --shell /usr/sbin/nologin buzon

if [ ! -f /etc/buzon.env ]; then
  echo
  echo "Pegue el token de GitHub (docs/buzon.md, paso 2). No se verá al pegarlo. Luego pulse Enter:"
  read -rs TOKEN
  CLAVE=$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)
  ( umask 027; printf 'GH_TOKEN=%s\nGITHUB_REPOSITORY=%s\nBUZON_CLAVE=%s\n' "$TOKEN" "$REPO" "$CLAVE" > /etc/buzon.env )
  chown root:buzon /etc/buzon.env
fi
grep -q '^BUZON_CLAVE=' /etc/buzon.env || echo "BUZON_CLAVE=$(head -c 18 /dev/urandom | base64 | tr -d '/+=' | head -c 20)" >> /etc/buzon.env

echo "== Descargando el archivo electoral"
sudo -u buzon bash -euo pipefail -c "
  cd '$CASA'
  [ -d repo ] || git clone -q 'https://github.com/$REPO.git' repo
  git -C repo config credential.helper '!f() { echo username=x-access-token; echo \"password=\$GH_TOKEN\"; }; f'
  git -C repo config user.name 'Buzón'
  git -C repo config user.email 'buzon@users.noreply.github.com'
  [ -d venv ] || python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
  venv/bin/pip install -q -r repo/requirements.txt
  mkdir -p recibido/pendiente recibido/aprobado
"

echo "== Dirección .onion (Tor)"
if ! grep -q "HiddenServiceDir /var/lib/tor/buzon/" /etc/tor/torrc; then
  printf '\n# Buzón del archivo electoral\nHiddenServiceDir /var/lib/tor/buzon/\nHiddenServicePort 80 127.0.0.1:%s\n' "$PUERTO" >> /etc/tor/torrc
fi
systemctl enable tor >/dev/null 2>&1 || true
systemctl restart tor
for _ in $(seq 60); do [ -f /var/lib/tor/buzon/hostname ] && break; sleep 2; done
ONION=$(cat /var/lib/tor/buzon/hostname)
grep -q '^BUZON_ONION=' /etc/buzon.env || echo "BUZON_ONION=$ONION" >> /etc/buzon.env

echo "== Configurando los servicios"
cat > /etc/systemd/system/buzon.service <<UNIDAD
[Unit]
Description=Buzón del archivo electoral (página web)
After=network-online.target
Wants=network-online.target

[Service]
User=buzon
WorkingDirectory=$CASA/repo
EnvironmentFile=/etc/buzon.env
Environment=BUZON_DATOS=$CASA/recibido
Environment=BUZON_PUERTO=$PUERTO
ExecStart=$CASA/venv/bin/python buzon/web.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
UNIDAD

cat > /etc/systemd/system/buzon-procesar.service <<UNIDAD
[Unit]
Description=Archivar lo que el equipo aprobó en el buzón

[Service]
Type=oneshot
User=buzon
EnvironmentFile=/etc/buzon.env
Environment=PATH=$CASA/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=RECIBIDO=$CASA/recibido/aprobado
Environment=ARCHIVO_SERIE=b
ExecStart=$CASA/repo/buzon/procesar.sh
UNIDAD

cat > /etc/systemd/system/buzon-procesar.timer <<UNIDAD
[Unit]
Description=Archivar lo aprobado en el buzón cada 15 minutos

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
UNIDAD

systemctl daemon-reload
systemctl enable --now buzon.service buzon-procesar.timer
systemctl restart buzon.service

echo
read -rp "¿Quiere también un enlace normal, que se abra en cualquier navegador sin instalar Tor? [S/n] " NORMAL
if [ "${NORMAL,,}" != "n" ]; then
  echo "== Enlace normal (Tailscale Funnel)"
  command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh
  echo "Si aparece un enlace de inicio de sesión, ábralo en el celular o en otra computadora y entre"
  echo "con su cuenta de Google, Microsoft o GitHub."
  tailscale up --hostname=buzon
  echo "Si aparece otro enlace para habilitar Funnel, ábralo y acéptelo; el comando sigue solo."
  tailscale funnel --bg "$PUERTO"
fi

bash "$CASA/repo/buzon/direccion.sh"
