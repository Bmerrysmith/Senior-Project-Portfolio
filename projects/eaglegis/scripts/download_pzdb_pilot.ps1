# Download PZDB pilot PDFs from app/data/documents.csv into data/raw/pzdb/{year}/
# Usage: powershell -File scripts/download_pzdb_pilot.ps1 [-IncludePending2025]

param(
    [switch]$IncludePending2025
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$docsPath = Join-Path $Root "app\data\documents.csv"
$outRoot = Join-Path $Root "data\raw\pzdb"

foreach ($year in 2022..2025) {
    New-Item -ItemType Directory -Force -Path (Join-Path $outRoot $year) | Out-Null
}

$rows = Import-Csv $docsPath | Where-Object {
    $_.type_name -match 'Planning Zoning' -and
    [int]$_.meeting_year -ge 2022 -and [int]$_.meeting_year -le 2025
}
if (-not $IncludePending2025) {
    $rows = $rows | Where-Object { $_.status -eq 'Accepted' }
}

$manifest = @()
$log = @()

foreach ($r in $rows) {
    $dt = [datetime]::Parse($r.meeting_date)
    $canonical = ('{0:yyyyMMdd} PZDB Minutes.pdf' -f $dt)
    $rel = "data/raw/pzdb/$($r.meeting_year)/$canonical"
    $dest = Join-Path $Root ($rel -replace '/', '\')

    $manifest += [PSCustomObject]@{
        meeting_id     = $r.meeting_id
        meeting_date   = $r.meeting_date
        meeting_year   = $r.meeting_year
        status         = $r.status
        source_url     = $r.file_url
        canonical_name = $canonical
        rel_path       = $rel
    }

    if (Test-Path $dest) {
        $log += [PSCustomObject]@{ file = $canonical; status = 'skipped_exists' }
        continue
    }
    try {
        Invoke-WebRequest -Uri $r.file_url -OutFile $dest -UseBasicParsing
        $log += [PSCustomObject]@{ file = $canonical; status = 'ok' }
    }
    catch {
        $log += [PSCustomObject]@{ file = $canonical; status = "fail: $($_.Exception.Message)" }
    }
    Start-Sleep -Milliseconds 350
}

$manifest | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outRoot "manifest_pilot.csv")
$log | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $outRoot "download_log.csv")

Write-Host "Manifest rows: $($manifest.Count)"
$log | Group-Object status | Format-Table Name, Count -AutoSize
$failed = $log | Where-Object { $_.status -notmatch '^(ok|skipped_exists)$' }
if ($failed) {
    Write-Host "Failures:"
    $failed | Format-Table -AutoSize
}
