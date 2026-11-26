# Auditoría y gobierno de datos

## Hallazgos de referencia

La lectura del manifiesto de solo lectura `../Geri/data/raw_sources/manifest.json` identifica Tatoeba `sentences_CC0` (34 registros, CC0 1.0), ELTeC-spa (111.842 ejemplos; textos indicados como dominio público y metadatos TEI CC BY 4.0) y Wikimedia en español (340 filas; CC BY-SA 4.0 con atribución, enlace a licencia e indicación de transformaciones por página). El corpus educativo procesado mezcla estas fuentes con ejemplos `teacher_reviewed_v1`; para esos ejemplos no se encontró procedencia/licencia individual suficiente en el manifiesto revisado. La inspección fue documental y agregada; no validó cada texto ni cada aviso legal en el sitio fuente.

La selección vigente añade cuatro textos consolidados BOE y tres artículos editoriales CORDIS a los 22 documentos ELTeC fijados por ruta/hash. Las decisiones, hashes, métricas y límites están en [pipeline y resultados](data-pipeline.md). Procedencia/licencia no demuestran calidad o veracidad. El corpus sigue dominado por literatura histórica y no es representativo del español contemporáneo.

No se copiaron los archivos preparados de Geri v1, pesos ni tokenizadores. Se usó el manifiesto v1 como inventario y se volvió a adquirir una selección desde la release primaria aprobada técnicamente. El registro `progress_v3_disk_full.json` en Geri incluye la etiqueta de fallo `disk_full`; es un antecedente operativo, no una medición del espacio disponible actual.

## Contrato mínimo de fuente

Antes de admitir cualquier fuente registrar: identificador y URL; fecha y método de adquisición; snapshot/revisión; titular/fuente; licencia exacta y obligaciones; transformaciones; idioma/dominio; conteos y hashes; PII/contaminación evaluadas; reglas de exclusión; split por documento/obra antes de fragmentar; persona/revisión y decisión de aprobación. Fuentes sin licencia clara se ponen en cuarentena.

## Auditorías obligatorias

1. Licencia y atribución compatible con distribución y uso previsto.
2. Veracidad: muestreo humano y contraste con fuentes identificables; registrar incertidumbre y fecha, no asignar una etiqueta automática de verdad.
3. Calidad: idioma, codificación, HTML/TEI, longitud, boilerplate, duplicados exactos y aproximados, texto corrupto y datos sensibles.
4. Fugas: separar por obra/fuente y detectar coincidencias entre train, validación, test y benchmarks.
5. Reproducibilidad: congelar versión, hashes, scripts y parámetros de transformación. No versionar los textos de origen por defecto.

## Flujo online de preparación

La adquisición online es una tarea explícita de preparación, no parte del proceso de entrenamiento: descargar únicamente fuentes fijadas, limitar tamaño, guardar snapshot/licencia, validar hashes y ejecutar transformaciones deterministas. Generar manifiesto y reporte de calidad. Revisar artefactos antes de transferirlos a un medio local de solo lectura. Tras la transferencia, desactivar red y verificar hashes antes de tokenizar/entrenar. Las credenciales nunca se guardan en manifiestos.

## Pendiente

Pendiente: revisión humana por obra de derechos/transcripción y nombres históricos de ELTeC; estado legal e interpretación de cada consolidado BOE; muestreo de factualidad, calidad de traducción automática y nombres de coordinadores públicos de CORDIS. La detección de correos/teléfonos/DNI-NIE no es un detector completo de PII. Ejemplos docentes de procedencia insuficiente, Tatoeba, Wikimedia, NOS_Científico CC BY-SA y CSIC con términos NC-SA/no anonimizado permanecen excluidos. El usuario indicó excluir CC BY-SA. No se ha emitido dictamen legal ni se debe inferir clearance de distribución de un modelo a partir de esta aprobación técnica.

## Revisión documental adicional (25-11-2026)

- ELTeC-spa v0.9.1 declara que todos los textos incluidos son de dominio público y que el marcado textual usa CC BY 4.0; el repo enlaza una release fijada y el DOI. Esto respalda selección/licencia técnica, pero no acredita calidad de cada transcripción ni resuelve titulares de ediciones modernas o atribución de metadatos. Revisar el [README primario ELTeC-spa](https://github.com/COST-ELTeC/ELTeC-spa).
- BOE confirma que su licencia tipo aprobada el 27-06-2024 permite reutilización comercial/no comercial, modificación y combinación en general. Exige atribución, preservación de fecha/metadatos, identificar cambios y marcar cada legislación consolidada como “de carácter meramente informativo”; hay excepciones para documentos sujetos a condiciones especiales, Biblioteca Jurídica Digital y materiales de terceros. El FAQ confirma el carácter informativo y que “Finalizado” indica la última versión consolidada disponible al momento consultado. Revisar [condiciones oficiales de reutilización](https://www.boe.es/informacion/aviso_legal/) y [FAQ de legislación consolidada](https://www.boe.es/datosabiertos/faq/consolidada.php) frente a cada snapshot.
- CORDIS declara CC BY 4.0 para contenido editorial propiedad de la UE salvo avisos específicos; contenido identificable o material de terceros puede requerir derechos adicionales. La política no elimina el trabajo de calidad/factualidad sobre las traducciones al español ni el análisis de nombres y datos de coordinadores. Revisar el [aviso jurídico CORDIS](https://cordis.europa.eu/about/legal/es) y cada página adquirida.

Estas fuentes confirman las condiciones publicadas, pero no autorizan por sí mismas el uso de cada registro ni el entrenamiento/distribución de pesos. En consecuencia, el manifiesto local continúa en `technically_prepared_candidate; human source review pending`, sin `training_authorization`; el loader de Geriv2 lo rechaza. No se cambió ese estado. La disponibilidad de datos conversacionales licenciados tampoco está resuelta: las muestras de Geri v1 con etiqueta `teacher_reviewed_v1` carecen de procedencia/licencia individual suficiente y quedan fuera.
