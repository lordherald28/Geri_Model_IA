# Hoja de ruta

## Fase 1 — inicialización y diseño

Establecer repositorio, límites de solo lectura, arquitectura, gobierno de datos, metodología, protocolo de dimensionamiento y decisiones pendientes. Cierre: documentación revisable y Git inicializado; sin descargas ni entrenamiento.

## Fase 2 — auditoría de corpus (pipeline técnico y ampliación inicial completados; revisión humana pendiente)

Se implementó el pipeline, se auditaron las fuentes de Geri v1 y se preparó una selección ELTeC, BOE y CORDIS; véase [resultados](data-pipeline.md). La revisión humana de derechos/transcripciones, traducción automática, factualidad y PII sigue pendiente. Completarla antes de ampliar el corpus o distribuir modelos.

## Fase 3 — perfilado y especificación

Acordar presupuesto computacional, benchmark de preparación/tokenización/modelo pequeño desechable y criterios de viabilidad. Elegir contratos de datos, tokenizador y estrategia experimental sin comprometer entrenamiento prolongado.

## Fase 4 — pipeline reproducible (adquisición, preparación, tokenización y verificación offline completadas)

El pipeline actual cumple la preparación y verificación técnica; revisión humana y aprobación del corpus permanecen pendientes antes de cualquier entrenamiento. Repetir hashes y offline-check al cambiar corpus o fuentes.

## Fase 5 — experimentos controlados

Comparar configuraciones sustentadas por benchmarks; registrar calidad/coste; detener cuando se alcance límite aprobado o no haya mejora. Solo después diseñar entrenamiento amplio.

## Fase 6 — conversación, continuidad e inferencia

Añadir fases separadas con datos aprobados, controles de regresión y seguridad, checkpoints recuperables e inferencia local. Criterios de salida por acordar antes de cada fase.

## Criterios de aceptación de fase 1

- Git local inicializado en Geriv2 con `.gitignore` que excluye entornos, secretos, datasets generados, pesos, checkpoints y salidas.
- Arquitectura modular y responsabilidades documentadas.
- Evidencia de auditoría inicial de corpus, con límites y asuntos legales/calidad sin resolver expresados claramente.
- Pipeline online/offline, tokenización, preentrenamiento, conversación, continuidad, evaluación, checkpoints e inferencia descritos.
- Protocolo que mida CPU, RAM, disco, tiempo y coste antes de dimensionar; sin hiperparámetros arbitrarios.
- Sin cambios a Geri; sin pesos/tokenizadores reutilizados; sin descarga ni entrenamiento.
- Decisiones pendientes listadas y sin dependencias o servicios externos innecesarios.

## Decisiones pendientes

1. Casos de uso y variedades de español prioritarias.
2. Fuentes autorizadas y política sobre datos conversacionales.
3. Evidencia de licencia y tratamiento de muestras docentes.
4. Presupuesto de tiempo, energía y almacenamiento disponible.
5. Definición de calidad mínima y rúbrica humana.
6. Requisitos de distribución, atribución y retención de checkpoints.
