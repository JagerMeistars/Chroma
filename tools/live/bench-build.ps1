$ErrorActionPreference='Stop'
$taskPrismRoot='C:/Users/konst/AppData/Roaming/PrismLauncher'
$taskJavaRoot="$taskPrismRoot/java/java-runtime-epsilon/bin"
$taskClientJar="$taskPrismRoot/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar"
$taskLibraryJars=Get-ChildItem -LiteralPath "$taskPrismRoot/libraries" -Filter '*.jar' -Recurse | Where-Object {$_.FullName -notmatch '\\com\\mojang\\minecraft\\'} | ForEach-Object {$_.FullName.Replace('\','/')}
$taskClassPath=(@($taskClientJar)+@($taskLibraryJars)) -join ';'
$taskArgsPath=Join-Path $PSScriptRoot 'bench-javac.args'
@('--release','17','-classpath',('"'+$taskClassPath+'"'),('"'+(Join-Path $PSScriptRoot 'bench_ChromaBenchmark.java').Replace('\','/')+'"')) | Set-Content -LiteralPath $taskArgsPath -Encoding utf8
& "$taskJavaRoot/javac.exe" "@$taskArgsPath"
if($LASTEXITCODE -ne 0){throw "javac exit $LASTEXITCODE"}
$taskManifest=Join-Path $PSScriptRoot 'bench-manifest.mf'
"Manifest-Version: 1.0`nAgent-Class: bench_ChromaBenchmark`n`n" | Set-Content -LiteralPath $taskManifest -Encoding ascii
$taskClasses=Get-ChildItem -LiteralPath $PSScriptRoot -Filter 'bench_ChromaBenchmark*.class' | ForEach-Object {$_.Name}
$taskJarArgs=@('cfm',(Join-Path $PSScriptRoot 'bench-chroma.jar'),$taskManifest)
foreach($taskClass in $taskClasses){$taskJarArgs+=@('-C',$PSScriptRoot,$taskClass)}
& "$taskJavaRoot/jar.exe" @taskJarArgs
if($LASTEXITCODE -ne 0){throw "jar exit $LASTEXITCODE"}
Write-Output 'Built isolated Chroma benchmark agent; no launch or attach performed.'
