# Rasterises every SVG in a folder to PNG (same name, in the parent folder) with headless Chrome.
param([string]$Src, [string]$Dest)
$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (-not (Test-Path $chrome)) { $chrome = 'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe' }
New-Item -ItemType Directory -Force $Dest | Out-Null
foreach ($f in Get-ChildItem $Src -Filter *.svg) {
  $x = [xml](Get-Content $f.FullName -Raw)
  $w = [int]$x.svg.width; $h = [int]$x.svg.height
  # render at 2x for print-friendly pixels
  $html = Join-Path $env:TEMP ("galley_" + $f.BaseName + ".html")
  "<html><body style='margin:0;background:transparent'><img src='file:///$($f.FullName -replace '\\','/')' style='width:$($w)px;height:$($h)px;display:block'></body></html>" | Set-Content $html -Encoding UTF8
  $out = Join-Path $Dest ($f.BaseName + '.png')
  & $chrome --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=2 --default-background-color=00000000 "--window-size=$w,$h" "--screenshot=$out" "file:///$($html -replace '\\','/')" 2>$null | Out-Null
  "$out"
}
