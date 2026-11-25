# Dimensionamiento y benchmarks

## Equipo observado en esta sesión

Windows, AMD Ryzen 5 7530U, 6 núcleos/12 hilos, 31,4 GiB RAM. En esta sesión D: reportó aproximadamente 0,1 GiB libres y C: 192,7 GiB libres. No se inspeccionó GPU dedicada y no se asume acelerador disponible. El almacenamiento debe medirse de nuevo en el destino elegido antes de cualquier descarga o entrenamiento.

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

No se ejecutó benchmark ni se instaló software. Falta fijar presupuesto de horas/energía y ubicación de almacenamiento. No se recomienda tamaño de modelo hasta obtener rendimiento medido y tamaño/calidad del corpus autorizado.
