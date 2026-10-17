# Montar el archivo en otro municipio

Toma unos 15 minutos y no hay que programar nada.

1. En la página de este repositorio, pulse **Use this template → Create a new repository**. Póngale un nombre como `archivo-electoral-pasto` y déjelo **público**: un archivo que nadie puede revisar no sirve como prueba.
2. En el repositorio nuevo, edite [`config.yaml`](../config.yaml): el municipio, el prefijo de los códigos (por ejemplo `pasto`) y la elección.
3. Vacíe [`candidatos.yaml`](../candidatos.yaml) y [`cuentas.yaml`](../cuentas.yaml), y agregue los candidatos (o aspirantes) de su municipio y sus cuentas, con los formularios del equipo.
4. En **Settings → Actions → General → Workflow permissions**, elija **Read and write permissions**. Así el sistema puede guardar las piezas.
5. En **Issues → Labels**, cree la etiqueta `archivar`. Con ella el equipo aprueba lo que envían personas de fuera.
6. En **Settings → Collaborators**, agregue a las personas del equipo. Lo que ellas envían se archiva sin esperar aprobación.
7. Pruebe: en **Actions → Archivar → Run workflow**, pegue un enlace y deje marcada la casilla de prueba. Al terminar, el resultado queda en un archivo descargable `prueba` en esa misma página.

## Opcional: buzón

Para recibir piezas de cualquier persona, sin que haga falta una cuenta y sin saber quién las envía, monte el [buzón](buzon.md). Necesita una computadora que quede prendida.

## Opcional: copia en el Internet Archive

Con una cuenta gratuita del [Internet Archive](https://archive.org), cada pieza se sube también allá y las capturas del Wayback Machine son más confiables. Saque las claves en <https://archive.org/account/s3.php> y guárdelas en **Settings → Secrets and variables → Actions** como `IA_ACCESS_KEY` e `IA_SECRET_KEY`.

## Servirse de testigo con otros municipios

Si otro municipio archiva algo, que ustedes también tengan una copia de sus huellas lo protege: si a alguien lo presionan para borrar una pieza, otros ya tenían la prueba de que existía. Basta con que cada equipo haga de vez en cuando un *fork* de los repositorios de los demás, y avisar en el índice común de nodos.
