# Makes JPEG images for the pitch page from the variant previews: each look's opener page and its first spread.
param([string]$Out = (Join-Path (Split-Path $PSScriptRoot -Parent) 'out'), [string]$Dest = (Join-Path (Split-Path $PSScriptRoot -Parent) 'pitch\img'))
Add-Type -AssemblyName System.Drawing
New-Item -ItemType Directory -Force $Dest | Out-Null
$enc = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object { $_.MimeType -eq 'image/jpeg' }
$ep = New-Object System.Drawing.Imaging.EncoderParameters(1)
$ep.Param[0] = New-Object System.Drawing.Imaging.EncoderParameter([System.Drawing.Imaging.Encoder]::Quality, [long]86)
function Save-Jpeg($files, $path, $height) {
  $imgs = $files | ForEach-Object { [System.Drawing.Image]::FromFile($_) }
  $w = 0; foreach ($i in $imgs) { $w += [int]($i.Width * $height / $i.Height) }
  $bmp = New-Object System.Drawing.Bitmap($w, $height); $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.InterpolationMode = 'HighQualityBicubic'; $g.Clear([System.Drawing.Color]::White); $x = 0
  foreach ($i in $imgs) { $iw = [int]($i.Width * $height / $i.Height); $g.DrawImage($i, $x, 0, $iw, $height); $x += $iw; $i.Dispose() }
  if ($files.Count -eq 2) { $pen = New-Object System.Drawing.Pen([System.Drawing.Color]::FromArgb(40, 0, 0, 0), 2); $g.DrawLine($pen, $x / 2, 0, $x / 2, $height) }
  $bmp.Save($path, $enc, $ep); $g.Dispose(); $bmp.Dispose()
}
foreach ($d in Get-ChildItem $Out -Directory) {
  $pv = Join-Path $d.FullName 'previews'; if (-not (Test-Path "$pv\p01.png")) { continue }
  Save-Jpeg @("$pv\p01.png") (Join-Path $Dest "$($d.Name)_opener.jpg") 782
  if (Test-Path "$pv\p03.png") { Save-Jpeg @("$pv\p02.png", "$pv\p03.png") (Join-Path $Dest "$($d.Name)_spread.jpg") 782 }
  if (Test-Path "$pv\p05.png") { Save-Jpeg @("$pv\p04.png", "$pv\p05.png") (Join-Path $Dest "$($d.Name)_spread2.jpg") 782 }
}
Get-ChildItem $Dest | Select-Object Name, Length
