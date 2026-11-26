# Geri 2.0

Proyecto de investigación para construir un modelo de lenguaje en español con adquisición controlada de datos y preparación reproducible sin conexión. Incluye pipeline de corpus y un motor experimental local de preentrenamiento desde inicialización aleatoria; no contiene pesos ni tokenizador heredados.

## Estado

Fase de preparación de piloto — motor probado offline, benchmark CPU repetido con contexto 256, candidato SFT OASST1 generado y validado técnicamente (779 ejemplos). Ambos manifiestos siguen sin aprobación humana y bloquean el entrenamiento definitivo. Solo se ejecutaron pruebas/smoke sintéticos; no se inició entrenamiento de producto.

## Mapa

- `docs/`: arquitectura, datos, metodología, benchmarks y hoja de ruta.
- `src/geri/data/`: adquisición limitada, auditoría, preparación y validación del corpus.
- `src/geri/tokenization/`: futura especificación y entrenamiento de tokenizador desde cero.
- `src/geri/model/`: Transformer decoder desde inicialización aleatoria.
- `src/geri/training/`: entrenamiento offline, checkpoints atómicos, recuperación, benchmark y CLI.
- `src/geri/evaluation/`: comparación determinista de regresiones de pérdida.
- `src/geri/inference/`: inferencia local.
- `configs/`: configuración explícita y versionada.
- `benchmarks/`: protocolos y resultados de mediciones locales.
- `data/`: datos locales ignorados por Git; solo manifiestos y documentación sin contenido de corpus se versionan.

PyTorch 2.15.0+cpu y tokenizers 0.23.3 se reutilizaron desde el entorno local compatible de Geri v1, solo para benchmark y pruebas, sin modificar ese proyecto ni usar sus datos/modelos. Para preparar otro entorno: `python -m pip install -e ".[training,dev]"`; en equipos aislados, transferir ruedas compatibles con sus hashes.

Flujo manual, preparación SFT y comando PowerShell: [motor de entrenamiento](docs/training-engine.md). El benchmark de selección está en [benchmarks](docs/benchmarks.md). No ejecutar `scripts\Train-Geri.ps1` hasta que ambos manifests indiquen aprobación humana explícita.

Los datos, artefactos de prueba y salidas de entrenamiento se centralizan fuera del repositorio en `C:\Geriv2-Data\`; el mapa está en [datos y reproducibilidad](docs/data-pipeline.md).

## Principios

Geri (proyecto anterior) es referencia de solo lectura. No se reutilizan sus datos, pesos, tokenizadores ni checkpoints. El flujo de entrenamiento no depende de red ni de servicios externos; la CPU usa la instalación PyTorch existente. El corpus y la licencia siguen pendientes de aprobación humana; la arquitectura es solo una configuración piloto dimensionada por microbenchmark.

Consultar [pipeline y resultados medidos](docs/data-pipeline.md), [arquitectura y decisiones](docs/architecture.md), [gobierno de datos](docs/data-governance.md), [metodología](docs/methodology.md), [benchmarks](docs/benchmarks.md) y [hoja de ruta](docs/roadmap.md).
