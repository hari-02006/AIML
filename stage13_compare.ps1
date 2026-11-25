$activeRoot = 'C:\Users\kshir\.gemini\antigravity\scratch\SmartInventoryDemandPrediction'
$backupRoot = 'C:\Users\kshir\.gemini\antigravity\scratch\SmartInventoryDemandPrediction_Stage13_Backup'
$dirs = @('ml\inventory_decision\simulation','tests\simulation')
foreach ($rel in $dirs) {
    Write-Host "=== Comparing $rel ==="
    $actPath = Join-Path $activeRoot $rel
    $bakPath = Join-Path $backupRoot $rel
    if (-not (Test-Path $actPath)) { Write-Host "Active directory $actPath missing!"; continue }
    if (-not (Test-Path $bakPath)) { Write-Host "Backup directory $bakPath missing!"; continue }
    $actFiles = Get-ChildItem -Path $actPath -Recurse -File
    $bakFiles = Get-ChildItem -Path $bakPath -Recurse -File
    Write-Host "Active count:" $actFiles.Count
    Write-Host "Backup count:" $bakFiles.Count
    $actMap = @{}
    foreach ($f in $actFiles) {
        $relPath = $f.FullName.Substring($activeRoot.Length + 1)
        $hash = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash
        $actMap[$relPath] = @{Size=$f.Length; Hash=$hash}
    }
    $bakMap = @{}
    foreach ($f in $bakFiles) {
        $relPath = $f.FullName.Substring($backupRoot.Length + 1)
        $hash = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash
        $bakMap[$relPath] = @{Size=$f.Length; Hash=$hash}
    }
    $missing = @()
    $additional = @()
    $modified = @()
    foreach ($k in $actMap.Keys) {
        if (-not $bakMap.ContainsKey($k)) {
            $missing += $k
        } else {
            if ($actMap[$k].Hash -ne $bakMap[$k].Hash -or $actMap[$k].Size -ne $bakMap[$k].Size) {
                $modified += [pscustomobject]@{
                    Path = $k
                    ActiveSize = $actMap[$k].Size
                    ActiveHash = $actMap[$k].Hash
                    BackupSize = $bakMap[$k].Size
                    BackupHash = $bakMap[$k].Hash
                }
            }
        }
    }
    foreach ($k in $bakMap.Keys) {
        if (-not $actMap.ContainsKey($k)) { $additional += $k }
    }
    Write-Host "Missing in backup:"
    foreach ($m in $missing) { Write-Host $m }
    Write-Host "Additional in backup:"
    foreach ($a in $additional) { Write-Host $a }
    Write-Host "Modified files:"
    foreach ($m in $modified) {
        Write-Host "$($m.Path) | SizeActive=$($m.ActiveSize) SizeBackup=$($m.BackupSize) | HashActive=$($m.ActiveHash) | HashBackup=$($m.BackupHash)"
    }
}
