# Para continuar este trabajo (guía para otra IA o persona)

Este archivo resume todo lo necesario para seguir desarrollando el proyecto sin haber visto la conversación en la que se construyó. Léalo completo antes de cambiar nada.

## 1. Qué es y para quién

**Objetivo:** un archivo verificable de propaganda electoral para investigación académica. Mucho contenido electoral se borra después de las elecciones; este sistema lo guarda de forma que cualquiera pueda comprobar después **que existió, cuándo, y quién lo publicó o pagó** (campaña, tercero contratado, influenciador, institución pública, etc.).

- Empieza en **Santiago de Cali (Colombia)**, para las elecciones territoriales del **31 de octubre de 2027**. Hoy (octubre de 2026) todavía no hay candidatos oficiales; la inscripción cierra hacia julio de 2027.
- Es una **plantilla**: otros municipios la copian ("Use this template" en GitHub), cambian `config.yaml`, `candidatos.yaml` y `cuentas.yaml`, y tienen su propio nodo.
- Repositorio: `https://github.com/telemetronpro/archivo-electoral` (público, licencia MIT, rama `main`).

**Quien lo dirige** es investigador/a en Colombia. Escribe en español informal. Quiere tres cosas, en este orden:

1. **Confiabilidad de la evidencia** (huellas, sellos de tiempo, testigos independientes).
2. **Privacidad estricta:** *no guardar ningún dato personal de ciudadanos*. Lo dijo explícitamente: "no quiero más info que esa".
3. **Que sea súper fácil de usar**, incluso para alguien que no sabe qué es Tor ni GitHub.

Todo lo visible para usuarios (documentación, mensajes, formularios, páginas) va **en español claro**, tratando al lector de **usted**. Los nombres de funciones y variables también van en español.

## 2. Reglas que no se pueden romper

- **Regla de privacidad.** Solo se guarda enlace, cuenta y metadatos de una pieza cuando la cuenta está en `cuentas.yaml`, que lista **actores públicos**: candidatos, campañas, partidos, agencias o personas contratadas, **personalidades públicas e influenciadores**, **instituciones públicas** (Presidencia, Gobernación, Alcaldía, Fuerza Pública, organismos de control o cualquier otro órgano, y sus funcionarios) y medios. De cualquier otra fuente se guarda **solo la pieza, sin metadatos, sin enlace y sin cuenta**. **Nunca** se guarda quién envió algo. El comando `archivar.py revisar` (y el flujo `Revisar` en GitHub) rechaza fichas que rompan esta regla.
- **Lo del buzón no se publica sin revisión humana**, para que nadie use el archivo para difundir contenido ilegal o violento.
- **La clasificación de la fuente nunca se borra:** los cambios se agregan al `historial` de la ficha con su evidencia.
- **Neutralidad:** mismo criterio para todos los candidatos.

## 3. Cómo funciona

```
Formularios de GitHub (issues) ──┐
Buzón web (buzon/web.py) ── revisión del equipo ──┤
Seguimiento diario de cuentas.yaml ──┤
                                     ▼
                     herramientas/archivar.py
   descarga (yt-dlp / gallery-dl / Browsertrix WACZ) → quita metadatos si la fuente no es pública
   → huellas SHA-256 (huellas.sha256) → sello OpenTimestamps (.ots)
   → testigo en el Wayback Machine (solo fuentes públicas) → ficha.yaml
   → archivos pesados a una versión (release) mensual de GitHub y, si hay claves, al Internet Archive
```

Cada pieza vive en `piezas/AAAA/MM/<código>/` con `ficha.yaml`, `huellas.sha256` y `huellas.sha256.ots`. Los archivos pesados **no van en git**: van a las releases `piezas-AAAA-MM`. Códigos: `cali-AAAA-000001` (GitHub Actions) y `cali-AAAA-b000001` (buzón, serie aparte para no chocar).

Categorías de fuente (`CATEGORIAS` en `archivar.py`): `campaña-oficial`, `tercero-contratado`, `tercero-sin-declarar`, `personalidad-publica`, `institucion`, `otro-actor-publico`, `desconocida`, `no-atribuida` (esta última = por privacidad no se guardó la fuente).

## 4. Mapa de archivos

| Archivo | Qué hace |
|---|---|
| `herramientas/archivar.py` | Todo el núcleo. Subcomandos: `enlace`, `archivo`, `desde-issue`, `reclasificar`, `seguir`, `agregar-cuenta`, `candidato`, `buzon`, `sellos`, `verificar`, `revisar`. Ver `python herramientas/archivar.py -h` |
| `buzon/web.py` | Buzón web (Flask + waitress): formulario en español sin cookies, sin JS, sin cargar nada externo, sin guardar IP. `/revisar` con clave (HTTP Basic, variable `BUZON_CLAVE`) para que el equipo apruebe o descarte. Muestra la lista de `candidatos.yaml` |
| `buzon/instalar.sh` | Instala el buzón en Debian/Ubuntu/Raspberry Pi OS: servicio .onion de Tor + enlace normal con Tailscale Funnel + temporizador que archiva lo aprobado cada 15 min |
| `buzon/procesar.sh`, `buzon/direccion.sh` | Procesar lo aprobado y subirlo a GitHub; mostrar direcciones, clave y códigos QR |
| `.github/ISSUE_TEMPLATE/` | 5 formularios: enlace, foto o archivo, reclasificar (equipo), agregar cuenta (equipo), candidato (equipo) |
| `.github/workflows/` | `archivar` (al abrir un issue o a mano, con modo prueba), `seguir` (diario), `sellos` (diario), `revisar` (en cada push: reglas + pruebas) |
| `config.yaml`, `cuentas.yaml`, `candidatos.yaml` | Configuración del municipio, actores públicos y candidatos (con estado aspirante/inscrito/retirado/no inscrito e historial) |
| `docs/metodo.md`, `docs/buzon.md`, `docs/nuevo-municipio.md` | Método y privacidad, buzón, copiar para otro municipio |
| `pruebas/` | 38 pruebas con `unittest`, sin red (todo lo de red se simula) |

## 5. Cómo trabajar

```
python -m venv venv && . venv/bin/activate
pip install -r requirements.txt          # necesita también ffmpeg instalado en el sistema
python -m unittest discover -s pruebas   # deben pasar todas
python herramientas/archivar.py revisar  # las fichas cumplen las reglas
```

Costumbres del código: comentarios y mensajes en español, cortos; funciones pequeñas; nada de dependencias nuevas sin necesidad; cada cambio con su prueba. Los errores que ve el usuario usan `ErrorArchivo` (permanente) o `ErrorTemporal` (se reintenta).

**Sin acceso a GitHub:** la persona sube los cambios ella misma (en la web de GitHub, "Add file → Upload files", o con git desde su computadora). Entréguele archivos completos o un zip, y dígale exactamente qué archivos reemplazar. Ojo: la carpeta `.github` es oculta en Mac y Windows.

## 6. Estado al 18 de octubre de 2026

**Probado y funcionando:**
- Las 38 pruebas pasan, localmente y en GitHub Actions (flujo `Revisar` en verde).
- En GitHub Actions, la captura completa (WACZ) de la Biblioteca de Anuncios de Meta y el sello de OpenTimestamps funcionan.
- El buzón web funciona en local (envío, revisión con clave, aprobación, paso al archivo); se vio en tamaño de celular, claro y oscuro.

**Probado y fallando:**
- **YouTube bloquea las descargas desde GitHub Actions** ("Sign in to confirm you're not a bot"). Lo más probable es que TikTok, Instagram y Facebook también; no se ha probado.
- **El Wayback Machine no acepta pedidos anónimos desde GitHub.** Hace falta una cuenta gratuita del Internet Archive y guardar sus claves como secretos `IA_ACCESS_KEY` e `IA_SECRET_KEY` (en GitHub: Settings → Secrets and variables → Actions).

**Sin probar** (necesitan una computadora real): Tor, Tailscale Funnel y `buzon/instalar.sh` completo; la subida de archivos a las releases; los formularios de issues con adjuntos reales.

## 7. Decisiones pendientes de la persona

1. **Mover las descargas a la computadora del buzón** (conexión de casa, que las plataformas casi no bloquean) y dejar GitHub solo para guardar y sellar. Recomendado. Implica: que esa computadora corra también `seguir` y procese los enlaces de los formularios (por ejemplo, leyendo los issues abiertos con `gh`), y que el flujo `archivar` de GitHub deje de descargar.
2. **Publicar el buzón con dominio propio detrás de Cloudflare** en vez de Tailscale Funnel: Cloudflare Tunnel (sin abrir puertos, oculta la IP de la casa, protege de ataques de saturación, gratis), dominio tipo `buzonelectoral.org` (Cloudflare Registrar con WHOIS oculto, o Njalla si no quiere que ni el registrador tenga su nombre), `/revisar` protegido con Cloudflare Access, sin Turnstile (molesta a Tor), y la dirección .onion sigue directa por Tor. Costo estimado: 10–15 USD al año.
3. **Límites contra el abuso en el buzón** (vayan o no con Cloudflare): tope de espacio de lo pendiente (por ejemplo 5 GB) y tope de envíos por minuto **sin guardar IP**; regla de límite de velocidad de Cloudflare para `/enviar`.

## 8. Otras ideas que quedaron anotadas

- Detectar la misma pieza publicada en muchas cuentas (huellas perceptuales de imagen y video) como indicio de "tercero sin declarar".
- Depósito anual en Zenodo (DOI citable) y cruce con los informes de gastos de campaña de **Cuentas Claras** (CNE) cuando se publiquen.
- Firma de los WACZ (especificación de firma WACZ, servidor `authsign`).
- Que los nodos de distintos municipios se copien las huellas entre sí (forks) para servirse de testigos.
