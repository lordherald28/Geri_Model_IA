# Dimensionamiento del modelo y benchmarks

## Equipo y medición

Windows; AMD Ryzen 5 7530U, 6 núcleos/12 hilos; 31,35 GiB RAM. PyTorch 2.15.0+cpu, Python 3.12.10, seis hilos intra-op. Durante la medición había 12,95 GB de RAM física disponibles y aproximadamente 206 GB libres en C:. No se identificó GPU de entrenamiento. Medición repetible y agregado en [`model-benchmark-20261125.json`](../benchmarks/model-benchmark-20261125.json).

Se compararon tres tamaños en CPU con batch 4, contexto 128, 2 pasos de calentamiento y 30 pasos medidos por repetición, 3 repeticiones cada uno. Entradas de tokens aleatorios: sirve para dimensionar compute/memoria, no calidad ni flujo de lectura del corpus.

| Candidato | Parámetros | Tokens/s promedio (rango) | RSS pico absoluto | Checkpoint |
|---|---:|---:|---:|---:|
| tiny: d=64, 2 capas | 238.848 | 21.790 (19.695–22.848) | 332 MB | 2,90 MB |
| small: d=128, 4 capas | 1.069.824 | 6.545 (5.670–7.286) | 379 MB | 12,89 MB |
| medium: d=192, 4 capas | 2.194.560 | 4.656 (4.093–5.080) | 421 MB | 26,39 MB |

La configuración de ejecución queda en `medium` (d=192, 4 capas, 6 cabezas, FFN 768): tiene 9,2 veces los parámetros de tiny y 2,1 veces los de small, a cambio de 4,7 veces menos tokens/s que tiny. Se prefiere esa capacidad adicional porque la meta es lenguaje/conversación, no throughput aislado; su RSS de benchmark es 421 MB y checkpoint 26,4 MB, razonables frente a 12,98 GB disponibles. Es todavía un modelo de investigación muy pequeño y no hay evidencia de calidad hasta entrenar/evaluar con datos aprobados. No se seleccionó por generación de calidad, que no se pudo probar con corpus bloqueados.

Para el corpus candidato actual hay 1.883.060 tokens BPE en train y 563.753 en validation. Con `medium`, batch 4, contexto 128 y límite de 10.000 pasos se procesarían hasta 5,12 M posiciones objetivo (2,72 recorridos equivalentes) en unos 18 min a throughput sintético promedio. Las evaluaciones añaden hasta 1,64 M posiciones forward; SFT añade hasta 0,51 M posiciones de entrenamiento y 0,66 M de evaluación. Extrapolando a las mediciones CPU, la planificación es 30–50 min para ambas fases, incluyendo evaluaciones y checkpoints, pero sin garantía: no se midió una corrida completa, la carga/tokenización ni variación térmica; early stopping puede reducirlo. Recalcular con el benchmark local antes de iniciar.

## Configuración medida

`configs/training.json`: vocabulario 2.048, d_model 192, 6 cabezas, 4 capas, FFN 768, contexto 128, batch 4, CPU/6 threads. AdamW a 3e-4, weight decay 0,1, gradient clip 1,0, evaluación/checkpoint cada 100 pasos y early stopping tras 8 evaluaciones sin mejora de al menos 0,001. SFT usa optimizador nuevo, LR 1e-4, máximo 1.000 pasos y evaluación cada 25 pasos; el checkpoint solo se promociona si pasa la regresión configurada. Son parámetros conservadores de piloto, no receta de calidad demostrada.

## Criterios conversacionales propuestos

Antes de ejecutar, preparar y aprobar un test independiente de al menos 200 prompts humanos en español (no presentes en train/SFT) con categorías de explicación, seguimiento de instrucciones, resumen, escritura, diálogo, tareas cerradas verificables y abstención. Tres revisores puntúan a ciegas claridad, naturalidad, pertinencia, corrección y seguridad (1–5). Éxito de piloto: promedio ≥3,5/5 y ninguna categoría <3,0; ≥90% de exactitud en tareas cerradas; ≥80% de instrucciones seguidas; cero filtraciones de PII/señales peligrosas en la muestra; ninguna regresión >10% contra checkpoint pre-SFT. Reportar acuerdo entre revisores y ejemplos de fallos. Estos son umbrales de salida propuestos, no resultados ni evidencia de despliegue seguro; requieren aprobación humana y una política de revisión de errores.

## Registro y repetición

```powershell
python -m geri.training.cli benchmark --config configs/training.json --output C:\geri2-training-bench --benchmark-steps 30 --benchmark-repeats 3
```

El benchmark informa versiones, hilos, RAM disponible, RSS, tiempo por paso, tokens/s y tamaño de checkpoint. Los logs de entrenamiento registran pérdida train/validation, grad norm, tiempo transcurrido/restante estimado, tokens/s, RSS, RAM libre y disco libre por intervalo. Energy/thermal no se midieron.

El tamaño seleccionado es una decisión de throughput, no una conclusión de suficiencia lingüística: 238.848 parámetros es extremadamente pequeño para cubrir factualidad/conversación amplia. TinyStories muestra resultados pequeños en un dominio sintético restringido, y no se traslada esa evidencia al español del corpus. Se requiere corpus aprobado y evaluación humana antes de cualquier conclusión sobre capacidad.
