"""Build either pure-RP shadow variant; keep the main Auto ZIP unchanged."""
from pathlib import Path
import argparse
import hashlib
import json
import zipfile
from build import ROOT, pack_files

CHAIN = 'assets/minecraft/post_effect/end_of_frame.json'
CONFIG = 'assets/chroma/shaders/include/shadow_config.glsl'


def target_input(name, target, **kwargs):
    return dict(sampler_name=name, target=target, **kwargs)


def render_pass(shader, output, inputs, vertex='minecraft:core/screenquad'):
    return dict(vertex_shader=vertex, fragment_shader='chroma:post/' + shader,
                inputs=inputs, output=output)


def configure(chain, volume=None):
    chain = json.loads(json.dumps(chain))
    chain['targets'] = {k: v for k, v in chain['targets'].items() if not k.startswith(('voxel','shadow_'))}
    chain['passes'] = [p for p in chain['passes'] if not p['output'].startswith(('voxel','shadow_'))]
    shade = next(p for p in chain['passes'] if p['fragment_shader'] == 'chroma:post/shade')
    shade['inputs'] = [i for i in shade['inputs'] if not i['sampler_name'].startswith(('Voxel','Shadow'))]
    voxel_inputs=[]
    if volume:
        dims = volume['dims']
        for level, sampler in enumerate(('Voxel', 'VoxelLod1', 'VoxelLod2')):
            name = 'volume' + (f'_lod{level}' if level else '')
            nx, ny, nz = [n >> level for n in dims]
            voxel_inputs.append(dict(sampler_name=sampler,
                location=f'chroma:shadows/{name}', width=nx // 16 * nz, height=ny,
                bilinear=False))
    else:
        for name, width, height in (('voxel',4096,256), ('voxel_history',4096,256),
                ('voxel_meta',8,1), ('voxel_meta_history',8,1),
                ('voxel_lod1',1024,128), ('voxel_lod2',256,64)):
            chain['targets'][name] = dict(width=width, height=height, persistent=True)
        updates = [
            render_pass('voxel_update','voxel',[
                target_input('Prev','voxel_history'), target_input('Meta','voxel_meta_history'),
                target_input('InDepth','minecraft:main',use_depth_buffer=True),
                target_input('MainColor','minecraft:main'),
                target_input('MatDec','matdec'), target_input('Catalog','catalog')]),
            render_pass('voxel_meta','voxel_meta',[
                target_input('Meta','voxel_meta_history'), target_input('MatDec','matdec')]),
            render_pass('voxel_lod','voxel_lod1',[target_input('In','voxel')]),
            render_pass('voxel_lod','voxel_lod2',[target_input('In','voxel_lod1')]),
        ]
        at = chain['passes'].index(shade)
        chain['passes'][at:at] = updates
        for sampler, target in (('Voxel','voxel'), ('VoxelLod1','voxel_lod1'), ('VoxelLod2','voxel_lod2')):
            voxel_inputs.append(target_input(sampler,target))
        at = len(chain['passes']) - 1
        chain['passes'][at:at] = [
            render_pass('copy','voxel_history',[target_input('In','voxel')]),
            render_pass('copy','voxel_meta_history',[target_input('In','voxel_meta')]),
        ]
    for name,width,height in (('shadow_map',2048,1024),('shadow_map_history',2048,1024),
                              ('shadow_meta',1024,1),('shadow_meta_history',1024,1)):
        chain['targets'][name]=dict(width=width,height=height,persistent=True)
    shadow_inputs=[target_input('MatDec','matdec'),
        target_input('PreviousShadow','shadow_map_history'),
        target_input('CurrentShadowMeta','shadow_meta'),
        target_input('PreviousShadowMeta','shadow_meta_history'),
        target_input('VoxelMeta','matdec' if volume else 'voxel_meta'), *voxel_inputs]
    at=chain['passes'].index(shade)
    chain['passes'][at:at]=[
        render_pass('shadow_meta','shadow_meta',[target_input('MatDec','matdec')]),
        render_pass('shadow_map','shadow_map',shadow_inputs)]
    shade['inputs'].append(target_input('Shadow','shadow_map'))
    shade['inputs'].append(voxel_inputs[0])
    chain['passes'][-1:-1]=[
        render_pass('copy','shadow_map_history',[target_input('In','shadow_map')]),
        render_pass('copy','shadow_meta_history',[target_input('In','shadow_meta')])]
    return chain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--static-volume', type=Path, help='Exporter output folder with metadata.json')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--prepare-dynamic', action='store_true', help='Update the source post chain')
    parser.add_argument('--debug', action='store_true', help='Diagnostic grayscale source visibility')
    args = parser.parse_args()
    volume = json.loads((args.static_volume/'metadata.json').read_text()) if args.static_volume else None
    chain = configure(json.loads((ROOT/CHAIN).read_text()), volume)
    if args.prepare_dynamic:
        if volume: parser.error('--prepare-dynamic cannot be used with a static volume')
        (ROOT/CHAIN).write_text(json.dumps(chain, indent=2)+'\n', encoding='utf-8')
    replacements = {CHAIN: (json.dumps(chain,indent=2)+'\n').encode()}
    kind = 'Static' if volume else 'Dynamic'
    meta = json.loads((ROOT/'pack.mcmeta').read_text(encoding='utf-8'))
    meta['pack']['description'] = f'Chroma Shadows {kind} · 128 lights / 128 источников · 26.3'
    replacements['pack.mcmeta'] = (json.dumps(meta, ensure_ascii=False, indent=2)+'\n').encode()
    config = (ROOT/CONFIG).read_text()
    if args.debug:
        config = config.replace('#define CHROMA_SHADOW_DEBUG 0', '#define CHROMA_SHADOW_DEBUG 1')
    if volume:
        origin = [round(n * volume['cellsPerBlock']) for n in volume['origin']]
        config = config.replace('#define CHROMA_STATIC_WORLD 0',
            '#define CHROMA_STATIC_WORLD 1\n#define CHROMA_VOX_DIMS ivec3('+','.join(map(str,volume['dims']))+
            ')\n#define CHROMA_VOX_ORIGIN ivec3('+','.join(map(str,origin))+')')
        replacements[CONFIG] = config.encode()
        for name in ('volume','volume_lod1','volume_lod2'):
            replacements[f'assets/chroma/textures/effect/shadows/{name}.png'] = (args.static_volume/(name+'.png')).read_bytes()
        replacements['docs/shadow-world.json'] = (args.static_volume/'metadata.json').read_bytes()
    replacements[CONFIG] = config.encode()
    out = args.output or ROOT/'dist'/f'Chroma-Shadows-{kind}-26.3.zip'
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in pack_files():
            relative = path.relative_to(ROOT).as_posix()
            archive.writestr(relative, replacements.pop(relative, path.read_bytes()))
        for relative,data in replacements.items(): archive.writestr(relative,data)
    sha = hashlib.sha256(out.read_bytes()).hexdigest()
    out.with_suffix('.zip.sha256').write_text(f'{sha}  {out.name}\n')
    print(json.dumps(dict(zip=str(out),sha256=sha,mode=kind,bytes=out.stat().st_size)))


if __name__ == '__main__': main()
