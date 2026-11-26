# Dimensionamiento del modelo y benchmarks

## Equipo y medición

Windows; AMD Ryzen 5 7530U, 6 núcleos/12 hilos; 31,35 GiB RAM. PyTorch 2.15.0+cpu, Python 3.12.10, seis hilos intra-op. Durante la medición había 12,98 GB de RAM física disponibles y aproximadamente 208,6 GB libres en C:. No se identificó GPU de entrenamiento. Medición repetible y agregado en [`model-benchmark-20261125.json`](../benchmarks/model-benchmark-20261125.json).

Se compararon tres tamaños en CPU con batch 4, contexto 256, 2 pasos de calentamiento y 30 pasos medidos por repetición, 3 repeticiones cada uno. Entradas de tokens aleatorios: sirve para dimensionar compute/memoria, no calidad ni flujo de lectura del corpus.

| Candidato | Parámetros | Tokens/s promedio (rango) | RSS pico absoluto | Checkpoint |
|---|---:|---:|---:|---:|
| tiny: d=64, 2 capas | 247.040 | 15.943 (15.315–16.279) | 362 MB | 2,99 MB |
| small: d=128, 4 capas | 1.086.208 | 4.566 (4.219–4.939) | 459 MB | 13,09 MB |
| medium: d=192, 4 capas | 2.219.136 | 3.436 (3.385–3.505) | 519 MB | 26,68 MB |

La configuración de ejecución queda en `medium` (d=192, 4 capas, 6 cabezas, FFN 768): tiene 9 veces los parámetros de tiny y 2 veces los de small, a cambio de 4,6 veces menos tokens/s que tiny. Se prefiere esa capacidad adicional y contexto 256 porque la meta es lenguaje/conversación, no throughput aislado; su RSS de benchmark es 519 MB y checkpoint 26,68 MB, razonables frente a 12,98 GB disponibles. El campo `fastest_candidate_by_tokens_per_second` identifica solo velocidad; no selecciona el tamaño final. Es todavía un modelo de investigación muy pequeño y no hay evidencia de calidad hasta entrenar/evaluar con datos aprobados.

Para el corpus candidato actual hay 1.883.060 tokens BPE en train y 563.753 en validation. Con `medium`, batch 4, contexto 256 y límite de 10.000 pasos se procesarían hasta 10,24 M posiciones objetivo (5,44 recorridos equivalentes) en unos 50 min a throughput sintético promedio. Las evaluaciones añaden hasta 3,28 M posiciones forward; SFT del candidato de 779 diálogos añade hasta 1,02 M posiciones de entrenamiento y 1,31 M de evaluación. Planificación combinada: 60–90 min, extrapolada con sobrecarga de evaluación/checkpoint/carga; no se midió una corrida completa ni variación térmica. El early stopping puede reducir duración. Recalcular antes de iniciar.

## Configuración medida

`configs/training.json`: vocabulario 2.048, d_model 192, 6 cabezas, 4 capas, FFN 768, contexto 256, batch 4, CPU/6 threads. AdamW a 3e-4, weight decay 0,1, gradient clip 1,0, evaluación/checkpoint cada 100 pasos y early stopping tras 8 evaluaciones sin mejora de al menos 0,001. SFT usa optimizador nuevo, LR 1e-4, máximo 1.000 pasos y evaluación cada 25 pasos; el checkpoint solo se promociona si pasa la regresión configurada. Son parámetros conservadores de piloto, no receta de calidad demostrada.

## Criterios conversacionales propuestos

Antes de ejecutar, preparar y aprobar un test independiente de al menos 200 prompts humanos en español (no presentes en train/SFT) con categorías de explicación, seguimiento de instrucciones, resumen, escritura, diálogo, tareas cerradas verificables y abstención. Tres revisores puntúan a ciegas claridad, naturalidad, pertinencia, corrección y seguridad (1–5). Éxito de piloto: promedio ≥3,5/5 y ninguna categoría <3,0; ≥90% de exactitud en tareas cerradas; ≥80% de instrucciones seguidas; cero filtraciones de PII/señales peligrosas en la muestra; ninguna regresión >10% contra checkpoint pre-SFT. Reportar acuerdo entre revisores y ejemplos de fallos. Estos son umbrales de salida propuestos, no resultados ni evidencia de despliegue seguro; requieren aprobación humana y una política de revisión de errores.

## Registro y repetición

```powershell
python -m geri.training.cli benchmark --config configs/training.json --output C:\geri2-training-bench --benchmark-steps 30 --benchmark-repeats 3
```

El benchmark informa versiones, hilos, RAM disponible, RSS, tiempo por paso, tokens/s y tamaño de checkpoint. Los logs de entrenamiento registran pérdida train/validation, grad norm, tiempo transcurrido/restante estimado, tokens/s, RSS, RAM libre y disco libre por intervalo. Energy/thermal no se midieron.

El tamaño seleccionado es una decisión de throughput, no una conclusión de suficiencia lingüística: 238.848 parámetros es extremadamente pequeño para cubrir factualidad/conversación amplia. TinyStories muestra resultados pequeños en un dominio sintético restringido, y no se traslada esa evidencia al español del corpus. Se requiere corpus aprobado y evaluación humana antes de cualquier conclusión sobre capacidad.
