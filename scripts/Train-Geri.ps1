[CmdletBinding()]
param(
    [string]$PretrainingData = 'C:\geri2-corpus',
    [string]$Tokenizer = 'C:\geri2-corpus\tokenizer\tokenizer.json',
    [string]$SftData = 'C:\geri2-sft',
    [string]$Output = 'C:\geri2-training-runs',
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
