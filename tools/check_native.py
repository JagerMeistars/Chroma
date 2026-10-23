"""Offline validation with the installed Minecraft compiler and local GL driver.

Requires PrismLauncher with Java and Minecraft 26.3 already installed.
Does not start or alter the game. Nothing is downloaded.
"""
from pathlib import Path
import argparse
import copy
import json
import os
import re
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def find_sodium_jar(prism, explicit=None):
    """Use the installed 26.3 adapter dependency, never download one."""
    candidates = [explicit] if explicit else sorted(
        (prism / 'instances/26.3/minecraft/mods').glob('sodium*.jar'))
    matches = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        with zipfile.ZipFile(candidate) as archive:
            if 'assets/sodium/shaders/include/globals.glsl' in archive.namelist():
                matches.append(candidate.resolve())
    if len(matches) != 1:
        raise ValueError('Expected one installed Sodium JAR; select it with --sodium-jar.')
    return matches[0]


def clear_stages(directory):
    # Only generated shaders in this check's own directory are removed.
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.suffix in ('.vsh', '.fsh'):
            path.unlink()


def remap_sodium_samplers(source, destination):
    """Model the engine's pipeline binding remap after independent translation.

    Native translation auto-numbers descriptors separately for each stage.
    Sodium's VS/FS samplers can thus get identical names but different types.
    Rename only generated sampler identifiers, not any candidate shader source.
    """
    clear_stages(destination)
    changed = []
    for path in sorted(source.iterdir()):
        if path.suffix not in ('.vsh', '.fsh'):
            continue
        shader = path.read_text(encoding='utf-8')
        samplers = re.findall(r'\buniform\s+([iu]?sampler\w+)\s+(_uniform_\w+)\s*;', shader)
        for kind, name in samplers:
            renamed = name + '_' + path.suffix[1:]
            shader = re.sub(r'\b' + re.escape(name) + r'\b', renamed, shader)
            changed.append({'file': path.name, 'type': kind, 'old': name, 'new': renamed})
        (destination / path.name).write_text(shader, encoding='utf-8')
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prism', type=Path, default=Path(os.environ['APPDATA']) / 'PrismLauncher')
    parser.add_argument('--pack', type=Path, help='Validate an existing variant ZIP instead of the source assets')
    parser.add_argument('--sodium-jar', type=Path, help='Installed Sodium JAR supplying the adapter includes')
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
    subprocess.run([str(java / 'javac.exe'), '-encoding', 'UTF-8', '-cp', gpu_cp, '-d', str(classes),
                    str(ROOT / 'tools/CheckDriver.java'), str(ROOT / 'tools/CheckNormalMaterials.java')], check=True)
    archive = args.pack.resolve() if args.pack else report / 'candidate.zip'
    if not args.pack:
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(ROOT / 'pack.mcmeta', 'pack.mcmeta')
            for p in sorted((ROOT / 'assets').rglob('*')):
                if p.is_file():
                    z.write(p, p.relative_to(ROOT).as_posix())
    stages = report / 'roundtrip'
    driver_args = [stages]
    vanilla_archive = archive
    sodium_jar = None
    normal_maps_enabled = '1'
    with zipfile.ZipFile(archive) as z:
        names = set(z.namelist())
        if any(name.startswith('assets/sodium/') for name in names):
            sodium_jar = find_sodium_jar(prism, args.sodium_jar)
            vanilla_archive = report / 'candidate-vanilla-validation.zip'
            with zipfile.ZipFile(vanilla_archive, 'w', zipfile.ZIP_DEFLATED) as native:
                for entry in z.infolist():
                    if not entry.filename.startswith('assets/sodium/'):
                        native.writestr(copy.copy(entry), z.read(entry))
            print('Vanilla generic shader check excludes assets/sodium; the adapter is checked separately below.')
        settings = 'assets/chroma/shaders/include/settings.glsl'
        shadow_config = 'assets/chroma/shaders/include/shadow_config.glsl'
        config_name = settings if settings in names else shadow_config
        normal_config = settings if settings in names else 'assets/chroma/shaders/include/normal_config.glsl'
        if normal_config in names:
            normal_setting = re.search(r'^\s*#define\s+CHROMA_NORMAL_MAPS\s+([01])(?:\s*//[^\n]*)?\s*$', z.read(normal_config).decode('utf-8'), re.M)
            if not normal_setting:
                raise ValueError(f'Cannot read CHROMA_NORMAL_MAPS from {normal_config}')
            normal_maps_enabled = normal_setting[1]
        if shadow_config in names:
            config = z.read(config_name).decode('utf-8')
            enabled = re.search(r'^\s*#define\s+CHROMA_SHADOWS_ENABLED\s+([01])(?:\s*//[^\n]*)?\s*$', config, re.M)
            if not enabled:
                raise ValueError(f'Cannot read CHROMA_SHADOWS_ENABLED from {config_name}')
            chain = json.loads(z.read('assets/minecraft/post_effect/end_of_frame.json'))
            shadow_passes = [f'post_pass_{i:03d}.vsh' for i, p in enumerate(chain['passes'])
                             if p['output'].startswith(('voxel', 'shadow_', 'surface_normal', 'vacancy_'))]
            shade = next(i for i, p in enumerate(chain['passes']) if p['fragment_shader'] == 'chroma:post/shade')
            assert shadow_passes, 'No shadow passes checked'
            driver_args += [enabled[1], ','.join(shadow_passes), f'post_pass_{shade:03d}.vsh']
    clear_stages(stages)

    def run(name, parameters, label=None):
        label = label or name
        argfile = report / (label + '.args')
        run_cp = gpu_cp if name in ('CheckDriver', 'CheckNormalMaterials') else cp
        argfile.write_text('--enable-native-access=ALL-UNNAMED\n-Xmx2G\n-Dorg.lwjgl.system.stackSize=1024\n-cp\n"' + run_cp.replace('\\', '/') + '"\n' + name + '\n', encoding='utf-8')
        result = subprocess.run([str(java / 'java.exe'), '@' + str(argfile), *map(str, parameters)], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        log = result.stdout.decode('utf-8', errors='replace')
        (report / (label + '.log')).write_text(log, encoding='utf-8')
        print(log[-6000:])
        result.check_returncode()

    run('ValidatePack', [vanilla_archive, jar])
    run('ReproduceClientShaders', [vanilla_archive, jar, stages])
    run('CheckDriver', driver_args)
    if sodium_jar:
        subprocess.run([str(java / 'javac.exe'), '-encoding', 'UTF-8', '-cp', cp, '-d', str(classes),
                        str(ROOT / 'tools/SodiumShaderCheck.java')], check=True)
        sodium_stages = report / 'sodium-roundtrip'
        sodium_driver = report / 'sodium-driver'
        clear_stages(sodium_stages)
        run('SodiumShaderCheck', [archive, jar, sodium_stages, sodium_jar])
        remapping = remap_sodium_samplers(sodium_stages, sodium_driver)
        (report / 'sodium-driver-remap.json').write_text(json.dumps({
            'reason': remap_sodium_samplers.__doc__, 'samplers': remapping,
            'candidate_modified': False,
        }, indent=2) + '\n', encoding='utf-8')
        run('CheckDriver', [sodium_driver], 'CheckSodiumDriver')
    # The material GPU check must use the selected archive, not a different
    # working tree when --pack was passed. Extract only its shader includes.
    with tempfile.TemporaryDirectory(prefix='native-materials-', dir=report) as directory:
        material_root = Path(directory)
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if name.startswith('assets/chroma/shaders/include/') and name.endswith('.glsl'):
                    target = (material_root / name).resolve()
                    if not target.is_relative_to(material_root.resolve()):
                        raise ValueError(f'Unsafe shader archive path: {name}')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
        run('CheckNormalMaterials', [material_root, normal_maps_enabled])
    # Command examples and bilingual guides belong to the repository, not the RP.
    run('CheckExamples', [ROOT, report / 'examples-validation.json'])


if __name__ == '__main__':
    main()
