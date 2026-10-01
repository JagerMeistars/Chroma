"""Build the optional flashlight datapack with Python's standard library."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'datapacks/chroma_flashlight'
    out = ROOT / 'dist/Chroma-Flashlight-Test-26.3.zip'
    out.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.write(source / 'pack.mcmeta', 'pack.mcmeta')
        for path in sorted((source / 'data').rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(source).as_posix())
    checksum = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix('.zip.sha256').write_text(f'{checksum}  {out.name}\n', encoding='ascii')
    print(json.dumps(dict(zip=str(out), sha256=checksum, bytes=out.stat().st_size)))


if __name__ == '__main__':
    main()
