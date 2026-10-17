# Método

## Qué prueba el archivo y cómo

Un archivo guardado por una sola persona no prueba nada: podría haberlo inventado o editado. La confianza sale de juntar pruebas que no dependen de una sola persona:

| Pregunta | Qué la responde |
|---|---|
| ¿Este archivo es el mismo que se guardó? | Su huella SHA-256, publicada en este repositorio |
| ¿Existía en tal fecha? | El sello de OpenTimestamps sobre esa huella, anclado en Bitcoin |
| ¿Estaba publicado en esa cuenta? | La captura que hace el Wayback Machine del Internet Archive, que es de ellos y no nuestra; y la captura WACZ de páginas y anuncios |
| ¿Quién lo pagó o lo produjo? | La evidencia citada en la ficha: Biblioteca de Anuncios de Meta, gastos de campaña en Cuentas Claras (CNE), etiqueta de "colaboración pagada", etc. |
| ¿Nadie cambió el historial? | El historial de git, las copias del repositorio (forks de otros nodos, Software Heritage) y el depósito anual en Zenodo |

## Privacidad: qué se guarda y qué no

`cuentas.yaml` lista las cuentas de actores públicos: candidatos, campañas, partidos, agencias, medios, entidades, y personalidades públicas e influenciadores. Estos últimos entran porque publican para el público y su alcance es lo que los hace relevantes. Cada cuenta lleva un enlace que respalda que es pública.

| | Cuenta en `cuentas.yaml` | Cualquier otra fuente | Foto o archivo subido |
|---|---|---|---|
| La pieza | Sí, tal como la sirve la plataforma | Sí, sin metadatos | Sí, sin metadatos |
| Enlace y cuenta | Sí | No | — |
| Fecha de publicación y números de vistas y reacciones | Sí | No | — |
| Captura en el Wayback Machine | Sí | No | — |
| Lugar | — | — | Solo comuna o barrio, si se escribe |
| Quién la envió | Nunca | Nunca | Nunca |

No se guarda nada más.

Comentarios, personas etiquetadas y datos de quienes interactúan con la publicación no se guardan nunca. El flujo `Revisar` rechaza cualquier ficha que rompa estas reglas.

Lo que **no** controla el archivo, y conviene saberlo:

- Quien envía algo con un formulario usa su cuenta de GitHub, y el formulario queda en los issues del repositorio. Después de archivar, el sistema borra el contenido del formulario y cierra el issue, pero GitHub conserva el autor del issue y su historial de ediciones. Quien no quiera dejar ningún rastro debe usar el [buzón anónimo](buzon.md), que funciona sobre Tor: ni el equipo puede saber quién envió algo.
- Lo que se ve dentro de la imagen no se puede limpiar automáticamente: si un video de TikTok trae la marca de agua con el usuario, o si en la foto de una valla sale una persona, queda en el archivo. El formulario de fotos le pide a quien envía que lo confirme, y el equipo debe borrar las piezas que no cumplan.
- La propaganda misma puede mostrar personas (testimonios, fotos de eventos). Eso lo publicó la campaña y es parte de la pieza.

## Quién está detrás de una pieza

La clasificación se basa en evidencia citada y siempre lleva un nivel de confianza. Toda pieza empieza en una de dos categorías: **desconocida**, cuando aún no se sabe de quién es, o **no atribuida**, cuando por privacidad no se guardó de dónde vino. De ahí pasa a otra solo con evidencia.

| Categoría | Evidencia que la sostiene |
|---|---|
| **Campaña oficial** | Cuenta del candidato, partido o campaña en `cuentas.yaml`, con un enlace que lo respalde; anuncio con "Pagado por" a nombre de la campaña |
| **Tercero contratado** | "Pagado por" a nombre de una agencia o persona distinta; ese proveedor aparece en los gastos reportados en **Cuentas Claras**; etiqueta de colaboración pagada |
| **Tercero sin declarar** (sospecha) | La misma pieza sale a la vez en muchas cuentas sin relación aparente. Es un indicio, no una prueba: confianza baja hasta que aparezca otra evidencia |
| **Personalidad pública o influenciador** | Su cuenta está en `cuentas.yaml`. Apoya a un candidato y no se sabe si le pagan; si aparece la prueba (colaboración pagada, "Pagado por", Cuentas Claras), pasa a tercero contratado |
| **Otro actor público** | Medios, entidades, organizaciones |

Para separar a la campaña de un tercero contratado, lo que más sirve es Cuentas Claras: los informes de ingresos y gastos dicen a quién se le pagó y por qué. Como se publican después de la elección, cuando el contenido ya desapareció, hay que capturar primero y clasificar después.

Una pieza no atribuida también puede ganar fuente: si la misma imagen aparece después en una cuenta oficial, se reclasifica citando el código de esa otra pieza.

## Límites

- Nada de esto prueba criptográficamente que el servidor de TikTok o Meta envió ese contenido. Lo que da fuerza es que coincidan varios testigos independientes.
- Lo que se borró antes de la primera captura no se recupera; por eso hay que capturar todos los días, sin esperar a que algo se vuelva noticia.
- Instagram y Facebook a veces piden iniciar sesión para descargar. Entonces la pieza queda solo con el testigo del Wayback Machine, si lo logra, y conviene subir el archivo a mano.

## Calendario para 2027

1. **Primer semestre:** probar con las cuentas de los precandidatos a la Alcaldía de Cali; buscar un aliado en otro municipio.
2. **Julio, cierre de inscripciones:** completar `cuentas.yaml` con todos los candidatos y sus campañas.
3. **Agosto a octubre:** captura diaria de esas cuentas y de la Biblioteca de Anuncios, más los aportes del público.
4. **Después del 31 de octubre:** depósito en Zenodo (da un DOI citable) y cruce con Cuentas Claras cuando salgan los informes de gastos.
