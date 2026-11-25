# Geri 2.0

Proyecto de investigación para construir un modelo de lenguaje en español con preparación de datos conectada y entrenamiento reproducible sin conexión. La fase actual establece arquitectura, metodología y criterios; no contiene pesos ni tokenizador heredados.

## Estado

Fase 1 — inicialización y diseño. No se descargan datos ni se ejecuta entrenamiento en esta fase.

## Mapa

- `docs/`: arquitectura, datos, metodología, benchmarks y hoja de ruta.
- `src/geri/data/`: futura adquisición controlada, auditoría y preparación de corpus.
- `src/geri/tokenization/`: futura especificación y entrenamiento de tokenizador desde cero.
- `src/geri/model/`: futura implementación del modelo desde inicialización aleatoria.
- `src/geri/training/`: futuro entrenamiento offline, checkpoints y reanudación.
- `src/geri/evaluation/`: evaluación reproducible y conjuntos separados.
- `src/geri/inference/`: inferencia local.
- `configs/`: configuración explícita y versionada.
- `benchmarks/`: protocolos y resultados de mediciones locales.
- `data/`: datos locales ignorados por Git; solo manifiestos y documentación sin contenido de corpus se versionan.

## Principios

Geri (proyecto anterior) es referencia de solo lectura. No se reutilizan sus pesos, tokenizadores ni checkpoints. El flujo de entrenamiento no depende de red ni de servicios externos. Las decisiones cuantitativas se posponen hasta medir capacidad y aprobar un corpus utilizable.

Consultar [arquitectura y decisiones](docs/architecture.md), [datos](docs/data-governance.md), [metodología](docs/methodology.md), [benchmarks](docs/benchmarks.md) y [hoja de ruta](docs/roadmap.md).
