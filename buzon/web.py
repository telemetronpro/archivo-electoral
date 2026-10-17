#!/usr/bin/env python3
"""Buzón web: una página sencilla para enviar piezas sin cuenta y sin datos personales.

Se publica de dos formas a la vez: con un enlace normal (por Tailscale Funnel) para quien no
usa Tor, y como dirección .onion para quien quiere el máximo anonimato. No guarda direcciones
IP, no usa cookies y no carga nada de otros sitios.

Lo que llega queda en BUZON_DATOS/pendiente hasta que alguien del equipo lo revisa en
/revisar (con la clave BUZON_CLAVE). Lo aprobado pasa a BUZON_DATOS/aprobado, de donde lo
toma procesar.sh; lo descartado se borra. Así nada se publica sin que una persona lo vea.

Uso: BUZON_CLAVE=... python buzon/web.py   (escucha en 127.0.0.1:8080)
"""

import datetime as dt
import hashlib
import hmac
import html
import mimetypes
import os
import re
import secrets
import shutil
from pathlib import Path

import yaml
from flask import Flask, Response, abort, redirect, request, send_file

DATOS = Path(os.environ.get("BUZON_DATOS", "/var/lib/buzon/recibido"))
CANDIDATOS = Path(__file__).resolve().parent.parent / "candidatos.yaml"
PENDIENTE, APROBADO = DATOS / "pendiente", DATOS / "aprobado"
CLAVE = os.environ.get("BUZON_CLAVE", "")
ONION = os.environ.get("BUZON_ONION", "")  # dirección .onion, para mostrarla y avisar a Tor Browser
TIPOS = {
    "valla": "Valla o pasacalle",
    "volante": "Volante o afiche",
    "mensajeria": "Algo que llegó por WhatsApp o Telegram",
    "otro": "Otra cosa (o solo enlaces)",
}
EXTENSIONES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".gif", ".mp4", ".mov",
               ".m4v", ".webm", ".3gp", ".mp3", ".m4a", ".ogg", ".opus", ".aac", ".wav"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

ESTILO = """
:root { --fondo:#f6f5f2; --texto:#1d1d1b; --suave:#5d5c58; --borde:#d8d6d0; --acento:#0b5d4b;
        --tarjeta:#fff; --aviso:#fff4d6; }
@media (prefers-color-scheme: dark) {
  :root { --fondo:#171716; --texto:#ecebe7; --suave:#a9a7a1; --borde:#3a3936; --acento:#5cc4a6;
          --tarjeta:#21211f; --aviso:#3a3320; } }
* { box-sizing:border-box }
body { margin:0; background:var(--fondo); color:var(--texto);
       font:17px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif }
main { max-width:560px; margin:0 auto; padding:24px 16px 48px }
h1 { font-size:1.6rem; margin:0 0 4px } h2 { font-size:1.15rem; margin:28px 0 8px }
a { color:var(--acento) } p { margin:8px 0 } .suave { color:var(--suave); font-size:.95rem }
form.envio, .tarjeta { background:var(--tarjeta); border:1px solid var(--borde); border-radius:12px; padding:16px }
label { display:block; font-weight:600; margin:16px 0 6px }
label:first-child { margin-top:0 }
input[type=text], select, textarea { width:100%; font:inherit; padding:10px; border:1px solid var(--borde);
       border-radius:8px; background:var(--fondo); color:var(--texto) }
textarea { min-height:90px }
.archivo { display:block; text-align:center; padding:22px 12px; border:2px dashed var(--borde);
           border-radius:10px; cursor:pointer; font-weight:600; color:var(--acento) }
.archivo input { display:block; margin:10px auto 0; max-width:100%; font-size:.9rem; color:var(--texto) }
button { width:100%; margin-top:20px; padding:14px; font:inherit; font-weight:700; color:#fff;
         background:var(--acento); border:0; border-radius:10px; cursor:pointer }
@media (prefers-color-scheme: dark) { button { color:#0e1f1a } }
.aviso { background:var(--aviso); border-radius:10px; padding:12px 14px; margin:16px 0; font-size:.95rem }
code { word-break:break-all; font-size:.85rem }
.envio-rev { margin:16px 0 } .envio-rev img, .envio-rev video { max-width:100%; border-radius:8px; margin:6px 0 }
.botones { display:flex; gap:8px } .botones form { flex:1 } .botones button { margin-top:8px }
button.descartar { background:#9b2c2c; color:#fff }
pre { white-space:pre-wrap; word-break:break-word; background:var(--fondo); padding:8px; border-radius:8px; font-size:.9rem }
"""


def pagina(titulo, cuerpo, estado=200):
    return Response(f"""<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>{html.escape(titulo)}</title>
<style>{ESTILO}</style></head><body><main>{cuerpo}</main></body></html>""", estado)


@app.after_request
def cabeceras(respuesta):
    respuesta.headers["Content-Security-Policy"] = ("default-src 'none'; style-src 'unsafe-inline'; "
                                                    "img-src 'self'; media-src 'self'; form-action 'self'")
    respuesta.headers["Referrer-Policy"] = "no-referrer"
    respuesta.headers["X-Content-Type-Options"] = "nosniff"
    if ONION:  # Tor Browser ofrece abrir la versión .onion
        respuesta.headers["Onion-Location"] = f"http://{ONION}{request.full_path.rstrip('?')}"
    return respuesta


# ---------------------------------------------------------------- para quien envía

def candidatos_en_carrera():
    """Los candidatos de candidatos.yaml que siguen en carrera, por cargo. Se lee en cada visita,
    así que basta con actualizar el repositorio para que la lista cambie."""
    try:
        lista = yaml.safe_load(CANDIDATOS.read_text(encoding="utf-8")).get("candidatos") or []
    except (OSError, AttributeError, yaml.YAMLError):
        return {}
    por_cargo = {}
    for c in lista:
        if c.get("nombre") and c.get("estado") not in ("retirado", "no inscrito"):
            por_cargo.setdefault(c.get("cargo") or "Otro", []).append(c["nombre"])
    return {cargo: sorted(nombres) for cargo, nombres in por_cargo.items()}


@app.get("/")
def inicio():
    opciones = "".join(f'<option value="{k}">{html.escape(v)}</option>' for k, v in TIPOS.items())
    por_cargo = candidatos_en_carrera()
    grupos = "".join(
        f'<optgroup label="{html.escape(cargo)}">'
        + "".join(f'<option value="{html.escape(n)}">{html.escape(n)}</option>' for n in nombres)
        + "</optgroup>" for cargo, nombres in por_cargo.items())
    eleccion_candidato = (f"""<label for="candidato">¿A favor (o en contra) de quién?
    <span class="suave">(opcional)</span></label>
  <select id="candidato" name="candidato"><option value="">No sé / no aplica</option>{grupos}</select>"""
                          if por_cargo else "")
    tor = (f"""<div class="aviso"><strong>¿Necesita el máximo anonimato?</strong> Por ejemplo, si trabaja
en una campaña o en una entidad pública. Abra esta misma página en el
<a href="https://www.torproject.org/es/download/">navegador Tor</a> con esta dirección:<br>
<code>http://{html.escape(ONION)}</code></div>""" if ONION else "")
    return pagina("Buzón del archivo electoral", f"""
<h1>Buzón del archivo electoral</h1>
<p>Envíenos la propaganda electoral que vea: vallas, volantes, videos, cadenas de WhatsApp o enlaces
de redes. La guardamos para que no se pierda cuando la borren.</p>
<p class="suave">No necesita cuenta. No guardamos su dirección IP ni usamos cookies. A las fotos y
videos les quitamos la ubicación y los datos del teléfono antes de guardarlos.</p>
<form class="envio" method="post" action="/enviar" enctype="multipart/form-data">
  <label class="archivo">📷 Elegir fotos o videos
    <input type="file" name="archivos" multiple accept="image/*,video/*,audio/*"></label>
  <label for="tipo">¿Qué es?</label>
  <select id="tipo" name="tipo">{opciones}</select>
  {eleccion_candidato}
  <label for="lugar">Comuna o barrio <span class="suave">(opcional, no ponga direcciones)</span></label>
  <input type="text" id="lugar" name="lugar" maxlength="60" placeholder="Comuna 19">
  <label for="texto">Enlaces o comentarios <span class="suave">(opcional)</span></label>
  <textarea id="texto" name="texto" maxlength="5000"
    placeholder="Pegue aquí enlaces de TikTok, Instagram, Facebook... No escriba su nombre."></textarea>
  <button type="submit">Enviar</button>
</form>
{tor}
<p class="suave">Fotografíe la propaganda, no a las personas. Lo que envíe lo revisa una persona del
equipo antes de guardarlo en el archivo público.</p>""")


@app.post("/enviar")
def enviar():
    archivos = [a for a in request.files.getlist("archivos") if a and a.filename]
    texto = (request.form.get("texto") or "").strip()[:5000]
    if not archivos and not re.search(r"https?://", texto):
        return pagina("Falta algo", """<h1>Falta algo</h1><p>Elija al menos una foto o video, o pegue
un enlace.</p><p><a href="/">Volver</a></p>""", 400)
    malos = [a.filename for a in archivos if Path(a.filename).suffix.lower() not in EXTENSIONES]
    if malos:
        return pagina("Archivo no aceptado", """<h1>Archivo no aceptado</h1><p>Solo se reciben fotos,
videos y audios. Si es un PDF, tómele una foto o una captura.</p><p><a href="/">Volver</a></p>""", 400)

    tipo = request.form.get("tipo") if request.form.get("tipo") in TIPOS else "otro"
    lugar = re.sub(r"\s+", " ", request.form.get("lugar") or "").strip()[:60]
    candidato = request.form.get("candidato") or ""
    if candidato not in {n for nombres in candidatos_en_carrera().values() for n in nombres}:
        candidato = ""
    fecha = dt.date.today().isoformat()
    id_envio = secrets.token_hex(8)
    carpeta = PENDIENTE / fecha / id_envio
    carpeta.mkdir(parents=True)
    # El nombre original del archivo puede tener datos personales: solo se conserva la extensión.
    for i, a in enumerate(archivos, 1):
        a.save(carpeta / f"archivo-{i}{Path(a.filename).suffix.lower()}")
    (PENDIENTE / fecha / f"{id_envio}-message.txt").write_text(
        f"tipo: {tipo}\nlugar: {lugar}\ncandidato: {candidato}\n---\n{texto}\n", encoding="utf-8")
    if not archivos:
        carpeta.rmdir()
    return pagina("¡Gracias!", """<h1>¡Gracias!</h1><p>Lo recibimos. Una persona del equipo lo revisa y
lo guarda en el archivo.</p><p><a href="/">Enviar algo más</a></p>""")


# ---------------------------------------------------------------- para el equipo

def autorizado():
    datos = request.authorization
    return bool(CLAVE) and datos is not None and hmac.compare_digest(datos.password or "", CLAVE)


def pedir_clave():
    return Response("Hace falta la clave del equipo.", 401,
                    {"WWW-Authenticate": 'Basic realm="Equipo del buzón", charset="UTF-8"'})


def ficha_envio(fecha, id_envio):
    """Protege los botones contra envíos desde otras páginas."""
    return hmac.new(CLAVE.encode(), f"{fecha}/{id_envio}".encode(), hashlib.sha256).hexdigest()


def ruta_segura(*partes):
    for parte in partes:
        if not re.fullmatch(r"[\w.-]+", parte) or parte.startswith("."):
            abort(404)
    return PENDIENTE.joinpath(*partes)


def envios_pendientes():
    for mensaje in sorted(PENDIENTE.glob("*/*-message.txt")):
        fecha, id_envio = mensaje.parent.name, mensaje.name.removesuffix("-message.txt")
        carpeta = mensaje.parent / id_envio
        archivos = sorted(p.name for p in carpeta.iterdir()) if carpeta.is_dir() else []
        yield fecha, id_envio, mensaje.read_text(encoding="utf-8", errors="replace"), archivos


@app.get("/revisar")
def revisar():
    if not autorizado():
        return pedir_clave()
    bloques = []
    for fecha, id_envio, texto, archivos in envios_pendientes():
        medios = []
        for nombre in archivos:
            url = f"/revisar/archivo/{fecha}/{id_envio}/{nombre}"
            tipo = (mimetypes.guess_type(nombre)[0] or "").split("/")[0]
            if tipo == "image":
                medios.append(f'<a href="{url}"><img src="{url}" alt="{html.escape(nombre)}"></a>')
            elif tipo in ("video", "audio"):
                medios.append(f'<{tipo} controls preload="metadata" src="{url}"></{tipo}>')
            else:
                medios.append(f'<a href="{url}">{html.escape(nombre)}</a>')
        token = ficha_envio(fecha, id_envio)
        botones = "".join(f"""<form method="post" action="/revisar/{fecha}/{id_envio}">
<input type="hidden" name="ficha" value="{token}"><input type="hidden" name="accion" value="{accion}">
<button class="{accion}">{etiqueta}</button></form>""" for accion, etiqueta in
                          (("aprobar", "Archivar"), ("descartar", "Descartar")))
        bloques.append(f"""<div class="tarjeta envio-rev"><p class="suave">{fecha}</p>
{''.join(medios)}<pre>{html.escape(texto)}</pre><div class="botones">{botones}</div></div>""")
    cuerpo = "".join(bloques) or "<p>No hay nada por revisar.</p>"
    return pagina("Revisar el buzón", f"""<h1>Revisar el buzón</h1>
<p class="suave">Archive lo que sea propaganda electoral. Descarte lo que no lo sea, lo que muestre
caras de personas o placas de carros, y cualquier contenido ilegal o violento. Al archivar solo se usan
los archivos, los enlaces, el tipo y el lugar; el resto del texto se borra.</p>{cuerpo}""")


@app.get("/revisar/archivo/<fecha>/<id_envio>/<nombre>")
def archivo(fecha, id_envio, nombre):
    if not autorizado():
        return pedir_clave()
    ruta = ruta_segura(fecha, id_envio, nombre)
    if not ruta.is_file():
        abort(404)
    return send_file(ruta)


@app.post("/revisar/<fecha>/<id_envio>")
def decidir(fecha, id_envio):
    if not autorizado():
        return pedir_clave()
    if not hmac.compare_digest(request.form.get("ficha", ""), ficha_envio(fecha, id_envio)):
        abort(403)
    mensaje = ruta_segura(fecha, f"{id_envio}-message.txt")
    carpeta = ruta_segura(fecha, id_envio)
    if not mensaje.is_file():
        abort(404)
    if request.form.get("accion") == "aprobar":
        destino = APROBADO / fecha
        destino.mkdir(parents=True, exist_ok=True)
        if carpeta.is_dir():
            shutil.move(carpeta, destino / id_envio)
        shutil.move(mensaje, destino / mensaje.name)
    else:
        shutil.rmtree(carpeta, ignore_errors=True)
        mensaje.unlink()
    return redirect("/revisar", 303)


@app.get("/salud")
def salud():
    return "ok"


if __name__ == "__main__":
    if not CLAVE:
        raise SystemExit("Falta la variable BUZON_CLAVE (la clave del equipo para /revisar).")
    PENDIENTE.mkdir(parents=True, exist_ok=True)
    APROBADO.mkdir(parents=True, exist_ok=True)
    from waitress import serve
    # waitress no guarda registro de visitas, así que no queda ninguna IP en disco.
    serve(app, host="127.0.0.1", port=int(os.environ.get("BUZON_PUERTO", "8080")), threads=4)
