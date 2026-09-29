"""Generate five automatic-address marker types and backward-compatible item aliases.

The only encoded properties are shape, local vertex corner, and header/payload.
No item-model suffix is used to allocate a light. Writes only marker assets/atlas.
"""
from argparse import ArgumentParser
from copy import deepcopy
from pathlib import Path
import json, struct, zlib
ROOT=Path(__file__).resolve().parents[1]
FAMILIES = {'marker': 0, 'marker_spot_narrow': 1, 'marker_spot': 2, 'marker_spot_wide': 3, 'marker_dome': 4}
MODEL_TEMPLATE = {'texture_size': [8, 8], 'textures': {'layer0': 'chroma:custom/marker', 'particle': 'chroma:custom/marker'}, 'elements': [{'from': [0, 0, 8], 'to': [16, 16, 8], 'faces': {'south': {'uv': [2, 2, 6, 6], 'texture': '#layer0', 'tintindex': 0}}}]}
ITEM_TEMPLATE = {'model': {'type': 'minecraft:select', 'property': 'minecraft:display_context', 'cases': [{'when': ['fixed', 'none'], 'model': {'type': 'minecraft:model', 'model': 'chroma:custom/marker', 'tints': [{'type': 'minecraft:custom_model_data', 'index': 0, 'default': -1}]}}], 'fallback': {'type': 'minecraft:model', 'model': 'minecraft:item/paper'}}}

def marker_png(shape, header):
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    rows=[]
    for y in range(8):
        row=bytearray([0])
        for x in range(8):
            corner=(0 if y<2 else 1) if x<2 else (3 if y<2 else 2)
            row+=bytes([76, 195, shape+8*corner+(32 if header else 0)])
        rows.append(row)
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',8,8,8,2,0,0,0))
            +chunk(b'IDAT',zlib.compress(b''.join(rows),9))+chunk(b'IEND',b''))

def generate(output=ROOT):
    output=Path(output).resolve()
    base=output/'assets/chroma'
    for folder in ['items','models/custom','textures/custom']:
        (base/folder).mkdir(parents=True,exist_ok=True)
    # Remove only legacy textures owned by this generator inside the selected pack.
    for family in FAMILIES:
        for n in range(2,33):
            path=base/f'textures/custom/{family}{n}.png'
            if path.is_file(): path.unlink()
    atlas=[]
    for name,shape in FAMILIES.items():
        model=deepcopy(MODEL_TEMPLATE)
        model['textures']={'layer0':f'chroma:custom/{name}','header':f'chroma:custom/{name}_header','particle':f'chroma:custom/{name}'}
        header=deepcopy(model['elements'][0]);header['faces']['south']['texture']='#header'
        model['elements']=[header,model['elements'][0]]
        for is_header in [False,True]:
            image_name=name+('_header' if is_header else '')
            (base/f'textures/custom/{image_name}.png').write_bytes(marker_png(shape,is_header))
            atlas.append({'type':'minecraft:single','resource':f'chroma:custom/{image_name}'})
        for index in range(32):
            alias=name+(str(index+1) if index else '')
            item=deepcopy(ITEM_TEMPLATE)
            item['model']['cases'][0]['model']['model']=f'chroma:custom/{name}'
            (base/f'items/{alias}.json').write_text(json.dumps(item,indent=2)+'\n',encoding='utf-8')
            model_data=model if index==0 else {'parent':f'chroma:custom/{name}'}
            (base/f'models/custom/{alias}.json').write_text(json.dumps(model_data,indent=2)+'\n',encoding='utf-8')
    target=output/'assets/minecraft/atlases/items.json';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps({'sources':atlas},indent=2)+'\n',encoding='utf-8')
    print('Generated 5 primary shapes, 10 textures and 160 compatible item aliases; no manual source IDs.')

def main():
    parser=ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT)
    generate(parser.parse_args().output)

if __name__=='__main__': main()
