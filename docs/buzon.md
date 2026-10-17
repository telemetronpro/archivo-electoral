# Buzón

Una página web sencilla, en español, para que cualquiera envíe propaganda electoral sin cuenta, sin instalar nada y sin dar su nombre. Tiene dos direcciones que llevan a la misma página:

- **Un enlace normal** (`https://buzon….ts.net`), que se abre en cualquier celular. Es lo que se pone en carteles, con un código QR, y lo que se comparte por WhatsApp.
- **Una dirección `.onion`** para el navegador Tor, para quien necesita el máximo anonimato (alguien que trabaja en una campaña o en una entidad pública, por ejemplo). La página misma la muestra.

Nada se publica sin que una persona del equipo lo revise antes.

## Para quien envía

1. Abra el enlace del buzón o escanee el código QR.
2. Pulse **Elegir fotos o videos**, diga qué es (valla, volante, WhatsApp...) y, si quiere, la comuna o el barrio y los enlaces.
3. Pulse **Enviar**.

Lo que sí se guarda: las fotos y videos sin metadatos (ni ubicación, ni fecha de la cámara, ni modelo del teléfono), los enlaces, el tipo y el lugar. Lo que no se guarda: el nombre de los archivos, el resto del texto, la dirección IP. La página no usa cookies y no carga nada de otros sitios.

**Qué tan anónimo es:** el buzón no guarda la dirección IP de nadie. Pero con el enlace normal, la empresa que da el enlace (Tailscale) y el proveedor de internet de quien envía pueden ver que hubo una conexión, aunque no lo que se envió. Con el navegador Tor ni eso: nadie puede saber quién se conectó.

## Para el equipo: revisar lo que llega

Abra `<enlace del buzón>/revisar` e ingrese la clave del equipo (el usuario puede ser cualquiera). Por cada envío verá las fotos, los videos y el texto, con dos botones:

- **Archivar:** si es propaganda electoral. En los siguientes 15 minutos se archiva como cualquier otra pieza, con su propia serie de códigos (`cali-2027-b000001`), y se borra de la computadora.
- **Descartar:** si no es propaganda, si se ven caras de personas o placas de carros, o si es contenido ilegal o violento. Se borra de inmediato.

Revise una vez al día, como mínimo: mientras nadie lo revise, el envío espera.

## Para el equipo: montarlo

Hace falta una computadora que quede prendida y conectada a internet: una Raspberry Pi 4 o 5, un portátil viejo o un servidor barato. No hay que abrir puertos en el router ni tener una IP fija, y nadie puede averiguar dónde está la computadora.

1. Instale **Raspberry Pi OS**, **Debian** o **Ubuntu**.
2. Saque un token de GitHub para que la computadora pueda guardar las piezas: en <https://github.com/settings/personal-access-tokens/new>, póngale un nombre como "buzón"; en **Repository access** elija **Only select repositories** y este repositorio, y en **Permissions → Contents** elija **Read and write**. Copie el token.
3. En la computadora, abra una terminal y corra (cambie `USUARIO` por el de la cuenta de GitHub):

   ```
   curl -fsSLO https://raw.githubusercontent.com/USUARIO/archivo-electoral/main/buzon/instalar.sh
   sudo bash instalar.sh https://github.com/USUARIO/archivo-electoral
   ```

4. Pegue el token cuando se lo pida.
5. Cuando pregunte por el enlace normal, responda que sí. Le mostrará un enlace de [Tailscale](https://tailscale.com) (gratis): ábralo en el celular y entre con una cuenta de Google, Microsoft o GitHub. Si le muestra otro enlace para habilitar **Funnel**, ábralo y acéptelo.
6. Al final verá el enlace normal, la dirección `.onion`, la clave del equipo y dónde quedaron los códigos QR. Guarde la clave y ponga el enlace en el README, en la sección "Cómo aportar".

Las direcciones son siempre las mismas, aunque la computadora se reinicie.

## Para empezar hoy, sin computadora dedicada

Mientras consigue la computadora, puede recibir piezas con la aplicación de escritorio de [OnionShare](https://onionshare.org). Tiene dos desventajas: solo funciona con el navegador Tor, y la página está en inglés.

1. Instale OnionShare, ábralo, pulse **Conectar a Tor** y elija **Recibir archivos**.
2. Marque **Guardar esta pestaña** (así la dirección no cambia) y **Este es un servicio público** (así no hace falta una clave). En **Título personalizado** ponga: `Buzón del archivo electoral: suba fotos o pegue enlaces. No escriba su nombre.`
3. Pulse **Iniciar modo de recepción**, copie la dirección `.onion` y configure la computadora para que no se suspenda.
4. Cada día, suba lo que llegó con los formularios [Subir una foto o un archivo](../../../issues/new?template=2-foto-o-archivo.yml) y [Guardar un enlace](../../../issues/new?template=1-enlace.yml), y borre lo que ya procesó. No copie a los formularios nada del texto de los mensajes, salvo los enlaces, el tipo y la comuna.

## Mantenimiento

- Ver las direcciones, la clave y los códigos QR: `sudo bash /var/lib/buzon/repo/buzon/direccion.sh`
- Ver si está funcionando: `systemctl status buzon buzon-procesar.timer tor`
- Ver qué se archivó: `journalctl -u buzon-procesar -n 50`
- Actualizar: `sudo -u buzon git -C /var/lib/buzon/repo pull && sudo systemctl restart buzon`

Si la computadora se apaga, el buzón deja de recibir hasta que vuelva a prender; no se pierde nada de lo que ya llegó.

**Cuide la computadora:** quien la tenga en las manos puede ver lo que espera revisión, el token de GitHub y la clave del equipo. Si se pierde o se la roban, borre el token en <https://github.com/settings/tokens>.
