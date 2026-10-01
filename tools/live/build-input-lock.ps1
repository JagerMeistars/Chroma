$ErrorActionPreference='Stop'
$taskPrismRoot=Join-Path $env:APPDATA 'PrismLauncher'
$taskJavaRoot="$taskPrismRoot/java/java-runtime-epsilon/bin"
$taskClientJar="$taskPrismRoot/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar"
$taskLibraryJars=Get-ChildItem -LiteralPath "$taskPrismRoot/libraries" -Filter '*.jar' -Recurse | Where-Object {$_.FullName -notmatch '\\com\\mojang\\minecraft\\'} | ForEach-Object {$_.FullName.Replace('\','/')}
$taskClassPath=(@($taskClientJar)+@($taskLibraryJars)) -join ';'
$taskArgsPath=Join-Path $PSScriptRoot 'input-lock-javac.args'
@('--release','17','-classpath',('"'+$taskClassPath+'"'),('"'+(Join-Path $PSScriptRoot 'ChromaLiveInputLock.java').Replace('\','/')+'"')) | Set-Content -LiteralPath $taskArgsPath -Encoding utf8
& "$taskJavaRoot/javac.exe" "@$taskArgsPath"
if($LASTEXITCODE -ne 0){throw "javac exit $LASTEXITCODE"}
$taskManifest=Join-Path $PSScriptRoot 'input-lock-manifest.mf'
"Manifest-Version: 1.0`nAgent-Class: ChromaLiveInputLock`n`n" | Set-Content -LiteralPath $taskManifest -Encoding ascii
& "$taskJavaRoot/jar.exe" cfm (Join-Path $PSScriptRoot 'chroma-live-input-lock.jar') $taskManifest -C $PSScriptRoot 'ChromaLiveInputLock.class' -C $PSScriptRoot 'ChromaLiveInputLock$InputLockScreen.class'
if($LASTEXITCODE -ne 0){throw "jar exit $LASTEXITCODE"}
Write-Output 'Built isolated Chroma input lock; no launch or attach performed.'
