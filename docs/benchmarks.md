# Dimensionamiento del modelo y benchmarks

## Equipo y medición

Windows; AMD Ryzen 5 7530U, 6 núcleos/12 hilos; 31,35 GiB RAM. PyTorch 2.15.0+cpu, Python 3.12.10, seis hilos intra-op. Durante la medición había 12,95 GB de RAM física disponibles y aproximadamente 206 GB libres en C:. No se identificó GPU de entrenamiento. Medición repetible y agregado en [`model-benchmark-20261125.json`](../benchmarks/model-benchmark-20261125.json).

Se compararon tres tamaños en CPU con batch 4, contexto 128, 2 pasos de calentamiento y 30 pasos medidos por repetición, 3 repeticiones cada uno. Entradas de tokens aleatorios: sirve para dimensionar compute/memoria, no calidad ni flujo de lectura del corpus.

| Candidato | Parámetros | Tokens/s promedio (rango) | RSS pico absoluto | Checkpoint |
|---|---:|---:|---:|---:|
| tiny: d=64, 2 capas | 238.848 | 19.422 (18.906–19.758) | 332 MB | 2,90 MB |
| small: d=128, 4 capas | 1.069.824 | 5.949 (5.553–6.186) | 378 MB | 12,89 MB |
| medium: d=192, 4 capas | 2.194.560 | 4.040 (3.880–4.144) | 417 MB | 26,39 MB |

Se selecciona `tiny` para el piloto por throughput y coste de checkpoint; la RAM medida está muy por debajo de la reserva configurada de 3 GiB. RSS pico absoluto incluye runtime/PyTorch y cachés del allocator; entre réplicas el baseline varía. La carga real podría usar más memoria por tokenizar 48.948 registros y mantener splits en RAM.

Para el corpus candidato actual hay 1,883,060 tokens BPE en train y 563,753 en validation. Con batch 4, contexto 128 y límite de 10.000 pasos se procesarían hasta 5,12 M posiciones objetivo (2,72 recorridos equivalentes sobre tokens train), aproximadamente 4,4 min a throughput sintético promedio, sin evaluación, checkpoints, preparación ni carga. La duración real será mayor; el coste completo no se ha medido ni debe usarse como promesa.

## Configuración medida

`configs/training.json`: vocabulario 2.048, d_model 64, 2 cabezas, 2 capas, FFN 256, contexto 128, batch 4, CPU/6 threads. AdamW a 3e-4, weight decay 0,1, gradient clip 1,0, evaluación/checkpoint cada 100 pasos y early stopping tras 8 evaluaciones sin mejora de al menos 0,001. SFT se ejecuta después con optimizador nuevo, LR 1e-4, máximo 1.000 pasos y evaluación cada 25 pasos; la elección final de SFT debe superar el gate de regresión. Son hiperparámetros piloto; no se han entrenado sobre corpus aprobado.

## Registro y repetición

```powershell
python -m geri.training.cli benchmark --config configs/training.json --output C:\geri2-training-bench --benchmark-steps 30 --benchmark-repeats 3
```

El benchmark informa versiones, hilos, RAM disponible, RSS, tiempo por paso, tokens/s y tamaño de checkpoint. Los logs de entrenamiento registran pérdida train/validation, grad norm, tiempo transcurrido/restante estimado, tokens/s, RSS, RAM libre y disco libre por intervalo. Energy/thermal no se midieron.

El tamaño seleccionado es una decisión de throughput, no una conclusión de suficiencia lingüística: 238.848 parámetros es extremadamente pequeño para cubrir factualidad/conversación amplia. TinyStories muestra resultados pequeños en un dominio sintético restringido, y no se traslada esa evidencia al español del corpus. Se requiere corpus aprobado y evaluación humana antes de cualquier conclusión sobre capacidad.
