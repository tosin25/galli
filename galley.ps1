<#
  Galley - manuscript in, book out.

  .\galley.ps1 ingest   -Manuscript samples\plants_chapter.docx      # .docx -> work\content.json (+ media, ingest_report.txt)
  .\galley.ps1 build    -Style bright                                # one chapter in one style -> out\bright\
  .\galley.ps1 variants [-Styles bright,classic,modern]              # same chapter in every style + QA + out\report.md
  .\galley.ps1 check                                                 # re-run QA + export on the document open in InDesign
  .\galley.ps1 ui                                                    # local web UI on http://localhost:8765
  .\galley.ps1 copilot                                               # copilot window docked beside InDesign

  Needs Adobe InDesign (2022 or later) on Windows; it is driven through COM. Python 3 for ingest and the UI.
#>
param(
  [Parameter(Position = 0)][ValidateSet('ingest', 'build', 'variants', 'check', 'ui', 'copilot', 'all')][string]$Command = 'all',
  [string]$Manuscript = '',
  [string]$Style = 'bright',
  [string[]]$Styles = @(),
  [string]$Content = '',
  [string]$Out = '',
  [switch]$KeepOpen
)
$ErrorActionPreference = 'Stop'
$G = $PSScriptRoot
if (-not $Content) { $Content = Join-Path $G 'work\content.json' }
if (-not $Out) { $Out = Join-Path $G 'out' }
$Styles = @($Styles | ForEach-Object { $_ -split ',' } | Where-Object { $_ })  # "-Styles a,b" also arrives as one string via -File
$JS = 1246973031  # ScriptLanguage.JAVASCRIPT

function Get-InDesign { New-Object -ComObject InDesign.Application }

function Invoke-Jsx($app, [string]$script, [hashtable]$vars) {
  foreach ($k in $vars.Keys) { $app.ScriptArgs.SetValue($k, [string]$vars[$k]) }
  $result = Join-Path $env:TEMP 'galley_result.txt'
  Remove-Item $result -ErrorAction SilentlyContinue
  $app.ScriptArgs.SetValue('galley_target', $script)
  $app.ScriptArgs.SetValue('galley_result', $result)
  $app.ScriptArgs.SetValue('galley_undo', '')  # shared with the copilot: never inherit its undo name
  try { [void]$app.DoScript((Join-Path $G 'indesign\run.jsx'), $JS) } catch { return "ERROR: $($_.Exception.Message)" }
  if (Test-Path $result) { Get-Content $result -Raw } else { 'ERROR: no result written' }
}

function Invoke-Ingest {
  if (-not $Manuscript) { $Manuscript = Join-Path $G 'samples\plants_chapter.docx' }
  if (-not (Test-Path $Manuscript)) { & python (Join-Path $G 'samples\make_sample.py') | Out-Null }
  & python (Join-Path $G 'ingest\ingest.py') $Manuscript (Split-Path $Content -Parent)
  if ($LASTEXITCODE) { throw 'ingest failed' }
}

function New-ContactSheet([string]$dir, [string]$title) {
  # pages laid out as reader spreads: page 1 alone on the right, then 2-3, 4-5 ...
  Add-Type -AssemblyName System.Drawing
  $files = Get-ChildItem $dir -Filter 'p*.png' | Where-Object { $_.BaseName -match '^p\d+$' } | Sort-Object Name
  if (-not $files) { return }
  $img0 = [System.Drawing.Image]::FromFile($files[0].FullName); $w = $img0.Width; $h = $img0.Height; $img0.Dispose()
  $spreads = @(, @($null, $files[0]))
  for ($i = 1; $i -lt $files.Count; $i += 2) { $spreads += , @($files[$i], $(if ($i + 1 -lt $files.Count) { $files[$i + 1] } else { $null })) }
  $cols = [Math]::Min(3, $spreads.Count); $rows = [Math]::Ceiling($spreads.Count / $cols)
  $gap = 24; $lab = 30; $sw = 2 * $w
  $bmp = New-Object System.Drawing.Bitmap(($cols * ($sw + $gap) + $gap), ($rows * ($h + $gap) + $gap + $lab + 10))
  $g = [System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::FromArgb(58, 61, 66))
  $g.InterpolationMode = 'HighQualityBicubic'
  $font = New-Object System.Drawing.Font('Segoe UI', 14, [System.Drawing.FontStyle]::Bold)
  $g.DrawString($title, $font, [System.Drawing.Brushes]::White, $gap, 10)
  for ($s = 0; $s -lt $spreads.Count; $s++) {
    $x = $gap + ($s % $cols) * ($sw + $gap); $y = $lab + 10 + $gap + [Math]::Floor($s / $cols) * ($h + $gap)
    for ($side = 0; $side -lt 2; $side++) {
      $f = $spreads[$s][$side]; if (-not $f) { continue }
      $im = [System.Drawing.Image]::FromFile($f.FullName); $g.DrawImage($im, $x + $side * $w, $y, $w, $h); $im.Dispose()
    }
  }
  $bmp.Save((Join-Path (Split-Path $dir -Parent) 'contact_sheet.png'), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
}

function Rename-Previews([string]$dir) {
  # InDesign writes page.png, page2.png, page3.png ... -> p01.png, p02.png ...
  foreach ($f in Get-ChildItem $dir -Filter 'page*.png') {
    $n = $f.BaseName.Substring(4); if ($n -eq '') { $n = 1 }
    Move-Item $f.FullName (Join-Path $dir ('p{0:D2}.png' -f [int]$n)) -Force
  }
}

function Invoke-Build([string]$styleId, $app) {
  $styleFile = Join-Path $G "style\$styleId.json"
  if (-not (Test-Path $styleFile)) { throw "no style spec $styleFile" }
  $dir = Join-Path $Out $styleId
  New-Item -ItemType Directory -Force $dir | Out-Null
  Get-ChildItem $dir -Recurse -Include *.png, *.pdf, qa.*, build_log.txt -ErrorAction SilentlyContinue | Remove-Item -Force
  foreach ($d in @($app.Documents)) { if ($d.Name -eq "$($styleId)_chapter.indd" -or $d.Name -like 'Untitled*') { $d.Close(1852776480) } }  # SaveOptions.NO
  $t0 = Get-Date
  $r = Invoke-Jsx $app (Join-Path $G 'indesign\build_chapter.jsx') @{ galley_content = $Content; galley_style = $styleFile; galley_art = (Join-Path $G 'art'); galley_out = $dir }
  if ($r -ne 'OK') { Write-Host "[$styleId] build: $r" -ForegroundColor Red; return $null }
  $r = Invoke-Jsx $app (Join-Path $G 'indesign\qa_export.jsx') @{ galley_doc = ''; galley_out = $dir; galley_export = '1' }
  if ($r -ne 'OK') { Write-Host "[$styleId] qa/export: $r" -ForegroundColor Red; return $null }
  Rename-Previews (Join-Path $dir 'previews')
  $spec = Get-Content $styleFile -Raw | ConvertFrom-Json
  New-ContactSheet (Join-Path $dir 'previews') "$($spec.name)  -  $($spec.trim.width) x $($spec.trim.height) mm"
  if (-not $KeepOpen) { $app.ActiveDocument.Close(1852776480) }
  $qa = Get-Content (Join-Path $dir 'qa.json') -Raw | ConvertFrom-Json
  $secs = [int]((Get-Date) - $t0).TotalSeconds
  $col = if ($qa.passed) { 'Green' } else { 'Yellow' }
  Write-Host ("[{0}] {1} pages, {2} errors, {3} warnings, {4}s" -f $styleId, $qa.pages, $qa.errors.Count, $qa.warnings.Count, $secs) -ForegroundColor $col
  [pscustomobject]@{ id = $styleId; name = $spec.name; description = $spec.description; trim = "$($spec.trim.width) x $($spec.trim.height) mm"; qa = $qa; seconds = $secs }
}

function Write-Report($results) {
  $c = Get-Content $Content -Raw | ConvertFrom-Json
  $L = @("# Galley variants: $($c.meta.chapter_title)", '', "Source: ``$($c.meta.source)`` - built $(Get-Date -Format 'yyyy-MM-dd HH:mm')", '',
    '| Variant | Trim | Pages | QA | Errors | Warnings | Build time |', '|---|---|---|---|---|---|---|')
  foreach ($r in $results) {
    $L += "| **$($r.name)** (``$($r.id)``) | $($r.trim) | $($r.qa.pages) | $(if ($r.qa.passed) { 'PASS' } else { 'CHECK' }) | $($r.qa.errors.Count) | $($r.qa.warnings.Count) | $($r.seconds) s |"
  }
  foreach ($r in $results) {
    $L += ''; $L += "## $($r.name)"; $L += ''; $L += $r.description; $L += ''
    $L += "Files: ``$($r.id)/$($r.id)_chapter.indd``, ``$($r.id)/$($r.id)_chapter.pdf``, ``$($r.id)/contact_sheet.png``, ``$($r.id)/previews/``"; $L += ''
    $ck = $r.qa.checks; $L += "Checks - overset: $($ck.overset), split boxes: $($ck.split_boxes), stranded headings: $($ck.stranded_headings), off page: $($ck.off_page), links: $($ck.links), empty pages: $($ck.empty_pages)"
    foreach ($e in $r.qa.errors) { $L += "- ERROR p$($e.page): $($e.msg)" }
    foreach ($w in $r.qa.warnings) { $L += "- note p$($w.page): $($w.msg)" }
    $log = Join-Path $Out "$($r.id)\build_log.txt"
    if (Test-Path $log) { $fx = @(Get-Content $log | Where-Object { $_ -match '^(moved|figure|opener|exercise|illustration)' }); if ($fx) { $L += ''; $L += 'Automatic fixes:'; $L += ($fx | ForEach-Object { "- $_" }) } }
  }
  $L | Set-Content (Join-Path $Out 'report.md') -Encoding UTF8
  ($results | ForEach-Object { [pscustomobject]@{ id = $_.id; name = $_.name; description = $_.description; trim = $_.trim; pages = $_.qa.pages; passed = $_.qa.passed; errors = $_.qa.errors; warnings = $_.qa.warnings; seconds = $_.seconds } }) |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $Out 'variants.json') -Encoding UTF8
  Write-Host "report: $(Join-Path $Out 'report.md')"
}

switch ($Command) {
  'ingest' { Invoke-Ingest }
  'build' { $app = Get-InDesign; $r = Invoke-Build $Style $app; if ($r) { Write-Report @($r) } }
  'variants' {
    if (-not (Test-Path $Content)) { Invoke-Ingest }
    if (-not $Styles) { $Styles = Get-ChildItem (Join-Path $G 'style') -Filter *.json | ForEach-Object { $_.BaseName } }
    $app = Get-InDesign; $res = @()
    foreach ($s in $Styles) { $r = Invoke-Build $s $app; if ($r) { $res += $r } }
    Write-Report $res
  }
  'all' {
    Invoke-Ingest
    $Styles = Get-ChildItem (Join-Path $G 'style') -Filter *.json | ForEach-Object { $_.BaseName }
    $app = Get-InDesign; $res = @(); foreach ($s in $Styles) { $r = Invoke-Build $s $app; if ($r) { $res += $r } }; Write-Report $res
  }
  'check' {
    $app = Get-InDesign; $doc = $app.ActiveDocument; $dir = Split-Path $doc.FullName -Parent
    $r = Invoke-Jsx $app (Join-Path $G 'indesign\qa_export.jsx') @{ galley_doc = ''; galley_out = $dir; galley_export = '1' }
    Rename-Previews (Join-Path $dir 'previews'); Get-Content (Join-Path $dir 'qa.txt')
  }
  'ui' { & python (Join-Path $G 'ui\server.py') }
  'copilot' {
    # 1. local server (reused if it is already running)
    $url = 'http://127.0.0.1:8765'  # not 'localhost': Windows PowerShell tries IPv6 first and stalls
    $up = $false; try { $up = (Invoke-WebRequest "$url/api/c/state" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {}
    if (-not $up) {
      # the real Python, not the Microsoft Store alias that 'python' can resolve to
      $py = (Get-Command python -All -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1).Source
      if (-not $py) { $py = 'python' }
      Start-Process $py -ArgumentList "`"$(Join-Path $G 'ui\server.py')`" --no-browser" -WindowStyle Minimized
      for ($i = 0; $i -lt 120 -and -not $up; $i++) { Start-Sleep -Milliseconds 250; try { $up = (Invoke-WebRequest "$url/api/c/state" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch {} }
      if (-not $up) { throw 'The Galley server did not start. Run: python ui\server.py' }
    }
    # 2. its own app window, docked at the right edge of the screen
    Add-Type -AssemblyName System.Windows.Forms
    $wa = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea; $w = 440
    $edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
      "$env:ProgramFiles\Google\Chrome\Application\chrome.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $edge) { Start-Process "$url/copilot"; return }
    $browserProfile = Join-Path $env:LOCALAPPDATA 'Galleyrowser'
    Start-Process $edge -ArgumentList "--app=$url/copilot", "--user-data-dir=`"$browserProfile`"", "--window-size=$w,$($wa.Height)", "--window-position=$($wa.Right - $w),$($wa.Top)", '--no-first-run'
    # 3. keep it above InDesign (Windows: topmost flag on the window titled "Galley Copilot")
    Add-Type @'
using System; using System.Runtime.InteropServices;
public static class GalleyWin { [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags); }
'@
    for ($i = 0; $i -lt 40; $i++) {
      Start-Sleep -Milliseconds 250
      $p = Get-Process | Where-Object { $_.MainWindowTitle -like 'Galley Copilot*' } | Select-Object -First 1
      if ($p) { [void][GalleyWin]::SetWindowPos($p.MainWindowHandle, [IntPtr](-1), $wa.Right - $w, $wa.Top, $w, $wa.Height, 0x0040); Write-Host 'Galley Copilot is open (docked right, pinned on top).'; break }
    }
  }
}
