[CmdletBinding()]
param([string]$DataRoot = 'C:\Geriv2-Data')

$ErrorActionPreference = 'Stop'
$ExpectedRoot = [IO.Path]::GetFullPath('C:\Geriv2-Data')
$ResolvedRoot = (Resolve-Path -LiteralPath $DataRoot).Path
if ($ResolvedRoot -ne $ExpectedRoot) { throw "Unexpected data root: $ResolvedRoot" }

$ManifestPath = Join-Path $ResolvedRoot 'migration-manifest.json'
$Manifest = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
if ($Manifest.status -notmatch 'copied_and_sha256_verified|relocation_data_verified') {
    throw "Migration is not in verified-copy state: $($Manifest.status)"
}

$LegacyRoots = @(
    'C:\geri2-bench-context256', 'C:\geri2-bench-context256-final', 'C:\geri2-bench-final',
    'C:\geri2-corpus', 'C:\geri2-engine-smoke', 'C:\geri2-engine-smoke-run',
    'C:\geri2-engine-smoke2', 'C:\geri2-engine-smoke2-run', 'C:\geri2-package-check',
    'C:\geri2-sft', 'C:\geri2-sft-source', 'C:\geri2-training-bench'
)

# Verify every original and relocated file before removing any legacy directory.
foreach ($Entry in $Manifest.files) {
    $Source = [IO.Path]::GetFullPath($Entry.source)
    $Destination = [IO.Path]::GetFullPath((Join-Path $ResolvedRoot $Entry.destination))
    $SourceRoot = Join-Path 'C:\' ($Source.Substring(3).Split('\')[0])
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf) -and $SourceRoot -notin $LegacyRoots) {
        throw "Source missing outside an expected legacy root: $Source"
    }
    if (-not (Test-Path -LiteralPath $Destination -PathType Leaf)) { throw "Destination missing: $Destination" }
    if (Test-Path -LiteralPath $Source -PathType Leaf) {
        if ((Get-Item -LiteralPath $Source).Length -ne $Entry.bytes) { throw "Source size mismatch: $Source" }
        if ((Get-FileHash -LiteralPath $Source -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256) {
            throw "Source hash mismatch: $Source"
        }
    }
    if ((Get-Item -LiteralPath $Destination).Length -ne $Entry.bytes_after_relocation_and_reference_updates) {
        throw "Destination size mismatch: $Destination"
    }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Entry.sha256_after_relocation_and_reference_updates) {
        throw "Destination hash mismatch: $Destination"
    }
}

$RemovedRoots = [Collections.Generic.List[string]]::new()
foreach ($LegacyRoot in $LegacyRoots) {
    $FullPath = [IO.Path]::GetFullPath($LegacyRoot)
    if ($FullPath -notmatch '^C:\\geri2-[^\\]+$') { throw "Unsafe cleanup target: $FullPath" }
    if (-not (Test-Path -LiteralPath $FullPath -PathType Container)) { $RemovedRoots.Add($FullPath); continue }
    if ((Resolve-Path -LiteralPath $FullPath).Path -ne $FullPath) { throw "Resolved path mismatch: $FullPath" }
}

$LockedRoots = [Collections.Generic.List[string]]::new()
foreach ($LegacyRoot in $LegacyRoots) {
    if (-not (Test-Path -LiteralPath $LegacyRoot -PathType Container)) { continue }
    try {
        Remove-Item -LiteralPath $LegacyRoot -Recurse -Force -ErrorAction Stop
        $RemovedRoots.Add($LegacyRoot)
    }
    catch {
        $LockedRoots.Add($LegacyRoot)
    }
}

$RemainingRoots = @(Get-ChildItem -LiteralPath 'C:\' -Directory -Force | Where-Object { $_.Name -like 'geri2-*' } | Select-Object -ExpandProperty FullName)
$Manifest.status = if ($RemainingRoots.Count -eq 0) {
    'relocation_complete; source_and_destination_sha256_verified; old_roots_removed'
} else {
    'relocation_data_verified; some_legacy_roots_locked_and_retained'
}
$Manifest | Add-Member -NotePropertyName removed_legacy_roots -NotePropertyValue $RemovedRoots.ToArray() -Force
$Manifest | Add-Member -NotePropertyName retained_legacy_roots -NotePropertyValue $RemainingRoots -Force
$Manifest | Add-Member -NotePropertyName completed_utc -NotePropertyValue ([DateTime]::UtcNow.ToString('o')) -Force
$Manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $ManifestPath -Encoding utf8
Write-Output "Verified $($Manifest.files.Count) files; removed $($RemovedRoots.Count) old roots; retained $($RemainingRoots.Count) locked roots."
