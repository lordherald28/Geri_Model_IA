# Metodología de datos y entrenamiento

## Tokenización

Definir normalización reversible y reglas Unicode antes de comparar tokenizadores. Entrenar un tokenizador nuevo solo sobre el corpus aprobado de entrenamiento, sin leer vocabularios o artefactos de Geri. Comparar candidatos por compresión en español (incluidos acentos, variantes regionales, código y cifras), cobertura, estabilidad y coste de entrenamiento; vocabulario se elige empíricamente y se registra con versión/hash. Mantener validación/test fuera del ajuste del tokenizador cuando se mida generalización.

## Preentrenamiento

Modelo desde inicialización aleatoria. Dataset empaquetado con separación por documento, muestras deterministas y semilla registrada. Medir pérdida en validación y tasa de tokens/segundo, memoria pico, temperatura/consumo si disponible y coste por millón de tokens. La decisión de continuar requiere mejora de validación, ausencia de fuga y estabilidad; pérdida sola no acredita utilidad lingüística.

## Conversación

Tratar corpus conversacional como una fase posterior, separada del preentrenamiento. El contrato de entrada usa pares alternados user/assistant y splits por conversación. `prepare-sft` valida procedencia de la fuente, estructura, duplicados y PII común; deja manifest pendiente. El loader requiere revisión/aprobación humana y entrena loss solo en respuestas assistant. Evaluar en un conjunto humano reservado y reportar factualidad, seguimiento de instrucciones, fluidez, sesgos y abstención. No asumir que aprendizaje continuo equivale a actualización segura.

## Aprendizaje continuo

Cada ciclo consume dataset/versionado nuevo y una copia identificable del checkpoint aprobado. Ejecutar evaluación de regresión sobre capacidades anteriores, olvido catastrófico, contaminación y reversibilidad. Promover un checkpoint solo con criterios predefinidos; conservar baseline y artefactos recuperables. La política de mezcla/replay se decide tras medir olvido, no se fija aquí.

## Evaluación y checkpoints

Separar evaluación automática determinista y revisión humana ciega. Métricas mínimas: pérdida/perplejidad por dominio, calidad de generación con rúbrica, factualidad en preguntas con fuentes, formato/seguimiento, toxicidad/PII y latencia. Publicar intervalos/errores y ejemplos con licencia. Checkpoints atómicos con configuración, hashes de código/datos/tokenizador, paso, métricas, estado de optimizador cuando aplique y comprobación de integridad; política de retención y recuperación definida antes de entrenar.

## Inferencia

Ejecutable local desde artefactos fijados, con generación reproducible cuando la configuración lo permita, límites de memoria/contexto y medición de latencia/uso de RAM. Sin llamadas de red por defecto. Registrar límites conocidos del modelo; no presentar salidas como hechos verificados.
