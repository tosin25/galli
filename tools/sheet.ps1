# Puts every page PNG in a folder (page.png, page2.png ... or p01.png ...) on one sheet, in page order.
param([Parameter(Mandatory)][string]$Dir, [int]$Cols = 6, [double]$Scale = 0.5, [string]$Out = '')
Add-Type -AssemblyName System.Drawing
$files = Get-ChildItem $Dir -Filter *.png | Where-Object { $_.BaseName -match '^(page|p)(\d*)$' } |
  Sort-Object { $n = ($_.BaseName -replace '^(page|p)', ''); if ($n -eq '') { 1 } else { [int]$n } }
if (-not $files) { throw "no page PNGs in $Dir" }
$i0 = [System.Drawing.Image]::FromFile($files[0].FullName)
$w = [int]($i0.Width * $Scale); $h = [int]($i0.Height * $Scale); $i0.Dispose()
$rows = [int][math]::Ceiling($files.Count / $Cols); $gap = 10
$bmp = New-Object System.Drawing.Bitmap([int]($Cols * ($w + $gap) + $gap), [int]($rows * ($h + $gap) + $gap))
$g = [System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::DimGray); $g.InterpolationMode = 'HighQualityBicubic'
for ($k = 0; $k -lt $files.Count; $k++) {
  $im = [System.Drawing.Image]::FromFile($files[$k].FullName)
  $g.DrawImage($im, [int]($gap + ($k % $Cols) * ($w + $gap)), [int]($gap + [math]::Floor($k / $Cols) * ($h + $gap)), $w, $h); $im.Dispose()
}
if (-not $Out) { $Out = Join-Path $Dir 'sheet.png' }
$bmp.Save($Out); $g.Dispose(); $bmp.Dispose(); $Out
