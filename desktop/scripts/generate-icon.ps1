Add-Type -AssemblyName System.Drawing

$size = 512
$bitmap = [System.Drawing.Bitmap]::new($size, $size)
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$graphics.Clear([System.Drawing.Color]::FromArgb(244, 241, 231))

$green = [System.Drawing.Color]::FromArgb(29, 111, 73)
$outerPen = [System.Drawing.Pen]::new($green, 18)
$innerPen = [System.Drawing.Pen]::new($green, 13)
$signalPen = [System.Drawing.Pen]::new($green, 14)
foreach ($pen in @($outerPen, $innerPen, $signalPen)) {
    $pen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $pen.LineJoin = [System.Drawing.Drawing2D.LineJoin]::Round
}

$graphics.DrawArc($outerPen, 86, 82, 204, 342, 90, 180)
$graphics.DrawLine($outerPen, 188, 82, 238, 82)
$graphics.DrawLine($outerPen, 188, 424, 238, 424)
$graphics.DrawArc($innerPen, 142, 144, 112, 220, 90, 180)
$graphics.DrawLine($innerPen, 198, 144, 238, 144)
$graphics.DrawLine($innerPen, 198, 364, 238, 364)
$graphics.DrawLine($signalPen, 294, 310, 294, 202)
$graphics.DrawLine($signalPen, 356, 346, 356, 166)
$graphics.DrawLine($signalPen, 418, 292, 418, 220)
$graphics.FillEllipse([System.Drawing.SolidBrush]::new($green), 282, 346, 24, 24)

$buildDirectory = Join-Path $PSScriptRoot '..\build'
[System.IO.Directory]::CreateDirectory($buildDirectory) | Out-Null
$outputPath = Join-Path $buildDirectory 'icon.png'
$bitmap.Save($outputPath, [System.Drawing.Imaging.ImageFormat]::Png)

$outerPen.Dispose()
$innerPen.Dispose()
$signalPen.Dispose()
$graphics.Dispose()
$bitmap.Dispose()
Write-Output "SCUT_ICON_GENERATED $outputPath"
