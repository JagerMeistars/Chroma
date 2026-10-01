$ErrorActionPreference='Stop'
$taskJavaRoot=Join-Path $env:APPDATA 'PrismLauncher/java/java-runtime-epsilon/bin'
& "$taskJavaRoot/javac.exe" --release 17 (Join-Path $PSScriptRoot 'ChromaLiveProbe.java') (Join-Path $PSScriptRoot 'AttachChromaProbe.java')
if($LASTEXITCODE -ne 0){throw "javac exit $LASTEXITCODE"}
$taskManifest=Join-Path $PSScriptRoot 'agent-manifest.mf'
"Manifest-Version: 1.0`nAgent-Class: ChromaLiveProbe`n`n" | Set-Content -LiteralPath $taskManifest -Encoding ascii
& "$taskJavaRoot/jar.exe" cfm (Join-Path $PSScriptRoot 'chroma-live-probe.jar') $taskManifest -C $PSScriptRoot 'ChromaLiveProbe.class'
if($LASTEXITCODE -ne 0){throw "jar exit $LASTEXITCODE"}
Write-Output 'Built direct API agent only; no launch or attach performed.'
