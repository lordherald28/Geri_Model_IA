# Geri 2.0

Proyecto de investigación para construir un modelo de lenguaje en español con adquisición controlada de datos y preparación reproducible sin conexión. El pipeline prepara un corpus ELTeC auditado por documento y ajusta un tokenizador BPE nuevo; no contiene pesos ni tokenizador heredados.

## Estado

Fase de preparación de datos — corpus ampliado, validación técnica/offline y tokenizador medido. Las revisiones humanas de licencias/calidad por fuente siguen pendientes; no se inicia entrenamiento del modelo en esta fase.

## Mapa

- `docs/`: arquitectura, datos, metodología, benchmarks y hoja de ruta.
- `src/geri/data/`: adquisición limitada, auditoría, preparación y validación del corpus.
- `src/geri/tokenization/`: futura especificación y entrenamiento de tokenizador desde cero.
- `src/geri/model/`: futura implementación del modelo desde inicialización aleatoria.
- `src/geri/training/`: futuro entrenamiento offline, checkpoints y reanudación.
- `src/geri/evaluation/`: evaluación reproducible y conjuntos separados.
- `src/geri/inference/`: inferencia local.
- `configs/`: configuración explícita y versionada.
- `benchmarks/`: protocolos y resultados de mediciones locales.
- `data/`: datos locales ignorados por Git; solo manifiestos y documentación sin contenido de corpus se versionan.

## Principios

Geri (proyecto anterior) es referencia de solo lectura. No se reutilizan sus pesos, tokenizadores ni checkpoints. El flujo de entrenamiento no depende de red ni de servicios externos. El corpus candidato ampliado y el tokenizador actual están medidos; la revisión humana y las decisiones de arquitectura/entrenamiento siguen pendientes.

Consultar [pipeline y resultados medidos](docs/data-pipeline.md), [arquitectura y decisiones](docs/architecture.md), [gobierno de datos](docs/data-governance.md), [metodología](docs/methodology.md), [benchmarks](docs/benchmarks.md) y [hoja de ruta](docs/roadmap.md).
