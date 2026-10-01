"""Compile and fake-test the audit agent only. Never attaches or initializes a GPU."""
from pathlib import Path
import json
import os
import subprocess
import zipfile

root = Path(__file__).resolve().parent
prism = Path(os.environ['APPDATA']) / 'PrismLauncher'
java = prism / 'java/java-runtime-epsilon/bin'
client = prism / 'libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar'
meta = json.loads((prism / 'meta/net.minecraft/26.3.json').read_text(encoding='utf-8'))
classes = root / 'gpu-timing-classes'
classes.mkdir(exist_ok=True)
libraries = [classes, client]
for lib in meta['libraries']:
    group, artifact, version, *classifier = lib['name'].split(':')
    name = artifact + '-' + version + (('-' + classifier[0]) if classifier else '') + '.jar'
    path = prism / 'libraries' / group.replace('.', '/') / artifact / version / name
    if path.exists():
        libraries.append(path)
for path in (prism / 'libraries/org/lwjgl').rglob('*3.4.3.jar'):
    if 'natives-' not in path.name:
        libraries.append(path)
cp = ';'.join(map(str, libraries))
sources = [root / 'gpu_ChromaPassTiming.java', root / 'gpu_ChromaPassTimingTest.java']
subprocess.run([str(java / 'javac.exe'), '--release', '17', '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes), *map(str, sources)], check=True)
subprocess.run([str(java / 'java.exe'), '-cp', cp, 'gpu_ChromaPassTimingTest'], check=True)
with zipfile.ZipFile(root / 'gpu-chroma-pass-timing.jar', 'w', zipfile.ZIP_DEFLATED) as archive:
    archive.writestr('META-INF/MANIFEST.MF', 'Manifest-Version: 1.0\nAgent-Class: gpu_ChromaPassTiming\n\n')
    for path in sorted(classes.glob('gpu_ChromaPassTiming*.class')):
        if not path.name.startswith('gpu_ChromaPassTimingTest'):
            archive.write(path, path.name)
print('Built gpu-chroma-pass-timing.jar; CPU fake tests only, no attach/GPU/game launch.')
