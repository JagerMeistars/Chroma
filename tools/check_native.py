"""Offline validation with the installed Minecraft compiler and local GL driver.

Requires PrismLauncher with Java and Minecraft 26.3 already installed.
Does not start or alter the game. Nothing is downloaded.
"""
from pathlib import Path
import argparse
import json
import os
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prism', type=Path, default=Path(os.environ['APPDATA']) / 'PrismLauncher')
    parser.add_argument('--pack', type=Path, help='Validate an existing variant ZIP instead of the source assets')
    args = parser.parse_args()
    prism = args.prism
    java = prism / 'java/java-runtime-epsilon/bin'
    jar = prism / 'libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar'
    meta = json.loads((prism / 'meta/net.minecraft/26.3.json').read_text(encoding='utf-8'))
    report = ROOT / 'audit'
    report.mkdir(exist_ok=True)
    classes = report / 'classes'
    classes.mkdir(exist_ok=True)
    libraries = [jar, classes]
    for lib in meta['libraries']:
        parts = lib['name'].split(':')
        group, artifact, version = parts[:3]
        name = artifact + '-' + version + ('' if len(parts) == 3 else '-' + parts[3]) + '.jar'
        path = prism / 'libraries' / group.replace('.', '/') / artifact / version / name
        if path.exists():
            libraries.append(path)
    for path in (prism / 'libraries/org/lwjgl').rglob('*3.4.3*.jar'):
        if not any(t in path.name for t in ('linux', 'macos', 'arm64', 'x86')):
            libraries.append(path)
    cp = ';'.join(str(p) for p in dict.fromkeys(libraries))
    sources = [ROOT / 'tools' / (s + '.java') for s in ('ValidatePack', 'ReproduceClientShaders', 'CheckExamples')]
    subprocess.run([str(java / 'javac.exe'), '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes), *map(str, sources)], check=True)
    # The installed older GLFW runtime provides a hidden OpenGL context. Keep it
    # separate from the game's 3.4.3 SDL runtime to avoid mixing LWJGL versions.
    gpu_libraries = [classes]
    for artifact in ('lwjgl', 'lwjgl-natives-windows', 'lwjgl-opengl', 'lwjgl-opengl-natives-windows', 'lwjgl-glfw', 'lwjgl-glfw-natives-windows'):
        gpu_libraries.append(prism / 'libraries/org/lwjgl' / artifact / '3.4.1' / (artifact + '-3.4.1.jar'))
    gpu_cp = ';'.join(map(str, gpu_libraries))
    subprocess.run([str(java / 'javac.exe'), '-encoding', 'UTF-8', '-cp', gpu_cp, '-d', str(classes), str(ROOT / 'tools/CheckDriver.java')], check=True)
    archive = args.pack.resolve() if args.pack else report / 'candidate.zip'
    if not args.pack:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(ROOT / 'pack.mcmeta', 'pack.mcmeta')
            for p in sorted((ROOT / 'assets').rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(ROOT).as_posix())
    stages = report / 'roundtrip'
    # Remove only this check's prior generated shader files to avoid stale success.
    if stages.exists():
        for p in stages.iterdir():
            if p.suffix in ('.vsh', '.fsh'):
                p.unlink()
    for name, parameters in (
        ('ValidatePack', [archive, jar]),
        ('ReproduceClientShaders', [archive, jar, stages]),
        ('CheckDriver', [stages]),
        ('CheckExamples', [ROOT, report / 'examples-validation.json']),
    ):
        argfile = report / (name + '.args')
        run_cp = gpu_cp if name == 'CheckDriver' else cp
        argfile.write_text('--enable-native-access=ALL-UNNAMED\n-Xmx2G\n-Dorg.lwjgl.system.stackSize=1024\n-cp\n"' + run_cp.replace('\\', '/') + '"\n' + name + '\n', encoding='utf-8')
        result = subprocess.run([str(java / 'java.exe'), '@' + str(argfile), *map(str, parameters)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = result.stdout.decode('utf-8', errors='replace')
        (report / (name + '.log')).write_text(log, encoding='utf-8')
        print(log[-6000:])
        result.check_returncode()


if __name__ == '__main__':
    main()
