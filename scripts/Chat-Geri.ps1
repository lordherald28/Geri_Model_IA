[CmdletBinding()]
param(
    [string]$Checkpoint = 'C:\Geriv2-Data\training\runs\promoted-sft.pt',
    [string]$Tokenizer = 'C:\Geriv2-Data\corpus\pretraining\tokenizer\tokenizer.json',
    [string]$PretrainingManifest = 'C:\Geriv2-Data\corpus\pretraining\processed\manifest.json',
    [string]$SftManifest = 'C:\Geriv2-Data\sft\candidate\processed\manifest.json',
    [double]$Temperature = 0.8,
    [int]$TopK = 40,
    [double]$TopP = 0.9,
    [int]$MaxNewTokens = 96
)

$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:PYTHONPATH = (Join-Path $ProjectRoot 'src') + [IO.Path]::PathSeparator + $env:PYTHONPATH
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:PYTHONUTF8 = '1'
$Python = (Get-Command python -ErrorAction Stop).Source
$V1Python = Join-Path (Split-Path $ProjectRoot -Parent) 'Geri\.venv\Scripts\python.exe'
if (Test-Path -LiteralPath $V1Python) {
    & $V1Python -c "import torch, tokenizers"
    if ($LASTEXITCODE -eq 0) { $Python = $V1Python }
}
& $Python -c "import torch, tokenizers; print('PyTorch', torch.__version__, '| tokenizers', tokenizers.__version__)"
if ($LASTEXITCODE -ne 0) { throw 'PyTorch o tokenizers no están disponibles en este entorno Python.' }

$Arguments = @(
    '-m', 'geri.inference.cli',
    '--checkpoint', $Checkpoint,
    '--tokenizer', $Tokenizer,
    '--pretraining-manifest', $PretrainingManifest,
    '--sft-manifest', $SftManifest,
    '--temperature', $Temperature.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--top-k', $TopK.ToString(),
    '--top-p', $TopP.ToString([Globalization.CultureInfo]::InvariantCulture),
    '--max-new-tokens', $MaxNewTokens.ToString()
)
& $Python @Arguments
if ($LASTEXITCODE -ne 0) { throw 'La inferencia se detuvo; revise checkpoint, hashes y manifiestos aprobados.' }
