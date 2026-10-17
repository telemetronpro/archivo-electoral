#!/usr/bin/env python3
"""Archiva propaganda electoral de forma verificable y sin datos personales de ciudadanos.

Uso:
  archivar.py enlace URL [--candidato T] [--nota T]
  archivar.py archivo RUTA... --tipo valla|volante|mensajeria|otro [--lugar T] [--candidato T] [--nota T]
  archivar.py desde-issue          lee el formulario de GitHub de la variable ISSUE_BODY
  archivar.py reclasificar ID --categoria C --confianza alta|media|baja --evidencia T
  archivar.py seguir [--maximo N]   guarda las publicaciones nuevas de las cuentas de cuentas.yaml
  archivar.py agregar-cuenta --plataforma P --cuenta C --nombre N --categoria K --respaldo URL
  archivar.py buzon CARPETA        archiva lo que llegó al buzón de OnionShare y lo borra
  archivar.py sellos               completa los sellos de tiempo pendientes
  archivar.py verificar ID [--carpeta DIR]
  archivar.py revisar              comprueba que las fichas cumplan las reglas

Regla de privacidad: solo se guarda el enlace y la cuenta cuando la cuenta está en
cuentas.yaml (candidatos, campañas, partidos, agencias, medios, personalidades públicas e
influenciadores). De cualquier otra fuente se guarda la pieza sola, sin metadatos, sin
enlace y sin cuenta. Nunca se guarda quién envió la pieza.
"""

import argparse
import datetime as dt
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import yaml

RAIZ = Path(__file__).resolve().parent.parent
PIEZAS = RAIZ / "piezas"
SALIDA = RAIZ / "salida"  # archivos pesados; no van en git
USER_AGENT = "archivo-electoral (+https://github.com)"

CATEGORIAS = {
    "campaña-oficial": "Campaña oficial",
    "tercero-contratado": "Tercero contratado",
    "tercero-sin-declarar": "Tercero sin declarar (sospecha)",
    "personalidad-publica": "Personalidad pública o influenciador",
    "institucion": "Institución u órgano público",
    "otro-actor-publico": "Otro actor público",
    "desconocida": "Desconocida",
    "no-atribuida": "No atribuida (por privacidad no se guardó la fuente)",
}
CONFIANZAS = ("alta", "media", "baja")
# Categorías que puede tener una cuenta de cuentas.yaml.
CATEGORIAS_CUENTA = ("campaña-oficial", "tercero-contratado", "personalidad-publica", "institucion",
                     "otro-actor-publico")
# Tipos de institución para la categoría "institucion". Con "Otra" se escribe el órgano a mano.
INSTITUCIONES = (
    "Presidencia de la República", "Vicepresidencia", "Ministerio o departamento administrativo",
    "Gobernación", "Alcaldía", "Secretaría departamental o municipal", "Congreso",
    "Asamblea departamental", "Concejo municipal", "Junta administradora local",
    "Fuerza Pública (Policía, Ejército, Armada, Fuerza Aeroespacial)",
    "Organismo de control (Procuraduría, Contraloría, Defensoría, Personería)",
    "Organización electoral (Registraduría, CNE)", "Rama judicial o Fiscalía",
    "Entidad descentralizada o empresa pública", "Otra",
)
PLATAFORMAS = ("tiktok", "instagram", "facebook", "youtube", "x", "threads", "telegram", "web")
TIPOS_ARCHIVO = {
    "valla": "Valla o pasacalle",
    "volante": "Volante o afiche",
    "mensajeria": "Cadena de WhatsApp o Telegram",
    "otro": "Otro",
}
# Campos de los metadatos de la plataforma que se conservan. Nada de comentarios,
# etiquetados ni datos de quienes interactúan.
CAMPOS_METADATOS = (
    "id", "title", "description", "uploader", "uploader_id", "uploader_url", "channel",
    "channel_id", "channel_url", "timestamp", "upload_date", "duration", "webpage_url",
    "extractor_key", "view_count", "like_count", "comment_count", "repost_count",
)


class ErrorArchivo(Exception):
    """Error que se le muestra tal cual a quien envió la pieza."""


class ErrorTemporal(Exception):
    """Falla que puede arreglarse sola al reintentar (red, GitHub)."""


# ---------------------------------------------------------------- configuración

def leer_yaml(ruta):
    with open(ruta, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def escribir_yaml(ruta, datos):
    with open(ruta, "w", encoding="utf-8") as f:
        yaml.safe_dump(datos, f, sort_keys=False, allow_unicode=True, width=100)


def config():
    return leer_yaml(RAIZ / "config.yaml")


def cuentas():
    return leer_yaml(RAIZ / "cuentas.yaml").get("cuentas") or []


def ahora():
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def iso(momento):
    return momento.isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------- plataformas y cuentas

def plataforma_de(url):
    host = (urlparse(url).hostname or "").lower().removeprefix("www.").removeprefix("m.")
    ruta = urlparse(url).path
    if host.endswith("facebook.com") and ruta.startswith("/ads/library"):
        return "biblioteca-anuncios-meta"
    for sufijo, nombre in (
        ("tiktok.com", "tiktok"), ("instagram.com", "instagram"), ("facebook.com", "facebook"),
        ("fb.watch", "facebook"), ("youtube.com", "youtube"), ("youtu.be", "youtube"),
        ("x.com", "x"), ("twitter.com", "x"), ("threads.net", "threads"),
        ("threads.com", "threads"), ("t.me", "telegram"),
    ):
        if host == sufijo or host.endswith("." + sufijo):
            return nombre
    return "web"


def normalizar(texto):
    """'@Campaña', 'https://tiktok.com/@campaña/' y 'campaña' quedan iguales."""
    texto = str(texto or "").strip().lower()
    if texto.startswith(("http://", "https://")):
        partes = [p for p in urlparse(texto).path.split("/") if p]
        texto = partes[-1] if partes else (urlparse(texto).hostname or "")
    return texto.lstrip("@").rstrip("/").removeprefix("www.")


def identificadores(url, metadatos):
    """Todo lo que podría identificar la cuenta que publicó la pieza."""
    ids = set()
    partes = [p for p in urlparse(url).path.split("/") if p]
    if partes and partes[0].startswith("@"):  # tiktok.com/@cuenta, youtube.com/@cuenta
        ids.add(normalizar(partes[0]))
    for campo in ("uploader", "uploader_id", "uploader_url", "channel", "channel_id",
                  "channel_url", "username", "owner", "fullname"):
        if metadatos.get(campo):
            ids.add(normalizar(metadatos[campo]))
    for campo in ("author", "user"):  # gallery-dl
        if isinstance(metadatos.get(campo), dict):
            for clave in ("name", "nick", "id"):
                if metadatos[campo].get(clave):
                    ids.add(normalizar(metadatos[campo][clave]))
    ids.discard("")
    return ids


def buscar_cuenta(url, plataforma, metadatos, lista=None):
    """Devuelve la entrada de cuentas.yaml que publicó la pieza, o None."""
    lista = cuentas() if lista is None else lista
    if plataforma == "web":
        dominio = normalizar(urlparse(url).hostname or "")
        for c in lista:
            if c.get("plataforma") == "web" and dominio in (
                    normalizar(c.get("cuenta")), *map(normalizar, c.get("alias") or [])):
                return c
        return None
    ids = identificadores(url, metadatos)
    for c in lista:
        if c.get("plataforma") != plataforma:
            continue
        nombres = {normalizar(c.get("cuenta")), *map(normalizar, c.get("alias") or [])}
        if ids & nombres:
            return c
    return None


# ---------------------------------------------------------------- descargas

def correr(comando, **kw):
    return subprocess.run(comando, capture_output=True, text=True, **kw)


def descargar_con_yt_dlp(url, carpeta):
    r = correr(["yt-dlp", "--no-playlist", "--write-info-json", "--no-write-comments",
                "-o", str(carpeta / "pieza.%(ext)s"), "--", url], timeout=900)
    info = next(carpeta.glob("*.info.json"), None)
    if r.returncode != 0 or not info:
        for sobrante in carpeta.iterdir():  # descargas a medias
            sobrante.unlink()
        return None
    datos = json.loads(info.read_text(encoding="utf-8"))
    info.unlink()
    return datos


def descargar_con_gallery_dl(url, carpeta):
    r = correr(["gallery-dl", "--write-metadata", "-D", str(carpeta),
                "-f", "pieza-{num}.{extension}", "--", url], timeout=900)
    jsons = sorted(carpeta.glob("*.json"))
    if r.returncode != 0 or not jsons:
        for sobrante in carpeta.iterdir():
            sobrante.unlink()
        return None
    datos = json.loads(jsons[0].read_text(encoding="utf-8"))
    for j in jsons:
        j.unlink()
    return datos


def limpiar_metadatos(datos):
    """Solo los campos de CAMPOS_METADATOS, más los equivalentes de gallery-dl."""
    limpio = {c: datos[c] for c in CAMPOS_METADATOS if datos.get(c) not in (None, "")}
    equivalentes = {
        "description": ("content", "caption"),
        "uploader_id": ("username",),
        "webpage_url": ("post_url",),
    }
    for campo, otros in equivalentes.items():
        for otro in otros:
            if campo not in limpio and isinstance(datos.get(otro), str):
                limpio[campo] = datos[otro]
    if "uploader" not in limpio and isinstance(datos.get("author"), dict):
        limpio["uploader"] = datos["author"].get("name") or datos["author"].get("nick")
    if "timestamp" not in limpio and isinstance(datos.get("date"), str):
        limpio["fecha"] = datos["date"]
    return limpio


def publicado_de(metadatos):
    if metadatos.get("timestamp"):
        return iso(dt.datetime.fromtimestamp(metadatos["timestamp"], dt.timezone.utc))
    if metadatos.get("fecha"):
        return str(metadatos["fecha"])
    if metadatos.get("upload_date"):
        d = metadatos["upload_date"]
        return f"{d[:4]}-{d[4:6]}-{d[6:]}"
    return None


def descargar_adjunto(url, destino):
    """Baja un adjunto de un issue de GitHub (fotos o videos arrastrados al formulario)."""
    cabeceras = {"User-Agent": USER_AGENT}
    if os.environ.get("GH_TOKEN"):
        cabeceras["Authorization"] = f"token {os.environ['GH_TOKEN']}"
    with requests.get(url, headers=cabeceras, stream=True, timeout=120) as r:
        r.raise_for_status()
        tipo = r.headers.get("Content-Type", "").split(";")[0]
        extension = mimetypes.guess_extension(tipo) or Path(urlparse(r.url).path).suffix
        ruta = destino.with_suffix(extension or ".bin")
        total = 0
        with open(ruta, "wb") as f:
            for bloque in r.iter_content(1 << 20):
                total += len(bloque)
                if total > 1 << 30:
                    raise ErrorArchivo("El archivo pesa más de 1 GB.")
                f.write(bloque)
    return ruta


# ---------------------------------------------------------------- quitar metadatos

def quitar_metadatos(ruta):
    """Devuelve una copia sin metadatos (ubicación, teléfono, fecha de la cámara, nombres).

    Las imágenes se vuelven a guardar a partir de los píxeles; los videos y audios se
    copian con ffmpeg sin metadatos ni capítulos.
    """
    from PIL import Image, ImageOps
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass

    try:
        with Image.open(ruta) as im:
            formato = "PNG" if im.format == "PNG" or im.mode in ("RGBA", "LA", "P") else "JPEG"
            im = ImageOps.exif_transpose(im)
            im = im.convert("RGBA" if formato == "PNG" else "RGB")
            limpia = Image.frombytes(im.mode, im.size, im.tobytes())
        salida = ruta.with_name(ruta.stem + "-limpia" + (".png" if formato == "PNG" else ".jpg"))
        limpia.save(salida, formato, **({"quality": 95} if formato == "JPEG" else {}))
        return salida
    except OSError:
        pass  # no es una imagen

    if not shutil.which("ffmpeg"):
        raise ErrorArchivo("Falta ffmpeg para limpiar videos y audios.")
    sonda = correr(["ffprobe", "-v", "error", "-show_entries", "format=format_name",
                    "-of", "default=nw=1:nk=1", str(ruta)])
    if sonda.returncode != 0:
        raise ErrorArchivo(f"No se reconoce el archivo {ruta.name} como foto, video o audio. "
                           "Si es un PDF, súbalo como foto o captura de la pieza.")
    extension = ruta.suffix if ruta.suffix not in ("", ".bin") else ".mp4"
    salida = ruta.with_name(ruta.stem + "-limpio" + extension)
    r = correr(["ffmpeg", "-y", "-v", "error", "-i", str(ruta), "-map", "0", "-map_metadata", "-1",
                "-map_chapters", "-1", "-c", "copy", "-fflags", "+bitexact",
                "-flags:v", "+bitexact", "-flags:a", "+bitexact", str(salida)])
    if r.returncode != 0:
        raise ErrorArchivo(f"No se pudo limpiar {ruta.name}: {r.stderr.strip()[-300:]}")
    return salida


# ---------------------------------------------------------------- testigos y sellos

def guardar_en_wayback(url):
    """Pide al Wayback Machine del Internet Archive una captura propia de la URL."""
    acceso, secreto = os.environ.get("IA_ACCESS_KEY"), os.environ.get("IA_SECRET_KEY")
    try:
        if acceso and secreto:
            cab = {"Accept": "application/json", "Authorization": f"LOW {acceso}:{secreto}",
                   "User-Agent": USER_AGENT}
            trabajo = requests.post("https://web.archive.org/save", headers=cab,
                                    data={"url": url}, timeout=120).json()["job_id"]
            for _ in range(36):
                time.sleep(5)
                estado = requests.get(f"https://web.archive.org/save/status/{trabajo}",
                                      headers=cab, timeout=60).json()
                if estado.get("status") == "success":
                    return f"https://web.archive.org/web/{estado['timestamp']}/{estado['original_url']}"
                if estado.get("status") == "error":
                    return None
            return None
        r = requests.get(f"https://web.archive.org/save/{url}", headers={"User-Agent": USER_AGENT},
                         timeout=300)
        lugar = r.headers.get("Content-Location") or urlparse(r.url).path
        if r.ok and lugar.startswith("/web/"):
            return "https://web.archive.org" + lugar
    except (requests.RequestException, ValueError, KeyError):
        pass
    return None


def capturar_wacz(url, carpeta):
    """Captura la página completa con Browsertrix (solo donde hay Docker, como en GitHub)."""
    if os.environ.get("ARCHIVO_WACZ") == "no" or not shutil.which("docker"):
        return None
    trabajo = Path(tempfile.mkdtemp(prefix="wacz-"))
    correr(["docker", "run", "--rm", "-v", f"{trabajo}:/crawls/", "webrecorder/browsertrix-crawler",
            "crawl", "--url", url, "--scopeType", "page", "--generateWACZ",
            "--collection", "pieza", "--pageLoadTimeout", "90"], timeout=900)
    wacz = next(trabajo.glob("collections/pieza/*.wacz"), None)
    if not wacz:
        return None
    destino = carpeta / "pagina.wacz"
    shutil.copyfile(wacz, destino)
    return destino


def sellar(ruta):
    """Sello de tiempo de OpenTimestamps (queda confirmado en Bitcoin unas horas después)."""
    r = correr(["ots", "stamp", str(ruta)], timeout=300)
    return r.returncode == 0 and Path(str(ruta) + ".ots").exists()


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


# ---------------------------------------------------------------- publicar archivos pesados

def publicar_archivos(id_pieza, archivos, momento):
    """Sube los archivos a una versión (release) mensual del repositorio y, si hay claves,
    al Internet Archive. Devuelve {nombre: [enlaces]}."""
    copias = {a.name: [] for a in archivos}
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo and shutil.which("gh"):
        etiqueta = f"piezas-{momento:%Y-%m}"
        if correr(["gh", "release", "view", etiqueta]).returncode != 0:
            correr(["gh", "release", "create", etiqueta, "--title", f"Piezas de {momento:%Y-%m}",
                    "--notes", "Archivos de las piezas registradas este mes. Las huellas y los "
                    "sellos de tiempo están en la carpeta piezas/ del repositorio."])
        subidos = []
        for a in archivos:
            nombre = f"{id_pieza}--{a.name}"
            renombrado = a.with_name(nombre)
            shutil.copyfile(a, renombrado)
            subidos.append(renombrado)
        r = correr(["gh", "release", "upload", etiqueta, "--clobber", *map(str, subidos)])
        if r.returncode != 0:
            raise ErrorTemporal(f"No se pudieron subir los archivos: {r.stderr.strip()[-300:]}")
        for a in archivos:
            copias[a.name].append(
                f"https://github.com/{repo}/releases/download/{etiqueta}/{id_pieza}--{a.name}")
    if os.environ.get("IA_ACCESS_KEY") and os.environ.get("IA_SECRET_KEY"):
        try:
            from internetarchive import upload
            item = f"archivo-electoral-{id_pieza}"
            upload(item, files={a.name: str(a) for a in archivos},
                   metadata={"title": f"Archivo electoral {id_pieza}", "mediatype": "data",
                             "subject": "propaganda electoral; elecciones; Colombia"},
                   access_key=os.environ["IA_ACCESS_KEY"], secret_key=os.environ["IA_SECRET_KEY"])
            for a in archivos:
                copias[a.name].append(f"https://archive.org/download/{item}/{a.name}")
        except Exception as e:  # una copia de más no debe tumbar el registro
            print(f"Aviso: no se pudo subir al Internet Archive: {e}", file=sys.stderr)
    return copias


# ---------------------------------------------------------------- registro

def nuevo_id(cfg, momento):
    # El buzón usa su propia serie (ARCHIVO_SERIE=b) para no chocar con GitHub Actions.
    prefijo = f"{cfg['prefijo']}-{momento:%Y}-{os.environ.get('ARCHIVO_SERIE', '')}"
    numeros = [int(p.name.removeprefix(prefijo)) for p in PIEZAS.glob(f"*/*/{prefijo}*")
               if p.name.removeprefix(prefijo).isdigit()]
    return f"{prefijo}{max(numeros, default=0) + 1:06d}"


def carpeta_de(id_pieza):
    encontradas = list(PIEZAS.glob(f"*/*/{id_pieza}"))
    if not encontradas:
        raise ErrorArchivo(f"No existe la pieza {id_pieza}.")
    return encontradas[0]


def registrar(archivos, ficha, momento, prueba=False):
    """Calcula huellas, sella, sube los archivos y escribe la ficha. Devuelve la carpeta."""
    cfg = config()
    id_pieza = nuevo_id(cfg, momento)
    carpeta = (Path(tempfile.mkdtemp(prefix="prueba-")) if prueba
               else PIEZAS / f"{momento:%Y}" / f"{momento:%m}" / id_pieza)
    carpeta.mkdir(parents=True, exist_ok=True)

    salida = SALIDA / id_pieza
    salida.mkdir(parents=True, exist_ok=True)
    finales = []
    for a in archivos:
        destino = salida / a.name
        shutil.copyfile(a, destino)
        finales.append(destino)

    huellas = carpeta / "huellas.sha256"
    huellas.write_text("".join(f"{sha256(a)}  {a.name}\n" for a in finales), encoding="utf-8")
    sellado = sellar(huellas)
    try:
        copias = {} if prueba else publicar_archivos(id_pieza, finales, momento)
    except ErrorTemporal:
        shutil.rmtree(carpeta)  # sin ficha a medias; el código queda libre para el reintento
        raise

    completa = {
        "id": id_pieza,
        "municipio": cfg["municipio"],
        "eleccion": cfg["eleccion"],
        "registrado": iso(momento),
        **ficha,
        "archivos": [
            {"nombre": a.name, "sha256": sha256(a), "bytes": a.stat().st_size,
             "copias": copias.get(a.name, [])}
            for a in finales
        ],
        "sello_tiempo": {"archivo": "huellas.sha256.ots",
                         "estado": "pendiente" if sellado else "falló; reintentar"},
    }
    completa["historial"] = [{"fecha": iso(momento), "cambio": "Registrada. Fuente: "
                              + CATEGORIAS[completa["fuente"]["categoria"]]}]
    escribir_yaml(carpeta / "ficha.yaml", completa)
    return carpeta


def archivar_enlace(url, candidato=None, nota=None, prueba=False, cuenta=None):
    url = url.strip()
    if not re.match(r"https?://", url):
        raise ErrorArchivo("El enlace debe empezar por http:// o https://")
    momento = ahora()
    plataforma = plataforma_de(url)
    trabajo = Path(tempfile.mkdtemp(prefix="pieza-"))
    avisos = []

    metadatos = {}
    if plataforma not in ("web", "biblioteca-anuncios-meta"):
        crudos = descargar_con_yt_dlp(url, trabajo) or descargar_con_gallery_dl(url, trabajo)
        metadatos = limpiar_metadatos(crudos) if crudos else {}
        if not crudos:
            avisos.append("No se pudo descargar el contenido (puede pedir inicio de sesión). "
                          "Si lo tiene guardado, súbalo con el formulario de foto o archivo.")
    medios = sorted(p for p in trabajo.iterdir() if p.is_file())

    # La pauta de la Biblioteca de Anuncios es pública por ley ("Pagado por").
    cuenta = cuenta or buscar_cuenta(url, plataforma, metadatos)
    atribuida = cuenta is not None or plataforma == "biblioteca-anuncios-meta"

    if not atribuida:
        if not medios:
            raise ErrorArchivo(
                "La cuenta no está en cuentas.yaml y no se pudo bajar la pieza. Por privacidad, "
                "de cuentas que no son de actores públicos solo se guarda la pieza, nunca el "
                "enlace. Si la cuenta es de una campaña, agencia o medio, agréguela a "
                "cuentas.yaml y vuelva a enviar el enlace.")
        limpios = [quitar_metadatos(m) for m in medios]
        archivos = [l.rename(l.with_name(f"pieza-{i}{l.suffix}" if len(limpios) > 1 else f"pieza{l.suffix}"))
                    for i, l in enumerate(limpios, 1)]
        ficha = {
            "tipo": "enlace",
            "plataforma": plataforma,
            "fuente_registrada": False,
            "candidatos": [candidato] if candidato else [],
            "nota": nota or None,
            "testigos": [],
            "fuente": {"categoria": "no-atribuida", "confianza": None, "evidencia": [
                "La cuenta no está en cuentas.yaml; por privacidad no se guardó el enlace, "
                "la cuenta ni los metadatos."]},
        }
        avisos.append("La cuenta no está en cuentas.yaml: se guardó solo la pieza. Si es de una "
                      "campaña, agencia o medio, agréguela a cuentas.yaml y vuelva a enviarla.")
    else:
        archivos = medios
        if metadatos:
            ruta_meta = trabajo / "metadatos.json"
            ruta_meta.write_text(json.dumps(metadatos, ensure_ascii=False, indent=2), encoding="utf-8")
            archivos.append(ruta_meta)
        if plataforma in ("web", "biblioteca-anuncios-meta"):
            wacz = capturar_wacz(url, trabajo)
            if wacz:
                archivos.append(wacz)
        testigo = guardar_en_wayback(url)
        if not testigo:
            avisos.append("El Wayback Machine no hizo la captura; pídala a mano en "
                          "https://web.archive.org/save y en https://archive.ph y agréguela a la ficha.")
        if not archivos:
            avisos.append("No quedó ningún archivo propio de la pieza; solo el testigo externo.")
        if cuenta:
            de_quien = cuenta["nombre"] + (f" ({cuenta['institucion']})" if cuenta.get("institucion") else "")
            fuente = {"categoria": cuenta["categoria"], "confianza": "alta" if cuenta.get("respaldo") else "media",
                      "evidencia": [f"La cuenta es de {de_quien} según cuentas.yaml"
                                    + (f" (respaldo: {cuenta['respaldo']})" if cuenta.get("respaldo") else "")]}
            if cuenta.get("institucion"):
                fuente["institucion"] = cuenta["institucion"]
        else:
            fuente = {"categoria": "desconocida", "confianza": None, "evidencia": [
                "Anuncio de la Biblioteca de Anuncios de Meta: revisar el aviso 'Pagado por' en la "
                "captura y reclasificar."]}
        ficha = {
            "tipo": "enlace",
            "plataforma": plataforma,
            "fuente_registrada": True,
            "url": url,
            "cuenta": cuenta["cuenta"] if cuenta else None,
            "publicado": publicado_de(metadatos),
            "candidatos": [candidato] if candidato else ([cuenta["nombre"]] if cuenta else []),
            "nota": nota or None,
            "testigos": [testigo] if testigo else [],
            "fuente": fuente,
        }
    if not archivos:
        raise ErrorArchivo("No se pudo guardar nada de la pieza. " + " ".join(avisos))
    return registrar(archivos, ficha, momento, prueba), avisos


def archivar_archivos(rutas, tipo, lugar=None, candidato=None, nota=None, prueba=False):
    if tipo not in TIPOS_ARCHIVO:
        raise ErrorArchivo(f"Tipo desconocido: {tipo}")
    if not rutas:
        raise ErrorArchivo("No llegó ningún archivo. Arrastre la foto o el video al formulario.")
    momento = ahora()
    limpios = [quitar_metadatos(Path(r)) for r in rutas]
    archivos = [l.rename(l.with_name(f"pieza-{i}{l.suffix}" if len(limpios) > 1 else f"pieza{l.suffix}"))
                for i, l in enumerate(limpios, 1)]
    ficha = {
        "tipo": tipo,
        "fuente_registrada": False,
        "lugar": lugar or None,
        "candidatos": [candidato] if candidato else [],
        "nota": nota or None,
        "testigos": [],
        "fuente": {"categoria": "desconocida" if tipo != "mensajeria" else "no-atribuida",
                   "confianza": None, "evidencia": []},
    }
    return registrar(archivos, ficha, momento, prueba), []


def reclasificar(id_pieza, categoria, confianza, evidencia):
    if categoria not in CATEGORIAS or categoria == "no-atribuida":
        raise ErrorArchivo(f"Categoría no válida: {categoria}")
    if confianza not in CONFIANZAS:
        raise ErrorArchivo(f"Confianza no válida: {confianza}")
    if not (evidencia or "").strip():
        raise ErrorArchivo("Hace falta la evidencia que sostiene el cambio.")
    carpeta = carpeta_de(id_pieza)
    ficha = leer_yaml(carpeta / "ficha.yaml")
    anterior = ficha["fuente"]["categoria"]
    lineas = [l.strip(" -•\t") for l in evidencia.strip().splitlines() if l.strip(" -•\t")]
    ficha["fuente"] = {"categoria": categoria, "confianza": confianza,
                       "evidencia": ficha["fuente"].get("evidencia", []) + lineas}
    ficha["historial"].append({"fecha": iso(ahora()),
                               "cambio": f"Fuente: {CATEGORIAS[anterior]} → {CATEGORIAS[categoria]} "
                                         f"(confianza {confianza})"})
    escribir_yaml(carpeta / "ficha.yaml", ficha)
    return carpeta


def perfil_de(cuenta):
    """Enlace al perfil de una cuenta, para listar sus publicaciones con yt-dlp."""
    nombre = str(cuenta.get("cuenta") or "")
    if nombre.startswith(("http://", "https://")):
        return nombre
    handle = "@" + nombre.lstrip("@")
    return {"tiktok": f"https://www.tiktok.com/{handle}",
            "youtube": f"https://www.youtube.com/{handle}/videos",
            "instagram": f"https://www.instagram.com/{handle[1:]}/",
            "facebook": f"https://www.facebook.com/{handle[1:]}",
            "x": f"https://x.com/{handle[1:]}"}.get(cuenta.get("plataforma"))


def seguir(maximo=10):
    """Archiva las publicaciones recientes de las cuentas de cuentas.yaml que aún no estén."""
    conocidas = {leer_yaml(f).get("url") for f in PIEZAS.glob("*/*/*/ficha.yaml")}
    informe = []
    for c in cuentas():
        perfil = perfil_de(c)
        if c.get("plataforma") == "web" or not perfil:
            continue
        r = correr(["yt-dlp", "--flat-playlist", "--playlist-end", str(maximo),
                    "--print", "%(url)s", "--", perfil], timeout=600)
        enlaces = [u for u in r.stdout.split() if u.startswith("http")]
        if not enlaces:
            informe.append(f"- {c['nombre']} ({c['plataforma']}): no se pudo leer el perfil")
            continue
        for url in enlaces:
            if url in conocidas:
                continue
            try:
                carpeta, _ = archivar_enlace(url, cuenta=c)
                conocidas.add(url)
                informe.append(f"- {c['nombre']}: {carpeta.name}")
            except ErrorArchivo as e:
                informe.append(f"- {c['nombre']}: {url} no se archivó: {e}")
    return informe


def agregar_cuenta(plataforma, cuenta, nombre, categoria, respaldo, institucion=None, otra=None):
    """Agrega una cuenta pública al final de cuentas.yaml, sin tocar los comentarios.

    Si la categoría es "institucion", hay que decir cuál: un tipo de INSTITUCIONES o, con
    "Otra" (o sin tipo), el nombre del órgano escrito a mano en `otra`.
    """
    if plataforma not in PLATAFORMAS:
        raise ErrorArchivo(f"Plataforma no válida: {plataforma}")
    if categoria not in CATEGORIAS_CUENTA:
        raise ErrorArchivo(f"Categoría no válida: {categoria}")
    institucion, otra = (institucion or "").strip(), (otra or "").strip()
    if categoria == "institucion":
        if institucion and institucion != "Otra" and institucion not in INSTITUCIONES:
            raise ErrorArchivo(f"Tipo de institución no válido: {institucion}")
        if institucion in ("", "Otra"):
            if not otra:
                raise ErrorArchivo("Diga qué institución u órgano es: elija un tipo o escríbalo "
                                   "en 'Otra institución u órgano'.")
            institucion = otra
    else:
        institucion = ""
    if not re.match(r"https?://", respaldo or ""):
        raise ErrorArchivo("El respaldo debe ser un enlace que muestre que la cuenta es de un "
                           "actor público.")
    cuenta, nombre = (cuenta or "").strip(), (nombre or "").strip()
    if not cuenta or not nombre:
        raise ErrorArchivo("Faltan la cuenta o el nombre.")
    for c in cuentas():
        if c.get("plataforma") == plataforma and normalizar(c.get("cuenta")) == normalizar(cuenta):
            raise ErrorArchivo(f"La cuenta ya está en cuentas.yaml como {c['nombre']}.")
    datos = {"plataforma": plataforma, "cuenta": cuenta, "nombre": nombre, "categoria": categoria}
    if institucion:
        datos["institucion"] = institucion
    datos["respaldo"] = respaldo.strip()
    entrada = yaml.safe_dump([datos], sort_keys=False, allow_unicode=True, width=100)
    ruta = RAIZ / "cuentas.yaml"
    texto = ruta.read_text(encoding="utf-8")
    if not texto.endswith("\n"):
        texto += "\n"
    sangria = re.search(r"^( *)- \w", texto, re.M)  # la de las entradas que ya hay
    sangria = sangria.group(1) if sangria else "  "
    texto += "\n" + "".join(sangria + linea + "\n" for linea in entrada.splitlines())
    ruta.write_text(texto, encoding="utf-8")
    return (f"Cuenta agregada: {nombre} ({plataforma}: {cuenta}), {CATEGORIAS[categoria]}"
            + (f": {institucion}." if institucion else "."))


PALABRAS_TIPO = (
    (r"valla|pasacalle", "valla"),
    (r"volante|afiche|cartel|panfleto", "volante"),
    (r"whats|telegram|cadena|reenvi", "mensajeria"),
)


def procesar_buzon(carpeta):
    """Archiva lo que el equipo aprobó en el buzón y lo borra.

    Cada envío es <fecha>/<id>-message.txt (el mensaje) y <fecha>/<id>/ (los archivos), como
    los guarda OnionShare y como los guarda buzon/web.py. El buzón web escribe al comienzo del
    mensaje las líneas "tipo:" y "lugar:"; si no están, el tipo y la comuna se deducen del
    texto. Del mensaje solo se usan los enlaces, el tipo y el lugar; el resto del texto no se
    guarda en ninguna parte. Si algo falla por la red, el envío se deja para el siguiente
    intento.
    """
    carpeta = Path(carpeta)
    informe = []
    envios = {}
    for ruta in sorted(carpeta.glob("*/*")):
        if ruta.is_dir():
            envios.setdefault((ruta.parent, ruta.name), {})["archivos"] = ruta
        elif ruta.name.endswith("-message.txt"):
            envios.setdefault((ruta.parent, ruta.name.removesuffix("-message.txt")), {})["mensaje"] = ruta
    for (_, id_envio), partes in envios.items():
        mensaje = partes.get("mensaje")
        texto = mensaje.read_text(encoding="utf-8", errors="replace") if mensaje else ""
        tipo = re.search(r"^tipo:[ \t]*(\S+)[ \t]*$", texto, re.M)
        tipo = tipo.group(1) if tipo and tipo.group(1) in TIPOS_ARCHIVO else next(
            (t for patron, t in PALABRAS_TIPO if re.search(patron, texto, re.I)), "otro")
        lugar = re.search(r"^lugar:[ \t]*(\S.{0,59})$", texto, re.M) or re.search(r"comuna\s*\d+", texto, re.I)
        lugar = (lugar.group(1).strip() if lugar.re.groups else lugar.group(0).capitalize()) if lugar else None
        try:
            if partes.get("archivos"):
                rutas = sorted(p for p in partes["archivos"].rglob("*") if p.is_file())
                if rutas:
                    try:
                        hecho, _ = archivar_archivos(rutas, tipo, lugar)
                        informe.append(f"- {hecho.name}: {TIPOS_ARCHIVO[tipo].lower()}")
                    except ErrorArchivo as e:
                        informe.append(f"- un envío no se archivó: {e}")
                shutil.rmtree(partes["archivos"])
            enlaces = list(dict.fromkeys(u.rstrip(".,;)") for u in re.findall(r"https?://\S+", texto)))
            while enlaces:
                try:
                    hecho, _ = archivar_enlace(enlaces[0])
                    informe.append(f"- {hecho.name}: enlace")
                except ErrorArchivo as e:
                    informe.append(f"- un enlace no se archivó: {e}")
                enlaces.pop(0)
                if mensaje:  # lo que queda por hacer, por si el siguiente falla por la red
                    mensaje.write_text("\n".join(enlaces), encoding="utf-8")
            if mensaje:
                mensaje.unlink()
        except (ErrorTemporal, requests.RequestException, subprocess.SubprocessError, OSError) as e:
            informe.append(f"- un envío quedó para el siguiente intento ({type(e).__name__})")
    for vacia in sorted(carpeta.glob("*/"), reverse=True):
        if vacia.is_dir() and not any(vacia.iterdir()):
            vacia.rmdir()
    return informe


def completar_sellos():
    """Pide a los calendarios de OpenTimestamps la prueba en Bitcoin de los sellos pendientes."""
    cambiadas = []
    for ruta_ficha in sorted(PIEZAS.glob("*/*/*/ficha.yaml")):
        ficha = leer_yaml(ruta_ficha)
        sello = ficha.get("sello_tiempo") or {}
        ots = ruta_ficha.parent / "huellas.sha256.ots"
        if sello.get("estado") == "confirmado en Bitcoin":
            continue
        if not ots.exists():
            if sellar(ruta_ficha.parent / "huellas.sha256"):
                sello["estado"] = "pendiente"
            else:
                continue
        else:
            r = correr(["ots", "upgrade", str(ots)], timeout=300)
            Path(str(ots) + ".bak").unlink(missing_ok=True)
            if "Success!" not in r.stdout + r.stderr:
                continue
            sello["estado"] = "confirmado en Bitcoin"
        ficha["sello_tiempo"] = sello
        escribir_yaml(ruta_ficha, ficha)
        cambiadas.append(ficha["id"])
    return cambiadas


# ---------------------------------------------------------------- verificar y revisar

def verificar(id_pieza, carpeta_archivos=None):
    """Comprueba que los archivos coincidan con las huellas selladas. Devuelve líneas de informe."""
    carpeta = carpeta_de(id_pieza)
    ficha = leer_yaml(carpeta / "ficha.yaml")
    informe, bien = [], True
    huellas = {}
    for linea in (carpeta / "huellas.sha256").read_text(encoding="utf-8").splitlines():
        h, nombre = linea.split(maxsplit=1)
        huellas[nombre.strip()] = h
    for a in ficha["archivos"]:
        if huellas.get(a["nombre"]) != a["sha256"]:
            bien = False
            informe.append(f"✗ {a['nombre']}: la ficha y huellas.sha256 no coinciden")
            continue
        ruta = Path(carpeta_archivos) / a["nombre"] if carpeta_archivos else None
        if ruta is None or not ruta.exists():
            ruta = None
            for enlace in a.get("copias", []):
                try:
                    destino = Path(tempfile.mkdtemp()) / a["nombre"]
                    with requests.get(enlace, stream=True, timeout=120) as r:
                        r.raise_for_status()
                        with open(destino, "wb") as f:
                            for bloque in r.iter_content(1 << 20):
                                f.write(bloque)
                    ruta = destino
                    break
                except requests.RequestException:
                    continue
        if ruta is None:
            bien = False
            informe.append(f"? {a['nombre']}: no se encontró ninguna copia")
        elif sha256(ruta) == a["sha256"]:
            informe.append(f"✓ {a['nombre']}: la huella coincide")
        else:
            bien = False
            informe.append(f"✗ {a['nombre']}: la huella NO coincide; el archivo fue alterado")
    ots = carpeta / "huellas.sha256.ots"
    if ots.exists():
        r = correr(["ots", "info", str(ots)])
        bloques = re.findall(r"BitcoinBlockHeaderAttestation\((\d+)\)", r.stdout)
        if bloques:
            informe.append(f"✓ Sello de tiempo anclado en el bloque {bloques[0]} de Bitcoin. "
                           "Para comprobarlo sin instalar nada, suba huellas.sha256 y "
                           "huellas.sha256.ots a https://opentimestamps.org")
        else:
            informe.append("… El sello de tiempo aún no está confirmado en Bitcoin.")
    else:
        bien = False
        informe.append("✗ Falta el sello de tiempo")
    return bien, informe


def revisar():
    """Reglas que toda ficha debe cumplir. Devuelve una lista de problemas."""
    problemas = []
    for ruta in sorted(PIEZAS.glob("*/*/*/ficha.yaml")):
        f = leer_yaml(ruta)
        nombre = ruta.parent.name
        if f.get("id") != nombre:
            problemas.append(f"{nombre}: el id de la ficha no coincide con la carpeta")
        if f.get("fuente_registrada") is False:
            for campo in ("url", "cuenta", "publicado"):
                if f.get(campo):
                    problemas.append(f"{nombre}: tiene '{campo}' pero la fuente no es pública")
            if f.get("testigos"):
                problemas.append(f"{nombre}: tiene testigos externos pero la fuente no es pública")
            if any(a["nombre"] == "metadatos.json" for a in f.get("archivos", [])):
                problemas.append(f"{nombre}: guarda metadatos pero la fuente no es pública")
        if (f.get("fuente") or {}).get("categoria") not in CATEGORIAS:
            problemas.append(f"{nombre}: categoría de fuente desconocida")
        huellas = (ruta.parent / "huellas.sha256")
        if not huellas.exists():
            problemas.append(f"{nombre}: falta huellas.sha256")
        else:
            listadas = {l.split(maxsplit=1)[1].strip(): l.split()[0]
                        for l in huellas.read_text(encoding="utf-8").splitlines() if l.strip()}
            if listadas != {a["nombre"]: a["sha256"] for a in f.get("archivos", [])}:
                problemas.append(f"{nombre}: huellas.sha256 no coincide con la ficha")
    return problemas


# ---------------------------------------------------------------- formularios de GitHub

def leer_formulario(texto):
    """Convierte el texto de un formulario de issue ('### Pregunta\\n\\nRespuesta') en un dict."""
    campos = {}
    for bloque in re.split(r"^### ", texto or "", flags=re.M)[1:]:
        titulo, _, valor = bloque.partition("\n")
        valor = valor.strip()
        campos[titulo.strip()] = None if valor in ("_No response_", "") else valor
    return campos


def enlaces_adjuntos(texto):
    return list(dict.fromkeys(re.findall(
        r"https://github\.com/user-attachments/(?:assets|files)/[^\s)\"'<>\]]+", texto or "")))


def desde_issue(prueba=False):
    campos = leer_formulario(os.environ.get("ISSUE_BODY", ""))
    candidato, nota = campos.get("Candidato, partido o campaña"), campos.get("Nota")
    if "Enlace" in campos:
        if not campos["Enlace"]:
            raise ErrorArchivo("Falta el enlace.")
        return archivar_enlace(campos["Enlace"].split()[0], candidato, nota, prueba)
    if "Tipo de pieza" in campos:
        tipo = next((k for k, v in TIPOS_ARCHIVO.items() if v == campos["Tipo de pieza"]), None)
        trabajo = Path(tempfile.mkdtemp(prefix="adjuntos-"))
        rutas = [descargar_adjunto(u, trabajo / f"adjunto-{i}")
                 for i, u in enumerate(enlaces_adjuntos(campos.get("Foto o video") or ""), 1)]
        return archivar_archivos(rutas, tipo, campos.get("Comuna o barrio"), candidato, nota, prueba)
    if "Cuenta o usuario" in campos:
        return None, [agregar_cuenta(campos.get("Plataforma") or "", campos.get("Cuenta o usuario"),
                                     campos.get("Nombre") or "", campos.get("Categoría") or "",
                                     campos.get("Respaldo") or "", campos.get("Tipo de institución"),
                                     campos.get("Otra institución u órgano"))]
    if "Código de la pieza" in campos:
        carpeta = reclasificar((campos["Código de la pieza"] or "").strip(),
                               campos.get("Nueva categoría") or "", campos.get("Confianza") or "",
                               campos.get("Evidencia") or "")
        return carpeta, []
    raise ErrorArchivo("No se reconoce el formulario. Use una de las plantillas del repositorio.")


# ---------------------------------------------------------------- informe

def informe(carpeta, avisos):
    if carpeta is None:
        return "\n".join(avisos) + "\n"
    ficha = leer_yaml(carpeta / "ficha.yaml")
    repo = os.environ.get("GITHUB_REPOSITORY")
    ruta = carpeta.relative_to(RAIZ) if carpeta.is_relative_to(RAIZ) else None
    enlace = f"https://github.com/{repo}/blob/HEAD/{ruta}/ficha.yaml" if repo and ruta else str(carpeta)
    lineas = [f"**Pieza `{ficha['id']}`** — [ver ficha]({enlace})", "",
              f"- Fuente: {CATEGORIAS[ficha['fuente']['categoria']]}"
              + (f" (confianza {ficha['fuente']['confianza']})" if ficha["fuente"].get("confianza") else ""),
              f"- Archivos: {', '.join(a['nombre'] for a in ficha['archivos'])}",
              f"- Sello de tiempo: {ficha['sello_tiempo']['estado']}"]
    if ficha.get("testigos"):
        lineas.append(f"- Testigo externo: {ficha['testigos'][0]}")
    lineas += [f"- ⚠️ {a}" for a in avisos]
    return "\n".join(lineas) + "\n"


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--prueba", action="store_true", default=os.environ.get("PRUEBA") == "true",
                   help="hace todo menos guardar en el repositorio y subir archivos")
    p.add_argument("--resultado", help="escribe el informe en este archivo")
    sub = p.add_subparsers(dest="orden", required=True)
    e = sub.add_parser("enlace"); e.add_argument("url")
    a = sub.add_parser("archivo"); a.add_argument("rutas", nargs="+")
    a.add_argument("--tipo", required=True, choices=TIPOS_ARCHIVO); a.add_argument("--lugar")
    for s in (e, a):
        s.add_argument("--candidato"); s.add_argument("--nota")
    sub.add_parser("desde-issue")
    r = sub.add_parser("reclasificar"); r.add_argument("id")
    r.add_argument("--categoria", required=True, choices=list(CATEGORIAS))
    r.add_argument("--confianza", required=True, choices=CONFIANZAS)
    r.add_argument("--evidencia", required=True)
    sg = sub.add_parser("seguir"); sg.add_argument("--maximo", type=int, default=10)
    ac = sub.add_parser("agregar-cuenta")
    ac.add_argument("--plataforma", required=True, choices=PLATAFORMAS)
    ac.add_argument("--cuenta", required=True); ac.add_argument("--nombre", required=True)
    ac.add_argument("--categoria", required=True, choices=CATEGORIAS_CUENTA)
    ac.add_argument("--respaldo", required=True)
    ac.add_argument("--institucion", choices=INSTITUCIONES, help="solo para la categoría institucion")
    ac.add_argument("--otra", help="nombre del órgano si no está en la lista de --institucion")
    bz = sub.add_parser("buzon"); bz.add_argument("carpeta")
    sub.add_parser("sellos")
    v = sub.add_parser("verificar"); v.add_argument("id"); v.add_argument("--carpeta")
    sub.add_parser("revisar")
    args = p.parse_args(argv)

    def escribir(texto):
        print(texto)
        if args.resultado:
            Path(args.resultado).write_text(texto, encoding="utf-8")

    try:
        if args.orden == "seguir":
            escribir("\n".join(seguir(args.maximo)) or "Nada nuevo.")
            return 0
        if args.orden == "agregar-cuenta":
            escribir(agregar_cuenta(args.plataforma, args.cuenta, args.nombre, args.categoria,
                                    args.respaldo, args.institucion, args.otra))
            return 0
        if args.orden == "buzon":
            escribir("\n".join(procesar_buzon(args.carpeta)) or "El buzón está vacío.")
            return 0
        if args.orden == "sellos":
            cambiadas = completar_sellos()
            escribir(f"Sellos actualizados: {', '.join(cambiadas) or 'ninguno'}")
            return 0
        if args.orden == "verificar":
            bien, lineas = verificar(args.id, args.carpeta)
            escribir("\n".join(lineas))
            return 0 if bien else 1
        if args.orden == "revisar":
            problemas = revisar()
            escribir("\n".join(problemas) if problemas else "Todas las fichas cumplen las reglas.")
            return 1 if problemas else 0
        if args.orden == "enlace":
            carpeta, avisos = archivar_enlace(args.url, args.candidato, args.nota, args.prueba)
        elif args.orden == "archivo":
            carpeta, avisos = archivar_archivos(args.rutas, args.tipo, args.lugar, args.candidato,
                                                args.nota, args.prueba)
        elif args.orden == "reclasificar":
            carpeta, avisos = reclasificar(args.id, args.categoria, args.confianza, args.evidencia), []
        else:
            carpeta, avisos = desde_issue(args.prueba)
        escribir(informe(carpeta, avisos))
        return 0
    except ErrorArchivo as e:
        escribir(f"❌ No se archivó: {e}\n")
        return 1
    except (ErrorTemporal, requests.RequestException, subprocess.SubprocessError) as e:
        escribir(f"❌ Falló por un problema temporal; vuelva a intentarlo más tarde. ({e})\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
