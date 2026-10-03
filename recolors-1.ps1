# ============================================================
#  Brujula Electoral - Recoloreo SEGURO (UTF-8 bulletproof)
#  Revertir:  .\recolor.ps1 -Revert
#  Aplicar:   .\recolor.ps1 -Apply -Push
# ============================================================
param([switch]$Apply, [switch]$Push, [switch]$Revert)
$ErrorActionPreference = "Stop"
$repo = "C:\RICHARD\RB\2026\brujula-panel-web"
Set-Location $repo
$Tema = "Medianoche"

$files = Get-ChildItem $repo -Recurse -Include *.html,*.css,*.js |
  Where-Object { $_.FullName -notmatch '\\\.git\\' -and $_.FullName -notmatch '\\_backup_' }

if ($Revert) {
  $last = Get-ChildItem $repo -Directory -Filter "_backup_colores_*" | Sort-Object Name -Descending | Select-Object -First 1
  if (-not $last) { Write-Host "No hay backups." -ForegroundColor Yellow; return }
  Get-ChildItem $last.FullName -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($last.FullName.Length).TrimStart('\')
    Copy-Item $_.FullName (Join-Path $repo $rel) -Force
  }
  Write-Host "Restaurado desde $($last.Name)" -ForegroundColor Green; return
}

$Map = [ordered]@{
  "#2C3E2E"="#0F1C2E"; "#1f2b22"="#0F1C2E"; "#1F2E20"="#0A1626"
  "#26352a"="#13273D"; "#34463a"="#1E3A57"; "#3A5A3F"="#1E3A57"; "#233145"="#1C2A3F"
  "#eef1f5"="#F4F6F9"; "#f5f3ec"="#F4F6F9"; "#F9F8F4"="#F4F6F9"; "#eef0ea"="#F4F6F9"
  "#dde3ec"="#E2E8F0"; "#e3dfd3"="#E2E8F0"; "#E8E4DB"="#E2E8F0"; "#c4cedb"="#CBD5E1"
  "#6a7688"="#6B7A90"; "#667067"="#6B7A90"; "#7A8A7B"="#6B7A90"; "#93a0b2"="#94A3B8"
  "#C9A961"="#C8A560"; "#c8a25a"="#C8A560"; "#A88A4F"="#A98841"; "#9c7a38"="#A98841"
  "#f5f3ed"="#F4EDDA"; "#f3ead6"="#F4EDDA"
  "#2f7d5b"="#2E9E7B"; "#e7f1ea"="#E4F3EC"; "#a4503c"="#C0485A"; "#f3e4df"="#F6E3E6"
  "#b5852a"="#BE8A2C"; "#f7efd9"="#F7EFDA"
  "#6B8E23"="#5E8ABF"
}

if (-not $Apply) {
  Write-Host "`n>>> PREVISUALIZACION. Para aplicar:" -ForegroundColor Yellow
  Write-Host "    .\recolor.ps1 -Apply -Push`n" -ForegroundColor Yellow
  return
}

$bk = Join-Path $repo ("_backup_colores_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
foreach ($f in $files) {
  $dest = Join-Path $bk ($f.FullName.Substring($repo.Length).TrimStart('\'))
  New-Item -ItemType Directory -Path (Split-Path $dest) -Force | Out-Null
  Copy-Item $f.FullName $dest
}
Write-Host "Backup: $bk" -ForegroundColor Green

$utf8NoBOM = New-Object System.Text.UTF8Encoding($false)
$mod = 0
foreach ($f in $files) {
  $txt = Get-Content $f.FullName -Raw -Encoding UTF8
  $orig = $txt
  
  foreach ($k in $Map.Keys) { 
    $txt = $txt -replace [regex]::Escape($k), $Map[$k]
  }
  
  if ($txt -ne $orig) { 
    [System.IO.File]::WriteAllText($f.FullName, $txt, $utf8NoBOM)
    $mod++
    Write-Host "  recoloreado: $($f.Name)" -ForegroundColor Green 
  }
}
Write-Host "`nArchivos modificados: $mod" -ForegroundColor Cyan

if ($Push) {
  git add -A
  git commit -m "Tema ${Tema}: recoloreo elegante navy + champan (UTF-8 seguro)"
  git push
  Write-Host "Push hecho. GitHub Pages reconstruye en ~1-2 min." -ForegroundColor Green
}