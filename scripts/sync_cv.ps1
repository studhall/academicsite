$source = 'C:\Users\David\University of Oregon Dropbox\David Hall\Apps\Overleaf\Job Market\Hall_CV_Academic_LaTeX_Native.tex'
$siteRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$destination = Join-Path $siteRoot 'cv\Hall_CV_Current.pdf'
$buildDir = Join-Path $siteRoot '.cv-build'

if (-not (Test-Path -LiteralPath $source)) {
  throw "Canonical CV source not found: $source"
}

New-Item -ItemType Directory -Force $buildDir | Out-Null
Copy-Item -LiteralPath $source -Destination (Join-Path $buildDir 'Hall_CV_Academic_LaTeX_Native.tex') -Force

Push-Location $buildDir
try {
  & pdflatex -interaction=nonstopmode -halt-on-error Hall_CV_Academic_LaTeX_Native.tex | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "CV compilation failed." }
  & pdflatex -interaction=nonstopmode -halt-on-error Hall_CV_Academic_LaTeX_Native.tex | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "CV compilation failed on the second pass." }
} finally {
  Pop-Location
}

$compiled = Join-Path $buildDir 'Hall_CV_Academic_LaTeX_Native.pdf'
Copy-Item -LiteralPath $compiled -Destination $destination -Force
Write-Host "Compiled and synced CV from the canonical Overleaf source."
