# Auditoría y gobierno de datos

## Hallazgos de referencia

La lectura del manifiesto de solo lectura `../Geri/data/raw_sources/manifest.json` identifica Tatoeba `sentences_CC0` (34 registros, CC0 1.0), ELTeC-spa (111.842 ejemplos; textos indicados como dominio público y metadatos TEI CC BY 4.0) y Wikimedia en español (340 filas; CC BY-SA 4.0 con atribución, enlace a licencia e indicación de transformaciones por página). El corpus educativo procesado mezcla estas fuentes con ejemplos `teacher_reviewed_v1`; para esos ejemplos no se encontró procedencia/licencia individual suficiente en el manifiesto revisado. La inspección fue documental y agregada; no validó cada texto ni cada aviso legal en el sitio fuente.

Estos datos son un inventario, no una aprobación para reuso. Calidad/veracidad no quedan demostradas por procedencia o licencia. ELTeC contiene literatura histórica, útil para registro lingüístico pero no representativa por sí sola del español contemporáneo. El corpus técnico de Wikimedia es pequeño. La asignación de niveles documenta reglas por longitud/marcadores gramaticales; es una etiqueta heurística, no garantía de dificultad o corrección. El test separado por obra es un control útil, pero se debe probar también duplicación y contaminación entre fuentes/versiones.

No se copió contenido al nuevo proyecto. El registro `progress_v3_disk_full.json` en Geri incluye la etiqueta de fallo `disk_full`; es un antecedente operativo, no una medición del espacio disponible actual.

## Contrato mínimo de fuente

Antes de admitir cualquier fuente registrar: identificador y URL; fecha y método de adquisición; snapshot/revisión; titular/fuente; licencia exacta y obligaciones; transformaciones; idioma/dominio; conteos y hashes; PII/contaminación evaluadas; reglas de exclusión; split por documento/obra antes de fragmentar; persona/revisión y decisión de aprobación. Fuentes sin licencia clara se ponen en cuarentena.

## Auditorías obligatorias

1. Licencia y atribución compatible con distribución y uso previsto.
2. Veracidad: muestreo humano y contraste con fuentes identificables; registrar incertidumbre y fecha, no asignar una etiqueta automática de verdad.
3. Calidad: idioma, codificación, HTML/TEI, longitud, boilerplate, duplicados exactos y aproximados, texto corrupto y datos sensibles.
4. Fugas: separar por obra/fuente y detectar coincidencias entre train, validación, test y benchmarks.
5. Reproducibilidad: congelar versión, hashes, scripts y parámetros de transformación. No versionar los textos de origen por defecto.

## Flujo online de preparación

La adquisición online es una tarea explícita de preparación, no parte del proceso de entrenamiento: descargar únicamente fuentes aprobadas, guardar snapshot/licencia, validar hashes y ejecutar transformaciones deterministas. Generar manifiesto y reporte de calidad. Revisar artefactos antes de transferirlos a un medio local de solo lectura. Tras la transferencia, desactivar red y verificar hashes antes de tokenizar/entrenar. Las credenciales nunca se guardan en manifiestos.

## Pendiente

Auditar el inventario íntegro por cada fila/obra y fuente original; confirmar licencia de ejemplos revisados por docente, derechos de ediciones digitales y condiciones de cualquier diálogo; inspeccionar posibles PII, duplicados, calidad factual y contaminación. No se ha emitido dictamen legal.
