# Retry failed PZDB downloads from download_log.csv
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$manifest = Import-Csv (Join-Path $Root "data\raw\pzdb\manifest_pilot.csv")
$headers = @{ "User-Agent" = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EagleGIS/1.0" }
$results = @()

foreach ($m in $manifest) {
    $dest = Join-Path $Root ($m.rel_path -replace '/', '\')
    if ((Test-Path $dest) -and ((Get-Item $dest).Length -gt 5000)) { continue }

    $ok = $false
    foreach ($attempt in 1..4) {
        try {
            if (Get-Command curl.exe -ErrorAction SilentlyContinue) {
                $args = @("-fsSL", "-A", $headers["User-Agent"], "-o", $dest, $m.source_url)
                & curl.exe @args
                if ($LASTEXITCODE -eq 0 -and (Test-Path $dest) -and ((Get-Item $dest).Length -gt 1000)) { $ok = $true; break }
            } else {
                Invoke-WebRequest -Uri $m.source_url -OutFile $dest -UseBasicParsing -Headers $headers -TimeoutSec 120
                if ((Get-Item $dest).Length -gt 1000) { $ok = $true; break }
            }
        } catch {
            Start-Sleep -Seconds (2 * $attempt)
        }
    }
    $status = if ($ok) { 'ok' } else { 'fail' }
    $results += [PSCustomObject]@{ file = $m.canonical_name; status = $status }
    Write-Host "$status $($m.canonical_name)"
    Start-Sleep -Milliseconds 800
}

$results | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $Root "data\raw\pzdb\retry_log.csv")
$results | Group-Object status | Format-Table Name, Count
