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

El benchmark sintético en CPU comparó tres candidatos y la configuración de piloto queda en 2.219.136 parámetros: vocabulario 2.048, `d_model=192`, 4 capas/6 cabezas, FFN 768, contexto 256 y batch 4. La selección favorece capacidad relativa/contexto frente a throughput aislado y permanece limitada, sin evidencia de calidad conversacional. AdamW con clipping, evaluación/early stopping y checkpoints se implementan en `src/geri/training/`; véase `docs/benchmarks.md`. Esta configuración no autoriza el corpus.

## Decisiones aplazadas

Siguen pendientes la aprobación humana de ambos corpora, factualidad/cobertura, revisión de derechos para distribución de pesos, evaluación humana del modelo y medición de energía. La configuración de entrenamiento permanece piloto hasta aprobar datos y medir calidad. La inferencia y política de promoción final no están implementadas.
