# Inferencia conversacional offline

El chat carga `promoted-sft.pt` en CPU con `weights_only=True`, comprueba el SHA-256 del archivo y contrasta los hashes de ambos manifiestos y del tokenizador original. Requiere aprobaciones explícitas para entrenamiento experimental privado, mantiene la prohibición de distribución y no certifica factualidad. No modifica pesos ni datos. El guard offline bloquea conexiones de red dentro del proceso.

La serialización coincide con SFT: cada mensaje es `<|user|>\ncontenido\n` o `<|assistant|>\ncontenido\n`; el prompt termina en `<|assistant|>\n`, sin BOS ni rol system. El contexto se limita al `max_seq_len` del checkpoint. Temperatura `0` selecciona greedy; `top-k 0` y `top-p 1` desactivan sus filtros.

Desde la raíz del proyecto, inicia la consola interactiva con:

```powershell
.\scripts\Chat-Geri.ps1
```

Parámetros opcionales: `-Temperature 0.8 -TopK 40 -TopP 0.9 -MaxNewTokens 96`. Escribe `/clear` para reiniciar el historial o `/exit` para salir. El prompt informa tokens generados, tokens/s y latencia de generación.

## Evaluación del checkpoint disponible

La prueba cualitativa determinista usó cuatro prompts breves, con generación greedy y hasta 48 tokens. Identidad, coherencia, seguimiento de la instrucción y generalización matemática no pasaron: produjo texto fragmentario o incoherente y no resolvió el problema aritmético. La velocidad medida en esta máquina fue 113–162 tokens/s (0,08–0,42 s por respuesta de 13–48 tokens); es una muestra corta, no una proyección de rendimiento sostenido.

El checkpoint reporta loss de validación SFT 3,485 en el mejor paso 825/975 y loss SFT de test 3,526. En el test reservado de preentrenamiento, la pérdida empeoró de 4,185 a 4,531 (8,3%); el motor la promovió porque su umbral de regresión es 10%. Esta métrica no predijo la calidad conversacional observada. No se inició entrenamiento durante esta tarea. El checkpoint se conserva intacto; la evaluación no justifica considerarlo un asistente útil. No se debe distribuir el checkpoint ni los corpus.
