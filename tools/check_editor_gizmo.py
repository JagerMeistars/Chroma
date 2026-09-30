"""Classify an actual Axiom GPU vertex dump and ordinary-geometry controls.

CPU signature coverage only: this does not execute shaders or prove raster output.
An optional capture contains uploaded Position/Color and Lines vertex buffers.
"""
from argparse import ArgumentParser
from pathlib import Path
import itertools
import json
import re
import struct


def matches(position, rgba, lines, scale, perspective=True):
    if not perspective: return False
    if scale[0]<.1-.000001 or any(abs(v-scale[0])>max(.000001,scale[0]*.0001) for v in scale):
        return False
    p = tuple(map(abs,position))
    color = tuple(v/255 for v in rgba)
    grey = all(abs(v-color[0])<.000001 for v in color[:3])
    if not lines and color[3]>.999999 and grey and all(abs(v-.3)<.000001 for v in p):
        return True
    if color[3]!=0 and all(abs(color[3]-a)>.000001 for a in (128/255,170/255,1)):
        return False
    lo,mid,hi = sorted(color[:3])
    axis_color = hi>0 and (mid<.000001 or (abs(lo-mid)<1.5/255 and
        any(abs(lo/hi-ratio)<.015 for ratio in (.6,191/255,128/255))))
    if not axis_color and not grey: return False
    smallest,middle,largest = sorted(p)
    radius2 = sum(v*v for v in p)
    ring = 24.939<=radius2<=25.003
    if lines:
        if not ((abs(hi-191/255)<.000001 and abs(color[3]-170/255)<.000001) or
                (abs(hi-1)<.000001 and abs(color[3]-1)<.000001 and mid>0)): return False
        axis_end = middle<.00001
        return axis_color and (ring or axis_end)
    cone = ((abs(largest-4)<.00001 and (middle<.00001 or
             abs(middle*middle+smallest*smallest-.071111111)<.00001)) or
            (abs(largest-4.8)<.00001 and middle<.00001))
    move_plane = (smallest<.00001 and any(abs(middle-v)<.00001 for v in (1.65,2.55)) and
                  any(abs(largest-v)<.00001 for v in (1.65,2.55)))
    scale_box = abs(smallest-.3)<.00001 and abs(middle-.3)<.00001
    return (largest<.00001 and color[3]==0) or (axis_color and (cone or move_plane or scale_box or ring))


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,help='Optional native gizmo dump metadata JSON')
    parser.add_argument('--report',type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    shader = (root/'assets/chroma/shaders/include/editor_gizmo.glsl').read_text()
    compact = re.sub(r'\s+','',re.sub(r'//[^\n]*','',shader))
    # Match CPU expressions to the versioned shader signature; do not silently
    # bless a capture using a stale classifier after the hook changes.
    for expression in (
        'if(ProjMat[2][3]==0.0)returnfalse;',
        'scale.x<0.1-0.000001', 'scale.x*0.0001',
        'abs(p-vec3(0.3))', 'abs(color.a-128.0/255.0)', 'abs(color.a-170.0/255.0)',
        'abs(lo/hi-0.6)<0.015', 'abs(lo/hi-191.0/255.0)<0.015', 'abs(lo/hi-128.0/255.0)<0.015',
        'boolring=radius2>=24.939&&radius2<=25.003;',
        'abs(largest-4.0)<0.00001&&(middle<0.00001||',
        'abs(middle*middle+smallest*smallest-0.071111111)<0.00001',
        'abs(largest-4.8)<0.00001&&middle<0.00001',
        'abs(smallest-0.3)<0.00001&&abs(middle-0.3)<0.00001',
        '(largest<0.00001&&color.a==0.0)',
        'returnaxisColor&&(ring||axisEnd);',
        'boolaxisEnd=middle<0.00001;',
        'abs(hi-1.0)<0.000001&&abs(color.a-1.0)<0.000001&&mid>0.0',
    ):
        assert expression in compact, 'Update CPU classifier after shader signature change: '+expression
    metadata = json.loads(args.capture.read_text()) if args.capture else {'gizmoCount': 0}
    counts = {}
    for index in range(metadata['gizmoCount']):
        gizmo = metadata[f'gizmo{index}']
        scalar = gizmo['nativeDistanceMultiplier']
        scale = (scalar,)*3
        for name,stride,lines in (('positionColor',16,False),('lines',24,True)):
            entry = gizmo[name]
            raw = Path(entry['rawBytes']).read_bytes()
            assert len(raw)%stride==0
            vertices = [struct.unpack_from('<3f4B',raw,offset) for offset in range(0,len(raw),stride)]
            missed = [i for i,v in enumerate(vertices) if not matches(v[:3],v[3:],lines,scale)]
            assert not missed, (name,'Unmatched actual GPU vertices',missed[:20])
            assert all(not matches(v[:3],v[3:],lines,scale,False) for v in vertices), 'Orthographic GUI must bypass tagging'
            assert all(not matches(v[:3],v[3:],lines,(scalar,scalar*1.1,scalar)) for v in vertices)
            counts[f'gizmo{index}/{name}'] = len(vertices)

    controls = 0
    for position in itertools.product((0,1),repeat=3):
        for color in ((0,0,0,102),(255,255,255,255),(255,0,0,255),(0,255,0,255)):
            for lines in (False,True):
                assert not matches(position,color,lines,(1,1,1)), ('Ordinary unit box/outline matched',position,color,lines)
                controls += 1
    for half in (.06,.1,.2,.5):
        for position in itertools.product((-half,half),repeat=3):
            assert not matches(position,(255,255,255,255),False,(1,1,1))
            controls += 1
    assert matches((.3,.3,.3),(255,255,255,255),False,(1,1,1)), 'Known centre-box identity'
    assert not matches((.3,.3,.3),(255,255,255,255),False,(1,1,1),False)
    assert not matches((.3,.3,.3),(255,255,255,255),False,(1,1.1,1))
    assert not matches((.3,.3,.3),(255,255,255,255),False,(.05,.05,.05))
    assert not matches((4,0,0),(133,0,0,200),False,(1,1,1)), 'Unrelated alpha must be excluded'
    assert matches((2.5,0,0),(191,0,0,170),True,(1,1,1)), 'Shrinking scale-drag endpoint'
    assert not matches((4,0,0),(255,0,0,255),True,(1,1,1)), 'Ordinary opaque primary-colour debug axis'
    assert matches((0,0,0),(0,0,0,0),False,(1,1,1)), 'Transparent rotation fan centre'
    result = dict(actualUploadedVertices=counts,negativeControls=controls,
                  orthographicAndNonuniformBypass=True,
                  scaleEvidence='Native getDistanceMultiplier scalar; full ModelView matrix was not captured',
                  nativeShaderExecution=False,
                  knownAmbiguities=['An identical opaque grey local cube at+-0.3 is indistinguishable from the Axiom centre mesh.',
                                    'Exact axis-coloured editor/debug long axes and .3-thick handle boxes may share the mesh signature.'])
    if args.report:
        args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
