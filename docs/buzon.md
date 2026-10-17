# Buzón anónimo

Una página web dentro de la red Tor donde cualquiera puede subir fotos y videos o pegar enlaces, sin cuenta, sin dar su nombre y sin que nadie, ni siquiera el equipo, pueda saber quién lo envió. Usa [OnionShare](https://onionshare.org), un programa libre hecho para esto por periodistas y defensores de la privacidad.

## Para quien envía

1. Instale el navegador Tor: [Tor Browser](https://www.torproject.org/download/) en Android, Windows, Mac o Linux, u [Onion Browser](https://onionbrowser.com) en iPhone. Es gratis y se usa como cualquier navegador.
2. Abra en él la dirección del buzón (la que termina en `.onion`, publicada en el README).
3. Elija las fotos o videos y, si quiere, escriba un mensaje con enlaces o con lo que es (por ejemplo, *"valla en la comuna 19"*). Pulse **Submit** (Enviar).

No escriba su nombre ni datos personales. Del mensaje solo se usan los enlaces, el tipo de pieza (valla, pasacalle, volante, afiche, WhatsApp, Telegram) y la comuna; el resto se borra sin guardarse. A las fotos y videos se les quita la ubicación, la fecha de la cámara y el modelo del teléfono.

## Para el equipo: montarlo

Hace falta una computadora que quede prendida y conectada a internet: una Raspberry Pi 4 o 5, un portátil viejo o un servidor barato. No necesita abrir puertos en el router ni tener una IP fija: Tor se encarga de eso, y nadie puede averiguar dónde está la computadora.

1. Instale **Raspberry Pi OS**, **Debian** o **Ubuntu**.
2. Saque un token de GitHub para que la computadora pueda guardar las piezas: en <https://github.com/settings/personal-access-tokens/new>, ponga un nombre como "buzón", en **Repository access** elija **Only select repositories** y este repositorio, y en **Permissions → Contents** elija **Read and write**. Copie el token.
3. En la computadora, abra una terminal y corra:

   ```
   curl -fsSLO https://raw.githubusercontent.com/USUARIO/archivo-electoral/main/buzon/instalar.sh
   sudo bash instalar.sh https://github.com/USUARIO/archivo-electoral
   ```

   (cambie `USUARIO` por el de la cuenta de GitHub). Le pedirá el token y al final mostrará la dirección `.onion` del buzón.
4. Ponga esa dirección en el README, en la sección "Cómo aportar". Es siempre la misma, aunque la computadora se reinicie.

Cada 15 minutos la computadora archiva lo que llegó, igual que con los formularios, lo sube a GitHub y lo borra de su disco. Las piezas del buzón tienen su propia serie de códigos (`cali-2027-b000001`).

## Mantenimiento

- Ver la dirección: `sudo bash /var/lib/buzon/repo/buzon/direccion.sh`
- Ver si está funcionando: `systemctl status buzon buzon-procesar.timer`
- Ver qué se archivó: `journalctl -u buzon-procesar -n 50`
- Actualizar: `sudo -u buzon git -C /var/lib/buzon/repo pull`

Si la computadora se apaga, el buzón deja de recibir hasta que vuelva a prender; no se pierde nada de lo que ya llegó.

**Cuide la computadora:** quien la tenga en las manos puede ver lo que llegó en los últimos 15 minutos antes de que se procese, y el token de GitHub. Si se pierde o se la roban, borre el token en <https://github.com/settings/tokens>.
