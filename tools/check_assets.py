"""Validate the standalone slotless resource graph, transport ABI and marker aliases.

This is static validation. It does not measure FPS or verify gameplay.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, struct, zipfile, zlib
ROOT=Path(__file__).resolve().parents[1]
FAMILIES={'marker':0,'marker_spot_narrow':1,'marker_spot':2,'marker_spot_wide':3,'marker_dome':4}

def read_marker_png(path):
    """Decode the deterministic RGB8/filter-zero PNG format emitted by our generator."""
    data=path.read_bytes()
    if data[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('Invalid PNG signature')
    at=8;compressed=bytearray();header=None
    while at<len(data):
        length=struct.unpack_from('>I',data,at)[0];kind=data[at+4:at+8]
        payload=data[at+8:at+8+length]
        crc=struct.unpack_from('>I',data,at+8+length)[0]
        if zlib.crc32(kind+payload)!=crc:raise ValueError('Invalid PNG CRC')
        if kind==b'IHDR':header=struct.unpack('>IIBBBBB',payload)
        if kind==b'IDAT':compressed+=payload
        at+=length+12
    if header!=(8,8,8,2,0,0,0):raise ValueError(f'Unexpected generated-marker PNG format: {header}')
    raw=zlib.decompress(compressed)
    if len(raw)!=8*25:raise ValueError('Unexpected decompressed PNG length')
    rows=[]
    for y in range(8):
        row=raw[y*25:(y+1)*25]
        if row[0]!=0:raise ValueError('Expected deterministic filter-zero PNG')
        rows.append([tuple(row[1+x*3:4+x*3]) for x in range(8)])
    return rows

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--client-jar',type=Path,default=Path(os.environ['APPDATA'])/'PrismLauncher/libraries/com/mojang/minecraft/26.3/minecraft-26.3-client.jar')
    parser.add_argument('--source',type=Path)
    parser.add_argument('--source-manifest',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args();root=args.root.resolve()
    shadow_build=(root/'assets/chroma/shaders/include/shadow_config.glsl').is_file()
    jar=zipfile.ZipFile(args.client_jar);vanilla=set(jar.namelist());errors=[];references=0
    def resource(identifier,folder,ext):
        nonlocal references
        ns,name=identifier.split(':',1) if ':' in identifier else ('minecraft',identifier)
        rel=f'assets/{ns}/{folder}/{name}{ext}';references+=1
        if not (root/rel).is_file() and rel not in vanilla:errors.append(f'Missing resource: {rel}')
        return rel
    def model_refs(value):
        if isinstance(value,dict):
            for key,item in value.items():
                if key in ('model','parent') and isinstance(item,str):resource(item,'models','.json')
                elif key=='textures':
                    for tex in item.values():
                        if not tex.startswith('#'):resource(tex,'textures','.png')
                else:model_refs(item)
        elif isinstance(value,list):
            for item in value:model_refs(item)
    files=sorted(p for p in (root/'assets').rglob('*') if p.is_file())
    for path in files:
        try:
            if path.suffix=='.json':
                data=json.loads(path.read_text(encoding='utf-8'))
                if '/items/' in path.as_posix() or '/models/' in path.as_posix():model_refs(data)
            if path.suffix in ('.fsh','.vsh','.glsl','.json'):
                source=path.read_text(encoding='utf-8')
                removed = r'objmc|shader_selector|dcs:|MATDEC_PREV|MatPrevSampler|CHROMA_PERF|DEBUG_MODE'
                if not shadow_build: removed += r'|shadow|voxel|noshadow'
                if re.search(removed,source,re.I):
                    errors.append(f'Removed subsystem remains: {path.relative_to(root)}')
                for inc in re.findall(r'#include\s*<([^>]+)>',source):resource(inc,'shaders/include','')
        except (ValueError,KeyError,TypeError) as e:errors.append(f'{path.relative_to(root)}: {e}')
    namespaces={p.name for p in (root/'assets').iterdir()}
    if namespaces!={'chroma','minecraft'}:errors.append(f'Unexpected asset namespaces: {namespaces}')
    mcfiles={p.relative_to(root/'assets/minecraft').as_posix() for p in (root/'assets/minecraft').rglob('*') if p.is_file()}
    allowed={'post_effect/end_of_frame.json','atlases/items.json'}|{f'shaders/core/{name}.{stage}' for name in ('item','entity') for stage in ('vsh','fsh')}
    if shadow_build: allowed.add('shaders/core/integrate_depth.fsh')
    if mcfiles!=allowed:errors.append(f'Unexpected Minecraft overrides: {mcfiles^allowed}')
    chain=json.loads((root/'assets/minecraft/post_effect/end_of_frame.json').read_text(encoding='utf-8'))
    targets=chain['targets'];available={'minecraft:main'};dimensions={}
    for name,definition in targets.items():
        if not isinstance(definition,dict):errors.append(f'Target {name} must be an object');continue
        width,height=definition.get('width'),definition.get('height')
        for axis,value in [('width',width),('height',height)]:
            if value is not None and (type(value) is not int or value<=0):errors.append(f'Invalid {name}.{axis}: {value}')
        if (width is None)!=(height is None):errors.append(f'Explicit target needs both dimensions: {name}')
        dimensions[name]=[width,height] if width is not None else 'framebuffer'
    for index,pas in enumerate(chain['passes']):
        resource(pas['vertex_shader'],'shaders','.vsh');resource(pas['fragment_shader'],'shaders','.fsh')
        output=pas['output'];seen=set()
        if output not in targets and output!='minecraft:main':errors.append(f'Undefined output target: {output}')
        for inp in pas.get('inputs',[]):
            sampler=inp['sampler_name']
            if sampler in seen:errors.append(f'Duplicate sampler in pass {index}: {sampler}')
            seen.add(sampler)
            if 'target' in inp:
                target=inp['target']
                if target not in targets and target!='minecraft:main':errors.append(f'Undefined input target: {target}')
                if target==output:errors.append(f'Read/write feedback in pass {index}: {target}')
                # This renderer is entirely frame-local, even if debug readback
                # makes a target persistent. Never read an earlier frame by accident.
                history = shadow_build and target in ('voxel_history','voxel_meta_history','shadow_map_history','shadow_meta_history') and targets[target].get('persistent')
                if target not in available and not history:errors.append(f'Target read before this frame writes it: {target}')
            elif 'location' in inp:
                # Exact 26.3 PostChain expands these to textures/effect/<id>.png.
                ns,name=inp['location'].split(':',1)
                rel=f'assets/{ns}/textures/effect/{name}.png';references+=1
                if not (root/rel).is_file() and rel not in vanilla:errors.append(f'Missing resource: {rel}')
        available.add(output)
    for target,expected in {'catalog':[2048,1],'counts':[64,1],'indices':[128,1],'colorcache':[128,1],'matdec':[2176,1],'tile_masks':[512,72],'swap':'framebuffer'}.items():
        if dimensions.get(target)!=expected:errors.append(f'Transport target dimension mismatch: {target}={dimensions.get(target)}, expected {expected}')
    if not chain['passes'] or chain['passes'][-1]['output']!='minecraft:main':errors.append('Final pass does not write the main target')
    atlas=json.loads((root/'assets/minecraft/atlases/items.json').read_text(encoding='utf-8')).get('sources',[])
    expected_sprites={f'chroma:custom/{name}{suffix}' for name in FAMILIES for suffix in ('','_header')}
    actual_sprites=set()
    for entry in atlas:
        if entry.get('type') not in ('single','minecraft:single'):errors.append(f'Unexpected atlas entry: {entry}');continue
        tex=entry.get('resource');actual_sprites.add(tex)
        if entry.get('sprite',tex)!=tex:errors.append(f'Unexpected sprite alias: {entry}')
        resource(tex,'textures','.png')
    if actual_sprites!=expected_sprites or len(atlas)!=10:errors.append('Item atlas must stitch exactly the ten primary marker/header textures')
    expected_items={name+(str(i) if i>1 else '') for name in FAMILIES for i in range(1,33)}
    actual_items={p.stem for p in (root/'assets/chroma/items').glob('*.json')}
    if actual_items!=expected_items:errors.append(f'Marker item aliases differ: {actual_items^expected_items}')
    expected_png={name+'.png' for name in [s.split('/')[-1] for s in expected_sprites]}
    actual_png={p.name for p in (root/'assets/chroma/textures/custom').glob('*.png')}
    if actual_png!=expected_png:errors.append(f'Unexpected marker textures: {actual_png^expected_png}')
    marker_count=0
    for family,shape in FAMILIES.items():
        model=json.loads((root/f'assets/chroma/models/custom/{family}.json').read_text(encoding='utf-8'))
        elements=model.get('elements',[])
        if len(elements)!=2:errors.append(f'{family}: expected header and payload quads')
        else:
            for index,texture in [(0,'#header'),(1,'#layer0')]:
                face=elements[index].get('faces',{}).get('south',{})
                if elements[index].get('from')!=[0,0,8] or elements[index].get('to')!=[16,16,8] or face.get('uv')!=[2,2,6,6] or face.get('texture')!=texture or face.get('tintindex')!=0:
                    errors.append(f'{family}: unexpected geometry/UV for quad {index}')
        if model.get('textures',{}).get('layer0')!=f'chroma:custom/{family}' or model.get('textures',{}).get('header')!=f'chroma:custom/{family}_header':
            errors.append(f'{family}: unexpected payload/header texture reference')
        for header in [False,True]:
            name=family+('_header' if header else '')
            try:
                pixels=read_marker_png(root/f'assets/chroma/textures/custom/{name}.png')
                for y in range(8):
                    for x in range(8):
                        corner=(0 if y<2 else 1) if x<2 else (3 if y<2 else 2)
                        expected=(76,195,shape+8*corner+(32 if header else 0))
                        if pixels[y][x]!=expected:raise ValueError(f'Wrong shape/corner/header bytes at {x},{y}: {pixels[y][x]} != {expected}')
            except (ValueError,OSError,struct.error,zlib.error) as e:errors.append(f'{name}: {e}')
        for i in range(1,33):
            name=family+(str(i) if i>1 else '')
            item=json.loads((root/f'assets/chroma/items/{name}.json').read_text(encoding='utf-8'))
            branch=item.get('model',{}).get('cases',[{}])[0]
            nested=branch.get('model',{})
            if set(branch.get('when',[]))!={'fixed','none'} or nested.get('model')!=f'chroma:custom/{family}':errors.append(f'{name}: alias must use the unnumbered primary model')
            if nested.get('tints')!=[{'type':'minecraft:custom_model_data','index':0,'default':-1}]:errors.append(f'{name}: colour component mismatch')
            if i>1:
                alias=json.loads((root/f'assets/chroma/models/custom/{name}.json').read_text(encoding='utf-8'))
                if alias!={'parent':f'chroma:custom/{family}'}:errors.append(f'{name}: legacy model must inherit its primary shape')
            marker_count+=1
    transport=(root/'assets/chroma/shaders/include/auto_transport.glsl').read_text(encoding='utf-8')
    for constant,value in [('CHROMA_AUTO_SIGNATURE','0xC7A03200u'),('CHROMA_AUTO_HEADER','0xC7A04E01u'),('CHROMA_AUTO_CHECKSUM','0x91E10DA5u')]:
        if not re.search(r'\b'+constant+r'\s*=\s*'+value+r'\s*;',transport):errors.append(f'Raw transport ABI constant mismatch: {constant}')
    for helper in ['chromaAutoEncode','chromaAutoDecode','chromaAutoCapacity','chromaAutoOrigin','chromaAutoPositionChecksum','chromaAutoChecksumBase','chromaAutoChecksumPosition','chromaAutoOctDecode','chromaAutoUnpackScales']:
        if not re.search(r'\b'+helper+r'\s*\(',transport):errors.append(f'Missing raw transport helper: {helper}')
    for name in ['item','entity']:
        for stage in ['vsh','fsh']:
            shader=(root/f'assets/minecraft/shaders/core/{name}.{stage}').read_text(encoding='utf-8')
            if not shader.startswith('#version 330\n'):errors.append(f'{name}.{stage}: expected native GLSL330 contract')
            if stage=='vsh' and 'gl_VertexIndex - corner' not in shader:errors.append(f'{name}: missing automatic vertex addressing')
            if stage=='fsh' and not all(f'words[{i}] =' in shader for i in range(8)):errors.append(f'{name}: incomplete eight-word payload')
    source_unchanged=None
    if args.source:
        before=json.loads((args.source_manifest or root/'audit/source-before.json').read_text(encoding='utf-8'))
        after={p.relative_to(args.source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in args.source.rglob('*') if p.is_file()}
        source_unchanged=before==after
        if not source_unchanged:errors.append('Source RPDREVO changed')
    result={'json_files':sum(p.suffix=='.json' for p in files),'references_checked':references,'post_passes':len(chain['passes']),
            'post_target_dimensions':dimensions,'minecraft_overrides':len(mcfiles),'primary_shapes':len(FAMILIES),
            'marker_item_aliases':marker_count,'item_atlas_sources':len(atlas),'manual_source_ids':False,
            'source_unchanged':source_unchanged,'errors':errors,'client_gameplay':False,'fps_measured':False}
    report=args.report or root/'audit/assets.json'
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2));jar.close()
    if errors:raise SystemExit(1)

if __name__=='__main__':main()
