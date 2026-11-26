# Motor de entrenamiento offline

## Alcance y decisiones

El motor es CPU-first y no contiene cliente HTTP, tracking remoto ni descarga de modelos. `GeriTransformer` es un decoder Transformer causal, pre-LayerNorm, GELU, embeddings de posición aprendidos, vocabulario compartido de entrada/salida y parámetros inicializados desde cero. La configuración de ejecución seleccionada tras comparar tres tamaños es `medium`: ancho 192, 4 capas, 6 cabezas, FFN 768, vocabulario 2.048, contexto 256 (2.219.136 parámetros). Sacrifica throughput frente a tiny/small para priorizar capacidad y contexto; su RSS sintético de 519 MB cabe holgadamente en el equipo medido, pero no prueba calidad conversacional. TinyStories muestra que modelos pequeños pueden funcionar en un dominio sintético simple; no acredita el mismo resultado en español factual. SmolLM2 destaca la importancia de datos y fases diferenciadas a escala mucho mayor; Qwen2.5 no se replica. Se trasladan únicamente principios de procedencia, mezcla/fases separadas, evaluación y medir antes de dimensionar. [TinyStories](https://arxiv.org/abs/2305.07759), [SmolLM2](https://arxiv.org/abs/2502.02737), [Qwen2.5](https://arxiv.org/abs/2412.15115).

El preentrenamiento consume solo `train.jsonl`; la validación es independiente. Un manifiesto debe decir `dataset_status: approved_for_training`, contener `training_authorization: human_review_approved` y hashes correctos de los splits. El pipeline actual deliberadamente produce `technically_prepared_candidate; human source review pending`, por lo que el loader lo rechaza.

Los artefactos SFT se preparan por separado. El input JSONL tiene una fila por conversación con `conversation_id`, `source_id` y `messages` alternados entre `user` y `assistant`; el registro de fuentes aporta URL, licencia exacta y atribución. El preparador valida estructura, duplicados y patrones comunes de PII, asigna train/validation/test de forma determinista por conversación y guarda hashes; el manifest queda siempre en revisión pendiente. El loader exige autorización humana, hash del tokenizador y de los tres splits, aprobación de cada fuente, consistencia de licencia/URL/atribución, ausencia de PII detectada y ninguna fuga entre splits. En SFT, el loss ignora los tokens user y optimiza las respuestas assistant.

El snapshot fijado de OASST1 produjo 779 pares iniciales. La revisión determinista descartó 46 respuestas claramente incompatibles o con errores conocidos y retuvo 733; no reescribió respuestas OASST. Se añadieron ocho conversaciones originales de Geri de dos turnos. El candidato tiene 741 conversaciones en splits 666/37/38. El manifest, hashes, cola de 741 registros y muestra de 200 están en `C:\Geriv2-Data\sft\candidate`; el manifest sigue sin aprobar. `scripts/curate_sft_candidate.py` reproduce la curación con la fuente de diálogos original conservada fuera de Git en `C:\Geriv2-Data\sft\source-workspace\curated-input-20261125`.

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

El motor no necesita red una vez instaladas sus dependencias y presentes snapshots, tokenizador y datos congelados. La configuración actual de trabajo no añade PyTorch al `.venv` de Geriv2; las operaciones de preparación de datos no lo importan. El launcher reutiliza el `.venv` de Geri v1 solo si sus dependencias están disponibles.

## Benchmark de tamaño

```powershell
python -m geri.training.cli benchmark --config configs/training.json --output C:\Geriv2-Data\benchmarks\training-engine --benchmark-steps 30 --benchmark-repeats 3
```

Comparar tamaños sintéticos tiny/small/medium; guardar `model-benchmark.json`. Se registran 30 pasos por repetición, 3 repeticiones, tokens/s, working set RSS, RAM disponible y bytes de checkpoint. No mide calidad ni viabilidad de entrenar el corpus completo.

Preparar un candidato conversacional desde archivos locales (requiere un registro de fuentes real):

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts\curate_sft_candidate.py --input C:\Geriv2-Data\sft\source-workspace\candidate-input-256\conversations.jsonl --geri-dialogues C:\Geriv2-Data\sft\source-workspace\curated-input-20261125\geri_identity_source.jsonl --tokenizer C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json --output C:\Geriv2-Data\sft\source-workspace\curated-input-20261125 --max-seq-len 256
python -m geri.training.cli prepare-sft --config configs\training.json --input C:\Geriv2-Data\sft\source-workspace\curated-input-20261125\conversations.jsonl --sources C:\Geriv2-Data\sft\source-workspace\curated-input-20261125\sources.json --data C:\Geriv2-Data\sft\candidate --tokenizer C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json
```

La preparación SFT usa solo Python y `tokenizers`; PyTorch se carga al entrar en benchmark, smoke o entrenamiento. La salida sigue pendiente y no se puede entrenar hasta cerrar y registrar la revisión humana de fuentes, PII, factualidad y calidad.

## Smoke test (solo fixture sintético)

Primer comando genera una fixture en `C:\Geriv2-Data\tests\smoke-data` y se detiene:

```powershell
geri-train smoke --config configs/training.json --data C:\Geriv2-Data\tests\smoke-data --tokenizer C:\Geriv2-Data\tests\smoke-data\tokenizer\tokenizer.json --output C:\Geriv2-Data\tests\smoke-runs --steps 3
```

Solo después de inspeccionar que el manifiesto dice `synthetic_smoke_test_only`, el segundo comando autoriza hasta tres pasos sintéticos y escribe checkpoints en otra carpeta:

```powershell
geri-train smoke --config configs/training.json --data C:\Geriv2-Data\tests\smoke-data --tokenizer C:\Geriv2-Data\tests\smoke-data\tokenizer\tokenizer.json --output C:\Geriv2-Data\tests\smoke-runs --steps 3 --authorize-pretraining
```

## Entrenamiento manual con corpus aprobado

Después de resolver y registrar toda revisión humana de cada fuente, congelar el corpus y emitir expresamente en ambos manifests `dataset_status: approved_for_training`, `training_authorization: human_review_approved`, `human_review.decision: approved`, persona/fecha, `review_status: human_approved` para cada fuente y hashes de tokenizador/splits. La ejecución definitiva se inicia únicamente cuando el usuario ejecuta manualmente:

Para comprobar de extremo a extremo la selección de Python, manifests, hashes, loaders, alcance privado, recursos y forward del modelo con los corpus aprobados sin crear optimizador ni checkpoints, usar `-PreflightOnly`. El reporte queda en `C:\Geriv2-Data\tests\training-startup\startup-preflight.json`:

```powershell
.\scripts\Train-Geri.ps1 -PreflightOnly
```

El launcher definitivo aplica el mismo contexto 256 desde `configs/training.json` a ambos loaders; el preflight valida vocabulario 2.048, autorización experimental privada y forward `[1,256,2048]`. La prueba de preflight no ejecuta pasos de entrenamiento.

```powershell
& .\scripts\Train-Geri.ps1 -PretrainingData C:\Geriv2-Data\corpus\pretraining -Tokenizer C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json -SftData C:\Geriv2-Data\sft\candidate -Output C:\Geriv2-Data\training\runs
```

Para reanudar desde el último intervalo comprobado, con los mismos datos, configuración y salida:

```powershell
& .\scripts\Train-Geri.ps1 -PretrainingData C:\Geriv2-Data\corpus\pretraining -Tokenizer C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json -SftData C:\Geriv2-Data\sft\candidate -Output C:\Geriv2-Data\training\runs -Resume
```

Los checkpoints guardan estado de modelo, AdamW, contador, generadores aleatorios, configuración, historial y procedencia del manifiesto. Se guardan atómicamente en cada intervalo de evaluación con SHA-256 y copia previa para recuperación; `best.pt` conserva la menor pérdida de validación. El script aplica una guarda de red en el proceso Python y comprueba snapshots del corpus offline. El script PowerShell no cambia firewall del sistema: iniciar sin conexión de red. Si SFT excede la regresión del 10% sobre el test reservado del preentrenamiento, `promoted-sft.pt` no se crea y se conserva `pretraining/best.pt`.

La ejecución de corpus no es una recomendación para el estado actual: la autorización humana no existe todavía. No usar la bandera como sustituto de la revisión. No ejecutar esta fase definitiva hasta cerrar licencias, procedencia, calidad, PII, factualidad y aprobación de fuentes, y repetir benchmark/capacidad.

## Estado y limitaciones

- PyTorch 2.15.0+cpu se reutilizó desde el `.venv` de Geri v1 en modo solo lectura; no se modificó Geri v1 ni se usaron sus datos, pesos o tokenizador.
- La reanudación serializa estado aleatorio de Python y PyTorch; la reproducción bit a bit puede variar con versiones de CPU/runtime. Se debe mantener la misma versión y configuración.
- La regresión usa límite de razón 1,10 sobre test reservado de preentrenamiento; SFT test se informa aparte y no elige el checkpoint.
- El corpus de preentrenamiento (48.873 registros ELTeC/BOE) y el candidato SFT (741 conversaciones, incluidas ocho de autoría del proyecto) siguen pendientes de revisión humana. Se excluyó CORDIS y se preservó en cuarentena. La revisión documental no equivale a aprobación legal ni de factualidad. El entrenamiento de producto queda bloqueado.
- No se crea checkpoint de inferencia empaquetado ni generador de texto; están fuera de esta fase del motor.
- El consumo energético y térmico requieren medición externa. La predicción de tiempo restante es extrapolación lineal.
