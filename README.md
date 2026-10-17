# Archivo electoral

Guarda la propaganda electoral antes de que la borren, de forma que cualquiera pueda comprobar después **que existió, cuándo y quién la publicó o la pagó**. Empieza en Cali, para las elecciones territoriales del 31 de octubre de 2027, y cualquier municipio puede copiarlo.

**No guarda datos personales de ciudadanos.** Solo se registra de quién es una pieza cuando la publicó un actor público: candidato, campaña, partido, agencia, medio, personalidad pública, influenciador o institución pública. De cualquier otra fuente se guarda la pieza sola, sin enlace, sin cuenta y sin metadatos. Tampoco queda registrado quién la envió.

## Cómo aportar

**Sin cuenta y de forma anónima:** use el [buzón anónimo](docs/buzon.md) con el navegador Tor. Suba las fotos o pegue los enlaces y envíe. Dirección: *(se publica aquí cuando el buzón esté montado)*

**Con una cuenta de GitHub** (es gratis), el resultado le llega en minutos:

1. **¿Es un enlace?** (TikTok, Instagram, Facebook, YouTube, X, un anuncio de la Biblioteca de Anuncios de Meta, una página web) → [Guardar un enlace](../../issues/new?template=1-enlace.yml). Pegue el enlace y envíe.
2. **¿Es una foto o un archivo?** (una valla, un pasacalle, un volante, algo que le llegó por WhatsApp) → [Subir una foto o un archivo](../../issues/new?template=2-foto-o-archivo.yml). Arrastre la foto y envíe.

En unos minutos el sistema responde con el código de la pieza (por ejemplo `cali-2027-000143`) y cierra la solicitud. Si la envió alguien que no es del equipo, se procesa cuando alguien del equipo le ponga la etiqueta `archivar`.

**Consejos:** guarde las piezas apenas las vea; mucho contenido se borra en días. Fotografíe la propaganda, no a las personas.

Además, **cada día el sistema revisa por su cuenta las cuentas de [`cuentas.yaml`](cuentas.yaml)** y guarda sus publicaciones nuevas. Con TikTok y YouTube funciona bien; Instagram, Facebook y X suelen pedir inicio de sesión, y de esas conviene seguir enviando los enlaces a mano.

## Qué pasa con cada pieza

1. Se descarga la pieza (o se recibe la foto).
2. Si la cuenta **no** está en [`cuentas.yaml`](cuentas.yaml), se le quitan los metadatos y se olvida de dónde vino. A las fotos y videos subidos siempre se les quitan los metadatos: ubicación, fecha de la cámara y modelo del teléfono.
3. Si la cuenta **sí** está en la lista, se guarda también el enlace, la cuenta, la fecha de publicación y los números de vistas y reacciones, y se le pide al [Wayback Machine](https://web.archive.org) del Internet Archive que haga su propia captura como testigo independiente. Las páginas web y los anuncios se capturan además completos (formato WACZ).
4. Se calcula la **huella** (SHA-256) de cada archivo y se sella con [OpenTimestamps](https://opentimestamps.org), que la ancla en Bitcoin. Eso prueba que el archivo existía ese día y que no ha cambiado.
5. La ficha y las huellas quedan en la carpeta [`piezas/`](piezas); los archivos, en las [versiones (releases)](../../releases) del repositorio, una por mes.

Cada ficha dice quién está detrás de la pieza y con qué evidencia: campaña oficial, tercero contratado, tercero sin declarar, personalidad pública o influenciador, institución u órgano público, otro actor público, desconocida o no atribuida. Cuando aparece evidencia nueva (la Biblioteca de Anuncios, los gastos de campaña en Cuentas Claras), el equipo cambia la clasificación con el formulario [Cambiar la fuente](../../issues/new?template=3-reclasificar.yml), y el cambio queda en el historial de la ficha. Lo anterior no se borra.

## Cómo comprobar una pieza

Sin instalar nada:

1. Abra la ficha de la pieza en `piezas/AAAA/MM/<código>/` y descargue el archivo desde el enlace de `copias`.
2. Suba `huellas.sha256.ots` a [opentimestamps.org](https://opentimestamps.org) junto con `huellas.sha256`: dice en qué fecha quedó sellado.
3. Compruebe que la huella del archivo descargado es la que aparece en `huellas.sha256` (en Linux o Mac: `sha256sum archivo`; en Windows: `certutil -hashfile archivo SHA256`).

Con el script: `python herramientas/archivar.py verificar cali-2027-000143` descarga los archivos y los compara.

## Para el equipo

- [Cómo se decide quién está detrás de una pieza, y por qué se puede confiar](docs/metodo.md)
- [Cómo montar el archivo en otro municipio](docs/nuevo-municipio.md)
- Mantener al día [`cuentas.yaml`](cuentas.yaml) con el formulario [Agregar una cuenta pública](../../issues/new?template=4-agregar-cuenta.yml): cuando se inscriba cada candidato, sus cuentas y las de su campaña; las personalidades públicas e influenciadores que lo apoyen, y las instituciones (Presidencia, Gobernación, Alcaldía o cualquier otro órgano) y sus funcionarios.
- [Montar el buzón anónimo](docs/buzon.md)
- El script también funciona desde la línea de comandos: `python herramientas/archivar.py -h`.
