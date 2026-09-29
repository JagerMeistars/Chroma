"""Build a resource-pack ZIP with pack.mcmeta at its root (Python standard library)."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def pack_files():
    files = [ROOT / 'pack.mcmeta', ROOT / 'README.md', ROOT / 'CREDITS.md']
    if (ROOT / 'pack.png').exists():
        files.append(ROOT / 'pack.png')
    for directory in ('assets', 'docs'):
        files.extend(p for p in (ROOT / directory).rglob('*') if p.is_file())
    return sorted(files)


def main():
    out = ROOT / 'dist' / 'Chroma-Auto-26.3.zip'
    out.parent.mkdir(exist_ok=True)
    files = pack_files()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (out.parent / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix('.zip.sha256').write_text(f'{checksum}  {out.name}\n', encoding='ascii')
    print(json.dumps({'zip': str(out), 'files': len(files), 'bytes': out.stat().st_size, 'sha256': checksum}))


if __name__ == '__main__':
    main()
