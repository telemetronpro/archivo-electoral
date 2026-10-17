import base64
import importlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "buzon"))
sys.path.insert(0, str(RAIZ / "herramientas"))
sys.path.insert(0, str(RAIZ / "pruebas"))
import archivar  # noqa: E402
from test_archivar import RepositorioTemporal  # noqa: E402

CLAVE = "clave-de-prueba"


class BuzonWeb(RepositorioTemporal):
    def setUp(self):
        super().setUp()
        self.datos = self.raiz / "recibido"
        entorno = mock.patch.dict(os.environ, {"BUZON_DATOS": str(self.datos), "BUZON_CLAVE": CLAVE,
                                               "BUZON_ONION": "abc.onion"})
        entorno.start()
        self.addCleanup(entorno.stop)
        import web
        self.web = importlib.reload(web)
        self.web.CANDIDATOS = archivar.RAIZ / "candidatos.yaml"
        archivar.agregar_candidato("Ana María Gómez", "Alcaldía", "aspirante")
        archivar.agregar_candidato("Pedro Ruiz", "Concejo", "inscrito")
        archivar.agregar_candidato("Luis Retirado", "Alcaldía", "retirado")
        self.web.PENDIENTE.mkdir(parents=True)
        self.cliente = self.web.app.test_client()
        self.equipo = {"Authorization": "Basic " + base64.b64encode(f"equipo:{CLAVE}".encode()).decode()}

    def enviar(self, **datos):
        return self.cliente.post("/enviar", data=datos, content_type="multipart/form-data")

    def foto(self):
        return (io.BytesIO(self.foto_con_gps().read_bytes()), "IMG_20270812_Juan_Perez.jpg")

    def test_portada_sencilla_y_sin_nada_de_afuera(self):
        r = self.cliente.get("/")
        self.assertEqual(r.status_code, 200)
        texto = r.get_data(as_text=True)
        self.assertIn('type="file"', texto)
        self.assertIn("abc.onion", texto)
        self.assertNotIn("<script", texto)
        self.assertIn("default-src 'none'", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["Onion-Location"], "http://abc.onion/")
        self.assertNotIn("Set-Cookie", r.headers)

    def test_lista_de_candidatos_en_carrera(self):
        texto = self.cliente.get("/").get_data(as_text=True)
        self.assertIn('<optgroup label="Alcaldía"><option value="Ana María Gómez">', texto)
        self.assertIn("Pedro Ruiz", texto)
        self.assertNotIn("Luis Retirado", texto)

    def test_candidato_inventado_no_se_guarda(self):
        self.enviar(archivos=self.foto(), tipo="valla", candidato="Mi vecino Juan")
        mensaje = next(self.web.PENDIENTE.glob("*/*-message.txt")).read_text(encoding="utf-8")
        self.assertIn("candidato: \n", mensaje)

    def test_envio_guarda_sin_nombre_de_archivo(self):
        r = self.enviar(archivos=self.foto(), tipo="valla", lugar="Comuna 19",
                        texto="Soy Juan https://www.tiktok.com/@a/video/1")
        self.assertEqual(r.status_code, 200)
        guardados = [p.name for p in self.web.PENDIENTE.rglob("*") if p.is_file()]
        self.assertIn("archivo-1.jpg", guardados)
        self.assertFalse(any("Juan" in n for n in guardados))
        mensaje = next(self.web.PENDIENTE.glob("*/*-message.txt")).read_text(encoding="utf-8")
        self.assertTrue(mensaje.startswith("tipo: valla\nlugar: Comuna 19\ncandidato: \n"))

    def test_rechaza_vacio_y_archivos_raros(self):
        self.assertEqual(self.enviar(texto="hola").status_code, 400)
        self.assertEqual(self.enviar(archivos=(io.BytesIO(b"x"), "virus.exe")).status_code, 400)
        self.assertEqual(list(self.web.PENDIENTE.rglob("*")), [])

    def test_solo_enlace(self):
        self.assertEqual(self.enviar(texto="https://x.com/a/status/1").status_code, 200)
        self.assertEqual(len(list(self.web.PENDIENTE.glob("*/*-message.txt"))), 1)
        self.assertEqual([p for p in self.web.PENDIENTE.glob("*/*") if p.is_dir()], [])

    def test_revisar_pide_clave(self):
        self.assertEqual(self.cliente.get("/revisar").status_code, 401)
        malo = {"Authorization": "Basic " + base64.b64encode(b"equipo:otra").decode()}
        self.assertEqual(self.cliente.get("/revisar", headers=malo).status_code, 401)

    def test_aprobar_y_archivar(self):
        self.enviar(archivos=self.foto(), tipo="volante", lugar="San Fernando", candidato="Pedro Ruiz",
                    texto="Soy Juan, 300 123 4567")
        pagina = self.cliente.get("/revisar", headers=self.equipo).get_data(as_text=True)
        self.assertIn("archivo-1.jpg", pagina)
        mensaje = next(self.web.PENDIENTE.glob("*/*-message.txt"))
        fecha, id_envio = mensaje.parent.name, mensaje.name.removesuffix("-message.txt")
        foto = self.cliente.get(f"/revisar/archivo/{fecha}/{id_envio}/archivo-1.jpg", headers=self.equipo)
        self.assertEqual(foto.status_code, 200)

        # Sin la ficha del formulario (por ejemplo, desde otra página) no se puede decidir.
        r = self.cliente.post(f"/revisar/{fecha}/{id_envio}", headers=self.equipo,
                              data={"accion": "aprobar", "ficha": "x"})
        self.assertEqual(r.status_code, 403)
        r = self.cliente.post(f"/revisar/{fecha}/{id_envio}", headers=self.equipo,
                              data={"accion": "aprobar", "ficha": self.web.ficha_envio(fecha, id_envio)})
        self.assertEqual(r.status_code, 303)
        self.assertEqual(list(self.web.PENDIENTE.glob("*/*")), [])

        informe = archivar.procesar_buzon(self.web.APROBADO)
        self.assertEqual(len(informe), 1, informe)
        ficha = next(archivar.PIEZAS.glob("*/*/*/ficha.yaml")).read_text(encoding="utf-8")
        self.assertIn("tipo: volante", ficha)
        self.assertIn("lugar: San Fernando", ficha)
        self.assertIn("- Pedro Ruiz", ficha)
        self.assertNotIn("Juan", ficha)
        self.assertNotIn("4567", ficha)

    def test_descartar_borra(self):
        self.enviar(archivos=self.foto(), tipo="otro")
        mensaje = next(self.web.PENDIENTE.glob("*/*-message.txt"))
        fecha, id_envio = mensaje.parent.name, mensaje.name.removesuffix("-message.txt")
        self.cliente.post(f"/revisar/{fecha}/{id_envio}", headers=self.equipo,
                          data={"accion": "descartar", "ficha": self.web.ficha_envio(fecha, id_envio)})
        self.assertEqual([p for p in self.web.PENDIENTE.rglob("*") if p.is_file()], [])
        self.assertFalse(self.web.APROBADO.exists() and any(self.web.APROBADO.rglob("*")))

    def test_no_deja_salir_de_la_carpeta(self):
        for ruta in ("/revisar/archivo/..%2F..%2Fcuentas.yaml/x/y", "/revisar/archivo/a/.ssh/x"):
            self.assertEqual(self.cliente.get(ruta, headers=self.equipo).status_code, 404, ruta)


if __name__ == "__main__":
    unittest.main()
