#!/usr/bin/env bash
# Instala el buzón anónimo (OnionShare sobre Tor) en una computadora con Debian, Ubuntu
# o Raspberry Pi OS que quede prendida. Instrucciones completas en docs/buzon.md.
#
# Uso: sudo bash instalar.sh https://github.com/USUARIO/archivo-electoral
set -euo pipefail

REPO_URL="${1:?Falta el enlace del repositorio, por ejemplo https://github.com/USUARIO/archivo-electoral}"
REPO="${REPO_URL#https://github.com/}"; REPO="${REPO%.git}"; REPO="${REPO%/}"
CASA=/var/lib/buzon

echo "== Instalando programas"
apt-get update -q
apt-get install -y -q tor ffmpeg git python3-venv gh
systemctl disable --now tor >/dev/null 2>&1 || true  # OnionShare arranca su propio Tor

id buzon >/dev/null 2>&1 || useradd --system --create-home --home-dir "$CASA" --shell /usr/sbin/nologin buzon

if [ ! -f /etc/buzon.env ]; then
  echo
  echo "Pegue el token de GitHub (docs/buzon.md, paso 2). No se verá al pegarlo. Luego pulse Enter:"
  read -rs TOKEN
  ( umask 027; printf 'GH_TOKEN=%s\nGITHUB_REPOSITORY=%s\n' "$TOKEN" "$REPO" > /etc/buzon.env )
  chown root:buzon /etc/buzon.env
fi

echo "== Descargando el archivo electoral"
sudo -u buzon bash -euo pipefail -c "
  cd '$CASA'
  [ -d repo ] || git clone -q 'https://github.com/$REPO.git' repo
  git -C repo config credential.helper '!f() { echo username=x-access-token; echo \"password=\$GH_TOKEN\"; }; f'
  git -C repo config user.name 'Buzón'
  git -C repo config user.email 'buzon@users.noreply.github.com'
  [ -d venv ] || python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
  venv/bin/pip install -q -r repo/requirements.txt onionshare-cli
  mkdir -p recibido
"

echo "== Configurando el servicio"
cat > /etc/systemd/system/buzon.service <<UNIDAD
[Unit]
Description=Buzón anónimo del archivo electoral (OnionShare)
After=network-online.target
Wants=network-online.target

[Service]
User=buzon
WorkingDirectory=$CASA
ExecStart=$CASA/venv/bin/onionshare-cli --receive --public --persistent $CASA/sesion.json --title "Buzón del archivo electoral: suba fotos o pegue enlaces. No escriba su nombre." --data-dir $CASA/recibido
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIDAD

cat > /etc/systemd/system/buzon-procesar.service <<UNIDAD
[Unit]
Description=Archivar lo que llegó al buzón

[Service]
Type=oneshot
User=buzon
EnvironmentFile=/etc/buzon.env
Environment=PATH=$CASA/venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=RECIBIDO=$CASA/recibido
Environment=ARCHIVO_SERIE=b
ExecStart=$CASA/repo/buzon/procesar.sh
UNIDAD

cat > /etc/systemd/system/buzon-procesar.timer <<UNIDAD
[Unit]
Description=Archivar lo que llegó al buzón cada 15 minutos

[Timer]
OnBootSec=5min
OnUnitActiveSec=15min

[Install]
WantedBy=timers.target
UNIDAD

systemctl daemon-reload
systemctl enable --now buzon.service buzon-procesar.timer

echo "== Esperando a que Tor publique la dirección (puede tardar unos minutos)"
for _ in $(seq 60); do
  DIRECCION=$(journalctl -u buzon -n 200 --no-pager | grep -oE 'https?://[a-z2-7]{56}\.onion[^ ]*' | tail -1 || true)
  [ -n "$DIRECCION" ] && break
  sleep 5
done
if [ -n "${DIRECCION:-}" ]; then
  echo
  echo "Listo. La dirección del buzón es:"
  echo
  echo "    $DIRECCION"
  echo
  echo "Es siempre la misma, aunque la computadora se reinicie. Publíquela en el README."
else
  echo "Tor aún no publica la dirección. Mírela más tarde con: sudo bash $CASA/repo/buzon/direccion.sh"
fi
