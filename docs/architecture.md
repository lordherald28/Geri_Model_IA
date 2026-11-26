# Arquitectura propuesta

## Límites

El repositorio Geriv2 es el único destino de modificaciones. `../Geri` es una referencia de solo lectura. No se importan pesos, checkpoints, código de tokenizador entrenado ni artefactos derivados. Se pueden usar hallazgos documentados como evidencia de diseño, sujetos a verificación antes de implementar.

## Componentes

```text
Fuentes aprobadas (online, preparación) ──> manifiestos y snapshots
       └──> validación de licencia/procedencia/calidad
             └──> normalización, deduplicación y partición por fuente
                   └──> dataset preparado, con hash y reporte
                         └── frontera offline ──> tokenizador desde cero
                                              └──> preentrenamiento
                                                    └── ajuste conversacional
                                                          └── evaluación
                                                                └── checkpoints
                                                                      └── inferencia local
```

La frontera offline debe aceptar artefactos inmutables con manifiesto, hashes y licencia; el runtime de entrenamiento no requiere red. Cada etapa produce entradas/salidas versionadas, configuración efectiva y registros reproducibles. La inferencia consume una versión explícita de modelo y tokenizador y no requiere servicios externos.

## Paquetes previstos

`src/geri/data`, `tokenization`, `model`, `training`, `evaluation` e `inference` separan responsabilidades. `configs/` conserva configuración declarativa; `benchmarks/` guarda protocolos y resultados agregados. Los datos, índices, cachés y artefactos grandes quedan fuera de Git; el repositorio conserva contratos, manifiestos sanitizados y documentación.

## Selección experimental vigente

El microbenchmark sintético en CPU seleccionó para el piloto 238.848 parámetros: vocabulario 2.048, `d_model=64`, 2 capas/cabezas, FFN 256, contexto 128 y batch 4. AdamW con clipping, evaluación/early stopping y checkpoints se implementan en `src/geri/training/`; véase `docs/benchmarks.md` para resultados y límites. Esta configuración no prueba capacidad lingüística general ni autoriza el corpus.

## Decisiones aplazadas

Siguen pendientes los datos aprobados de pretraining/SFT, factualidad/cobertura esperada, duración/energía aceptable, derechos aplicables a la distribución de pesos y evaluación humana. La configuración de entrenamiento permanece piloto hasta tener datos aprobados y calidad evaluada. La inferencia y política de promoción final no están implementadas.
