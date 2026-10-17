import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "herramientas"))
import archivar  # noqa: E402
import yaml  # noqa: E402
from PIL import Image  # noqa: E402

CUENTAS = [
    {"plataforma": "tiktok", "cuenta": "@ejemplo2027", "nombre": "Campaña Ejemplo",
     "categoria": "campaña-oficial", "respaldo": "https://ejemplo2027.co"},
    {"plataforma": "facebook", "cuenta": "https://www.facebook.com/AgenciaX/", "alias": ["Agencia X SAS"],
     "nombre": "Agencia X", "categoria": "tercero-contratado"},
    {"plataforma": "web", "cuenta": "www.ejemplo2027.co", "nombre": "Campaña Ejemplo",
     "categoria": "campaña-oficial"},
]


class RepositorioTemporal(unittest.TestCase):
    """Cada prueba trabaja en una copia vacía del repositorio, sin red."""

    def setUp(self):
        self.raiz = Path(tempfile.mkdtemp())
        (self.raiz / "config.yaml").write_text(
            "municipio: Prueba\nprefijo: prueba\neleccion: territoriales-2027\n", encoding="utf-8")
        archivar.escribir_yaml(self.raiz / "cuentas.yaml", {"cuentas": CUENTAS})
        for nombre, valor in (("RAIZ", self.raiz), ("PIEZAS", self.raiz / "piezas"),
                              ("SALIDA", self.raiz / "salida")):
            p = mock.patch.object(archivar, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        for nombre, valor in (("sellar", lambda ruta: False),
                              ("guardar_en_wayback", lambda url: "https://web.archive.org/web/1/x"),
                              ("capturar_wacz", lambda url, carpeta: None)):
            p = mock.patch.object(archivar, nombre, valor)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.dict(os.environ, {"GITHUB_REPOSITORY": ""})
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(shutil.rmtree, self.raiz, True)

    def foto_con_gps(self):
        ruta = self.raiz / "IMG_20270812_Juan.jpg"
        exif = Image.Exif()
        exif[0x010F] = "MarcaTelefono"  # Make
        exif[0x8825] = {1: "N", 2: (3.0, 27.0, 0.0)}  # GPSInfo
        Image.new("RGB", (40, 30), "red").save(ruta, exif=exif)
        return ruta


class Formularios(unittest.TestCase):
    def test_lee_formulario(self):
        texto = ("### Enlace\n\nhttps://www.tiktok.com/@a/video/1\n\n"
                 "### Candidato, partido o campaña\n\n_No response_\n\n### Nota\n\nhola\n")
        self.assertEqual(archivar.leer_formulario(texto), {
            "Enlace": "https://www.tiktok.com/@a/video/1",
            "Candidato, partido o campaña": None, "Nota": "hola"})

    def test_encuentra_adjuntos(self):
        texto = ('<img width="300" alt="IMG_1" src="https://github.com/user-attachments/assets/abc-1" />\n'
                 "[video.mp4](https://github.com/user-attachments/assets/def-2)\n"
                 "https://github.com/user-attachments/files/123/volante.pdf")
        self.assertEqual(archivar.enlaces_adjuntos(texto), [
            "https://github.com/user-attachments/assets/abc-1",
            "https://github.com/user-attachments/assets/def-2",
            "https://github.com/user-attachments/files/123/volante.pdf"])


class Cuentas(unittest.TestCase):
    def test_plataformas(self):
        casos = {
            "https://www.tiktok.com/@a/video/1": "tiktok",
            "https://vm.tiktok.com/ZM123/": "tiktok",
            "https://www.facebook.com/ads/library/?id=123": "biblioteca-anuncios-meta",
            "https://m.facebook.com/AgenciaX/posts/1": "facebook",
            "https://youtu.be/xyz": "youtube",
            "https://x.com/a/status/1": "x",
            "https://ejemplo2027.co/propuestas": "web",
        }
        for url, plataforma in casos.items():
            self.assertEqual(archivar.plataforma_de(url), plataforma, url)

    def test_cuenta_por_url(self):
        c = archivar.buscar_cuenta("https://www.tiktok.com/@Ejemplo2027/video/1", "tiktok", {}, CUENTAS)
        self.assertEqual(c["nombre"], "Campaña Ejemplo")

    def test_cuenta_por_metadatos_y_alias(self):
        c = archivar.buscar_cuenta("https://www.facebook.com/watch?v=1", "facebook",
                                   {"uploader": "Agencia X SAS"}, CUENTAS)
        self.assertEqual(c["categoria"], "tercero-contratado")

    def test_cuenta_por_dominio(self):
        c = archivar.buscar_cuenta("https://ejemplo2027.co/propuestas", "web", {}, CUENTAS)
        self.assertEqual(c["nombre"], "Campaña Ejemplo")

    def test_misma_cuenta_en_otra_plataforma_no_cuenta(self):
        self.assertIsNone(archivar.buscar_cuenta("https://www.instagram.com/ejemplo2027/", "instagram",
                                                 {"username": "ejemplo2027"}, CUENTAS))

    def test_ciudadano_no_esta(self):
        self.assertIsNone(archivar.buscar_cuenta("https://www.tiktok.com/@juanita/video/1", "tiktok",
                                                 {"uploader": "Juanita"}, CUENTAS))

    def test_metadatos_sin_datos_de_terceros(self):
        limpio = archivar.limpiar_metadatos({
            "id": "1", "uploader": "Campaña", "timestamp": 1700000000, "view_count": 5,
            "comments": [{"author": "Pedro"}], "tagged_users": ["pedro"], "formats": []})
        self.assertEqual(set(limpio), {"id", "uploader", "timestamp", "view_count"})


class QuitarMetadatos(RepositorioTemporal):
    def test_foto_sin_exif(self):
        limpia = archivar.quitar_metadatos(self.foto_con_gps())
        with Image.open(limpia) as im:
            self.assertEqual(len(im.getexif()), 0)
            self.assertEqual(im.size, (40, 30))

    @unittest.skipUnless(shutil.which("ffmpeg"), "falta ffmpeg")
    def test_video_sin_metadatos(self):
        video = self.raiz / "video.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=32x32:d=1",
                        "-metadata", "title=Video de Juan", "-metadata", "location=+03.45-076.53/",
                        str(video)], check=True)
        limpio = archivar.quitar_metadatos(video)
        sonda = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format_tags",
                                "-of", "default=nw=1", str(limpio)], capture_output=True, text=True)
        self.assertNotIn("Juan", sonda.stdout)
        self.assertNotIn("location", sonda.stdout)

    def test_rechaza_lo_que_no_es_foto_ni_video(self):
        ruta = self.raiz / "nota.txt"
        ruta.write_text("hola")
        with self.assertRaises(archivar.ErrorArchivo):
            archivar.quitar_metadatos(ruta)


class Registro(RepositorioTemporal):
    def test_foto_de_valla(self):
        carpeta, _ = archivar.archivar_archivos([self.foto_con_gps()], "valla", "Comuna 2", "Ejemplo")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ficha["id"], "prueba-%s-000001" % ficha["registrado"][:4])
        self.assertEqual(ficha["lugar"], "Comuna 2")
        self.assertEqual([a["nombre"] for a in ficha["archivos"]], ["pieza.jpg"])
        self.assertFalse(ficha["fuente_registrada"])
        self.assertNotIn("Juan", (carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(archivar.revisar(), [])

    def test_codigos_seguidos(self):
        a, _ = archivar.archivar_archivos([self.foto_con_gps()], "volante")
        b, _ = archivar.archivar_archivos([self.foto_con_gps()], "volante")
        self.assertTrue(b.name.endswith("000002"), b.name)

    def test_serie_del_buzon_aparte(self):
        archivar.archivar_archivos([self.foto_con_gps()], "volante")
        with mock.patch.dict(os.environ, {"ARCHIVO_SERIE": "b"}):
            b, _ = archivar.archivar_archivos([self.foto_con_gps()], "volante")
        c, _ = archivar.archivar_archivos([self.foto_con_gps()], "volante")
        self.assertTrue(b.name.endswith("-b000001"), b.name)
        self.assertTrue(c.name.endswith("-000002"), c.name)

    def test_enlace_de_ciudadano_no_guarda_fuente(self):
        def falsa_descarga(url, carpeta):
            shutil.copyfile(self.foto_con_gps(), carpeta / "pieza.jpg")
            return {"uploader": "Juanita Pérez", "uploader_id": "juanita", "title": "mi video"}
        with mock.patch.object(archivar, "descargar_con_yt_dlp", falsa_descarga):
            carpeta, avisos = archivar.archivar_enlace("https://www.tiktok.com/@juanita/video/9")
        texto = (carpeta / "ficha.yaml").read_text(encoding="utf-8")
        ficha = yaml.safe_load(texto)
        self.assertEqual(ficha["fuente"]["categoria"], "no-atribuida")
        self.assertNotIn("juanita", texto.lower())
        self.assertEqual(ficha["testigos"], [])
        self.assertEqual([a["nombre"] for a in ficha["archivos"]], ["pieza.jpg"])
        self.assertTrue(avisos)
        self.assertEqual(archivar.revisar(), [])

    def test_enlace_de_campaña_guarda_fuente(self):
        def falsa_descarga(url, carpeta):
            (carpeta / "pieza.mp4").write_bytes(b"video")
            return {"uploader_id": "ejemplo2027", "timestamp": 1800000000, "comments": ["x"]}
        with mock.patch.object(archivar, "descargar_con_yt_dlp", falsa_descarga):
            carpeta, _ = archivar.archivar_enlace("https://www.tiktok.com/@ejemplo2027/video/9")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ficha["fuente"]["categoria"], "campaña-oficial")
        self.assertEqual(ficha["fuente"]["confianza"], "alta")
        self.assertEqual(ficha["cuenta"], "@ejemplo2027")
        self.assertEqual(ficha["publicado"], "2027-01-15T08:00:00Z")
        self.assertEqual(ficha["testigos"], ["https://web.archive.org/web/1/x"])
        self.assertEqual([a["nombre"] for a in ficha["archivos"]], ["pieza.mp4", "metadatos.json"])
        meta = (archivar.SALIDA / ficha["id"] / "metadatos.json").read_text(encoding="utf-8")
        self.assertNotIn("comments", meta)

    def test_seguir_solo_guarda_lo_nuevo(self):
        def falsa_lista(comando, **kw):
            return mock.Mock(stdout="https://www.tiktok.com/@ejemplo2027/video/1\n"
                                    "https://www.tiktok.com/@ejemplo2027/video/2\n", returncode=0)

        def falsa_descarga(url, carpeta):
            (carpeta / "pieza.mp4").write_bytes(url.encode())
            return {"uploader": "otro nombre"}  # aunque no coincida, la cuenta ya se conoce
        with mock.patch.object(archivar, "correr", falsa_lista), \
                mock.patch.object(archivar, "descargar_con_yt_dlp", falsa_descarga):
            primera = archivar.seguir()
            segunda = archivar.seguir()
        self.assertEqual(len(primera), 2)
        self.assertEqual(segunda, [])
        fichas = [yaml.safe_load(f.read_text(encoding="utf-8")) for f in archivar.PIEZAS.glob("*/*/*/ficha.yaml")]
        self.assertTrue(all(f["fuente"]["categoria"] == "campaña-oficial" for f in fichas))

    def test_influenciador_guarda_toda_la_fuente(self):
        archivar.agregar_cuenta("instagram", "@influ.cali", "Influenciadora Ejemplo",
                                "personalidad-publica", "https://prensa.co/nota")

        def falsa_descarga(url, carpeta):
            (carpeta / "pieza-1.jpg").write_bytes(b"foto")
            return {"username": "influ.cali", "description": "Vote por Ejemplo", "likes": 9}
        with mock.patch.object(archivar, "descargar_con_yt_dlp", lambda u, c: None), \
                mock.patch.object(archivar, "descargar_con_gallery_dl", falsa_descarga):
            carpeta, _ = archivar.archivar_enlace("https://www.instagram.com/p/ABC/")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ficha["fuente"]["categoria"], "personalidad-publica")
        self.assertEqual(ficha["url"], "https://www.instagram.com/p/ABC/")
        self.assertEqual(ficha["cuenta"], "@influ.cali")
        self.assertIn("metadatos.json", [a["nombre"] for a in ficha["archivos"]])

    def test_agregar_cuenta_conserva_comentarios_y_evita_repetidas(self):
        ruta = archivar.RAIZ / "cuentas.yaml"
        ruta.write_text("# comentario\ncuentas:\n  # - ejemplo\n", encoding="utf-8")
        archivar.agregar_cuenta("tiktok", "@nueva", "Nueva", "campaña-oficial", "https://a.co")
        texto = ruta.read_text(encoding="utf-8")
        self.assertIn("# comentario", texto)
        self.assertEqual(archivar.cuentas()[0]["nombre"], "Nueva")
        with self.assertRaises(archivar.ErrorArchivo):
            archivar.agregar_cuenta("tiktok", "nueva", "Otra", "campaña-oficial", "https://a.co")
        with self.assertRaises(archivar.ErrorArchivo):
            archivar.agregar_cuenta("tiktok", "@x", "X", "ciudadano", "https://a.co")
        with self.assertRaises(archivar.ErrorArchivo):
            archivar.agregar_cuenta("tiktok", "@x", "X", "campaña-oficial", "")

    def test_institucion_de_la_lista_o_escrita(self):
        archivar.agregar_cuenta("x", "@GobValle", "Gobernación del Valle del Cauca", "institucion",
                                "https://www.valledelcauca.gov.co", "Gobernación")
        archivar.agregar_cuenta("facebook", "PoliciaCali", "Policía Metropolitana de Cali",
                                "institucion", "https://policia.gov.co", "Otra",
                                "Policía Metropolitana de Cali")
        dadas = {c["cuenta"]: c["institucion"] for c in archivar.cuentas() if c.get("institucion")}
        self.assertEqual(dadas, {"@GobValle": "Gobernación",
                                 "PoliciaCali": "Policía Metropolitana de Cali"})
        with self.assertRaises(archivar.ErrorArchivo):  # institución sin decir cuál
            archivar.agregar_cuenta("x", "@algo", "Algo", "institucion", "https://a.co")
        with self.assertRaises(archivar.ErrorArchivo):
            archivar.agregar_cuenta("x", "@algo", "Algo", "institucion", "https://a.co", "Inventada")

        def falsa_descarga(url, carpeta):
            (carpeta / "pieza.mp4").write_bytes(b"video")
            return {"uploader_id": "GobValle"}
        with mock.patch.object(archivar, "descargar_con_yt_dlp", falsa_descarga):
            carpeta, _ = archivar.archivar_enlace("https://x.com/GobValle/status/1")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ficha["fuente"]["categoria"], "institucion")
        self.assertEqual(ficha["fuente"]["institucion"], "Gobernación")

    def test_buzon_archiva_y_borra_todo(self):
        buzon = self.raiz / "recibido" / "2027-08-12"
        (buzon / "154827441370").mkdir(parents=True)
        shutil.copyfile(self.foto_con_gps(), buzon / "154827441370" / "IMG_Juan.jpg")
        (buzon / "154827441370-message.txt").write_text(
            "Soy Juan, mi cel 3001234567. Valla en la Comuna 2", encoding="utf-8")
        (buzon / "154900000000-message.txt").write_text(
            "miren esto https://www.tiktok.com/@ejemplo2027/video/5.", encoding="utf-8")

        def falsa_descarga(url, carpeta):
            (carpeta / "pieza.mp4").write_bytes(b"video")
            return {"uploader_id": "ejemplo2027"}
        with mock.patch.object(archivar, "descargar_con_yt_dlp", falsa_descarga):
            informe = archivar.procesar_buzon(self.raiz / "recibido")
        self.assertEqual(len(informe), 2, informe)
        self.assertEqual(list((self.raiz / "recibido").iterdir()), [])
        fichas = [f.read_text(encoding="utf-8") for f in archivar.PIEZAS.glob("*/*/*/ficha.yaml")]
        todo = "".join(fichas)
        self.assertNotIn("Juan", todo)
        self.assertNotIn("3001234567", todo)
        self.assertIn("lugar: Comuna 2", todo)
        self.assertIn("tipo: valla", todo)
        self.assertIn("https://www.tiktok.com/@ejemplo2027/video/5\n", todo)
        self.assertEqual(archivar.revisar(), [])

    def test_buzon_reintenta_si_falla_la_red(self):
        buzon = self.raiz / "recibido" / "2027-08-12"
        buzon.mkdir(parents=True)
        mensaje = buzon / "1-message.txt"
        mensaje.write_text("https://www.tiktok.com/@ejemplo2027/video/5", encoding="utf-8")

        def sin_red(url, carpeta):
            raise archivar.requests.ConnectionError()
        with mock.patch.object(archivar, "descargar_con_yt_dlp", sin_red):
            archivar.procesar_buzon(self.raiz / "recibido")
        self.assertTrue(mensaje.exists())

    def test_reclasificar_conserva_historial(self):
        carpeta, _ = archivar.archivar_archivos([self.foto_con_gps()], "valla")
        archivar.reclasificar(carpeta.name, "tercero-contratado", "media",
                              "- Cuentas Claras: pago a Agencia X\n- Pagado por Agencia X")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        self.assertEqual(ficha["fuente"]["categoria"], "tercero-contratado")
        self.assertEqual(len(ficha["fuente"]["evidencia"]), 2)
        self.assertEqual(len(ficha["historial"]), 2)

    def test_revisar_detecta_fuga(self):
        carpeta, _ = archivar.archivar_archivos([self.foto_con_gps()], "valla")
        ficha = yaml.safe_load((carpeta / "ficha.yaml").read_text(encoding="utf-8"))
        ficha["url"] = "https://www.tiktok.com/@juanita/video/9"
        archivar.escribir_yaml(carpeta / "ficha.yaml", ficha)
        self.assertTrue(any("url" in p for p in archivar.revisar()))

    def test_verificar_detecta_alteracion(self):
        carpeta, _ = archivar.archivar_archivos([self.foto_con_gps()], "valla")
        archivos = archivar.SALIDA / carpeta.name
        self.assertTrue(archivar.verificar(carpeta.name, archivos)[1][0].startswith("✓"))
        (archivos / "pieza.jpg").write_bytes(b"otra cosa")
        bien, informe = archivar.verificar(carpeta.name, archivos)
        self.assertFalse(bien)
        self.assertIn("NO coincide", informe[0])


if __name__ == "__main__":
    unittest.main()
