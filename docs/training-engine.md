# Motor de entrenamiento offline

## Alcance y decisiones

El motor es CPU-first y no contiene cliente HTTP, tracking remoto ni descarga de modelos. `GeriTransformer` es un decoder Transformer causal, pre-LayerNorm, GELU, embeddings de posición aprendidos, vocabulario compartido de entrada/salida y parámetros inicializados desde cero. La configuración de ejecución seleccionada tras comparar tres tamaños es `medium`: ancho 192, 4 capas, 6 cabezas, FFN 768, vocabulario 2.048, contexto 128 (2.194.560 parámetros). Sacrifica throughput frente a tiny/small para priorizar capacidad, y su RSS sintético de 417 MB cabe holgadamente en el equipo medido; esto no prueba calidad conversacional. TinyStories muestra que modelos pequeños pueden funcionar en un dominio sintético simple; no acredita el mismo resultado en español factual. SmolLM2 destaca la importancia de datos y fases diferenciadas a escala mucho mayor; Qwen2.5 no se replica. Se trasladan únicamente principios de procedencia, mezcla/fases separadas, evaluación y medir antes de dimensionar. [TinyStories](https://arxiv.org/abs/2305.07759), [SmolLM2](https://arxiv.org/abs/2502.02737), [Qwen2.5](https://arxiv.org/abs/2412.15115).

El preentrenamiento consume solo `train.jsonl`; la validación es independiente. Un manifiesto debe decir `dataset_status: approved_for_training`, contener `training_authorization: human_review_approved` y hashes correctos de los splits. El pipeline actual deliberadamente produce `technically_prepared_candidate; human source review pending`, por lo que el loader lo rechaza.

Los artefactos SFT se preparan por separado. El input JSONL tiene una fila por conversación con `conversation_id`, `source_id` y `messages` alternados entre `user` y `assistant`; el registro de fuentes aporta URL, licencia exacta y atribución. El preparador valida estructura, duplicados y patrones comunes de PII, asigna train/validation/test de forma determinista por conversación y guarda hashes; el manifest queda siempre en revisión pendiente. El loader exige autorización humana, hash del tokenizador y de los tres splits, aprobación de cada fuente, consistencia de licencia/URL/atribución, ausencia de PII detectada y ninguna fuga entre splits. En SFT, el loss ignora los tokens user y optimiza las respuestas assistant. No existe corpus SFT de producto entregado en este repositorio.

Fila de entrada (`conversations.jsonl`):

```json
{"conversation_id":"c-0001","source_id":"manual-source-1","messages":[{"role":"user","content":"¿Qué es una planta?"},{"role":"assistant","content":"Es un ser vivo que suele producir su propio alimento mediante fotosíntesis."}]}
```

El ejemplo solo define el formato; no es un registro de corpus ni una afirmación de que el dataset esté revisado. El registro `sources.json` debe contener `source_id`, `source_url`, licencia/version exacta y atribución. La herramienta deriva la procedencia por fila del registro en lugar de confiar en campos de licencia suministrados en el JSONL.

## Instalación local

```powershell
Set-Location 'D:\Proyectos\!!!LEARN DL - ML - LLM\Geriv2'
python -m pip install -e ".[training,dev]"
```

Para instalación aislada, preparar wheels para el mismo Windows, arquitectura y versión menor de Python, verificar sus SHA-256 en un registro de operador, copiarlos al equipo y usar:

```powershell
python -m pip install --no-index --find-links .\wheelhouse -e ".[training,dev]"
```

El motor no necesita red una vez instaladas sus dependencias y presentes snapshots, tokenizador y datos congelados.

## Benchmark de tamaño

```powershell
python -m geri.training.cli benchmark --config configs/training.json --output C:\geri2-training-bench --benchmark-steps 30 --benchmark-repeats 3
```

Comparar tamaños sintéticos tiny/small/medium; guardar `model-benchmark.json`. Se registran 30 pasos por repetición, 3 repeticiones, tokens/s, working set RSS, RAM disponible y bytes de checkpoint. No mide calidad ni viabilidad de entrenar el corpus completo.

Preparar un candidato conversacional desde archivos locales (requiere un registro de fuentes real):

```powershell
python -m geri.training.cli prepare-sft --config configs/training.json --input C:\geri2-sft-input\conversations.jsonl --sources C:\geri2-sft-input\sources.json --data C:\geri2-sft --tokenizer C:\geri2-corpus\tokenizer\tokenizer.json
```

La salida sigue pendiente y no se puede entrenar hasta cerrar y registrar la revisión humana de fuentes, PII, factualidad y calidad.

## Smoke test (solo fixture sintético)

Primer comando genera una fixture en `C:\geri2-smoke-data` y se detiene:

```powershell
geri-train smoke --config configs/training.json --data C:\geri2-smoke-data --tokenizer C:\geri2-smoke-data\tokenizer\tokenizer.json --output C:\geri2-smoke-runs --steps 3
```

Solo después de inspeccionar que el manifiesto dice `synthetic_smoke_test_only`, el segundo comando autoriza hasta tres pasos sintéticos y escribe checkpoints en otra carpeta:

```powershell
geri-train smoke --config configs/training.json --data C:\geri2-smoke-data --tokenizer C:\geri2-smoke-data\tokenizer\tokenizer.json --output C:\geri2-smoke-runs --steps 3 --authorize-pretraining
```

## Entrenamiento manual con corpus aprobado

Después de resolver y registrar toda revisión humana de cada fuente, congelar el corpus y emitir expresamente en ambos manifests `dataset_status: approved_for_training`, `training_authorization: human_review_approved`, `human_review.decision: approved`, persona/fecha, `review_status: human_approved` para cada fuente y hashes de tokenizador/splits. La ejecución definitiva se inicia únicamente cuando el usuario ejecuta manualmente:

```powershell
& .\scripts\Train-Geri.ps1 -PretrainingData C:\geri2-corpus -Tokenizer C:\geri2-corpus\tokenizer\tokenizer.json -SftData C:\geri2-sft -Output C:\geri2-training-runs
```

Para reanudar desde el último intervalo comprobado, con los mismos datos, configuración y salida:

```powershell
& .\scripts\Train-Geri.ps1 -PretrainingData C:\geri2-corpus -Tokenizer C:\geri2-corpus\tokenizer\tokenizer.json -SftData C:\geri2-sft -Output C:\geri2-training-runs -Resume
```

Los checkpoints guardan estado de modelo, AdamW, contador, generadores aleatorios, configuración, historial y procedencia del manifiesto. Se guardan atómicamente en cada intervalo de evaluación con SHA-256 y copia previa para recuperación; `best.pt` conserva la menor pérdida de validación. El script aplica una guarda de red en el proceso Python y comprueba snapshots del corpus offline. El script PowerShell no cambia firewall del sistema: iniciar sin conexión de red. Si SFT excede la regresión del 10% sobre el test reservado del preentrenamiento, `promoted-sft.pt` no se crea y se conserva `pretraining/best.pt`.

La ejecución de corpus no es una recomendación para el estado actual: la autorización humana no existe todavía. No usar la bandera como sustituto de la revisión. No ejecutar esta fase definitiva hasta cerrar licencias, procedencia, calidad, PII, factualidad y aprobación de fuentes, y repetir benchmark/capacidad.

## Estado y limitaciones

- PyTorch 2.15.0+cpu se reutilizó desde el `.venv` de Geri v1 en modo solo lectura; no se modificó Geri v1 ni se usaron sus datos, pesos o tokenizador.
- La reanudación serializa estado aleatorio de Python y PyTorch; la reproducción bit a bit puede variar con versiones de CPU/runtime. Se debe mantener la misma versión y configuración.
- La regresión usa límite de razón 1,10 sobre test reservado de preentrenamiento; SFT test se informa aparte y no elige el checkpoint.
- El corpus de preentrenamiento local sigue pendiente de revisión humana y no hay corpus SFT preparado. La revisión documental no equivale a aprobación legal ni de factualidad. El entrenamiento de producto queda bloqueado.
- No se crea checkpoint de inferencia empaquetado ni generador de texto; están fuera de esta fase del motor.
- El consumo energético y térmico requieren medición externa. La predicción de tiempo restante es extrapolación lineal.
