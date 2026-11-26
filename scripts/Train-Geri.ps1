[CmdletBinding()]
param(
    [string]$PretrainingData = 'C:\Geriv2-Data\corpus\pretraining',
    [string]$Tokenizer = 'C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json',
    [string]$SftData = 'C:\Geriv2-Data\sft\candidate',
    [string]$Output = 'C:\Geriv2-Data\training\runs',
    [switch]$Resume
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = (Join-Path $ProjectRoot 'src') + [IO.Path]::PathSeparator + $env:PYTHONPATH
$Python = (Get-Command python -ErrorAction Stop).Source
$V1Python = Join-Path (Split-Path $ProjectRoot -Parent) 'Geri\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $V1Python) {
    & $V1Python -c "import torch, tokenizers"
    if ($LASTEXITCODE -eq 0) { $Python = $V1Python }
}

& $Python -c "import torch, tokenizers; print('PyTorch', torch.__version__, '| tokenizers', tokenizers.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'PyTorch o tokenizers no están disponibles en este entorno Python.' }

& $Python -m geri.data.cli offline-check --output $PretrainingData
if ($LASTEXITCODE -ne 0) { throw 'Falló la verificación offline del corpus de preentrenamiento.' }

$Arguments = @(
    '-m', 'geri.training.cli', 'train',
    '--config', (Join-Path $ProjectRoot 'configs/training.json'),
    '--data', $PretrainingData,
    '--tokenizer', $Tokenizer,
    '--sft-data', $SftData,
    '--sft-tokenizer', $Tokenizer,
    '--output', $Output,
    '--authorize-pretraining',
    '--authorize-sft'
)
if ($Resume) { $Arguments += '--resume' }

& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'El motor se detuvo; revise estado del corpus, checkpoints y logs.' }
