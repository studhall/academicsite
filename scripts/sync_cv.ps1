$source = 'C:\Users\David\OneDrive\Documents\Life\CVs\Hall_CV_Current.pdf'
$siteRoot = Resolve-Path (Join-Path $PSScriptRoot '..')
$destination = Join-Path $siteRoot 'cv\Hall_CV_Current.pdf'
Copy-Item -LiteralPath $source -Destination $destination -Force
$version = (Get-Item -LiteralPath $source).LastWriteTimeUtc.ToString('yyyyMMddHHmmss')
$cvQmd = @"
---
title: "Curriculum Vitae"
format:
  html:
    toc: false
---

::: {.cv-actions}
<a class="btn btn-primary btn-lg" href="cv/Hall_CV_Current.pdf?v=$version" download="Hall_CV_Current.pdf">Download CV as PDF</a>
:::

::: {.pdf-frame .cv-frame}
<iframe src="cv/Hall_CV_Current.pdf?v=$version" title="David Hall curriculum vitae PDF"></iframe>
:::

If the embedded PDF does not load in your browser, use the download button above.
"@
Set-Content -Path (Join-Path $siteRoot 'cv.qmd') -Value $cvQmd -Encoding UTF8
Write-Host "Synced CV from $source with cache key $version"
