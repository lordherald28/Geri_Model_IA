# Dimensionamiento y benchmarks

## Equipo observado en esta sesión

Windows, AMD Ryzen 5 7530U, 6 núcleos/12 hilos, 31,35 GiB RAM. En el preflight del 25-11-2026 C: reportó 192,4 GiB libres, D: 43,4 GiB libres y 11,3 GiB de RAM física disponible. Se conservaron el proyecto en D: y los artefactos de datos en C:; no se movieron ni eliminaron archivos. No se inspeccionó GPU dedicada y no se asume acelerador disponible. El almacenamiento y la RAM disponible deben medirse de nuevo antes de cada expansión o entrenamiento.

## Protocolo antes de elegir tamaño

1. Registrar CPU/GPU y memoria efectivamente disponible, sistema operativo, almacenamiento/sistema de archivos y procesos concurrentes.
2. Usar un microbenchmark reproducible del stack candidato en CPU; comparar varios tamaños candidatos derivados de un presupuesto explícito, no escoger cifras por intuición.
3. Medir tokens/segundo, memoria pico del proceso y del sistema, tiempo de inicio, uso de disco por dataset/checkpoint, estabilidad térmica y coste energético si hay medidor.
4. Estimar pasos/tiempo sobre volumen aprobado y reportar rango con margen de seguridad; distinguir capacidad de memoria de viabilidad temporal.
5. Repetir mediciones y registrar configuración, versiones, semilla y hashes. Definir umbral de RAM/disco reservado para el sistema y recuperación antes de correr.

## Matriz de decisión

| Recurso | Evidencia a medir | Criterio para continuar |
|---|---|---|
| CPU | tokens/s, uso sostenido, tiempo total estimado | ciclo completo dentro del presupuesto temporal acordado |
| RAM | pico de entrenamiento, loader y evaluación | pico más reserva operativa cabe sin paginación sostenida |
| Disco | corpus, shards, checkpoints, temporales y retención | capacidad disponible cubre todo el ciclo y recuperación |
| Presupuesto | horas, energía y coste de oportunidad | presupuesto explícito aprobado y experimento informativo |

## Resultados pendientes

No se ejecutó entrenamiento ni benchmark de rendimiento de modelo. El benchmark de preparación y tokenizador (CPU) está en [pipeline y resultados](data-pipeline.md). Falta fijar presupuesto de horas/energía para cualquier entrenamiento y rendimiento del modelo. No se recomienda tamaño de modelo hasta completar esas mediciones y las revisiones humanas del corpus.
