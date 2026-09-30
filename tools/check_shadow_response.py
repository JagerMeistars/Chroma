"""CPU response regression; no game, shader execution or FPS claim."""
from pathlib import Path
import random
import re

ROOT = Path(__file__).resolve().parents[1]
LUMA = (.2125, .7154, .0721)
FULL = 3.0


def dot(a, b): return sum(x*y for x,y in zip(a,b))


def response(energy):
    t = min(max(energy/FULL, 0), 1)
    return t*t*(3-2*t)


def aggregate(lamps, bounded=True):
    # Each item is the full RGB lamp contribution and independent visibility.
    rgb = tuple(sum(color[k]*v for color,v in lamps) for k in range(3))
    lum = dot(rgb,LUMA)
    reach = sum(min(dot(color,LUMA),FULL)*v for color,v in lamps) if bounded else lum
    hue = tuple(c/lum for c in rgb) if lum>1e-4 else (0,0,0)
    return response(reach) if lum>1e-4 else 0.0, hue


def aces(x):
    return min(max(x*(2.51*x+.03)/(x*(2.43*x+.59)+.14),0),1)


def output(albedo, lamps, bounded=True):
    reach,hue = aggregate(lamps,bounded)
    full = tuple(a*(1+4*h) for a,h in zip(albedo,hue))
    lum = dot(full,LUMA)
    hue_scale = aces(lum)/max(lum,1e-4)
    toned = tuple(.4*aces(c)+.6*c*hue_scale for c in full)
    return tuple(a+(b-a)*reach for a,b in zip(albedo,toned))


def main():
    shader = (ROOT/'assets/chroma/shaders/post/shade.fsh').read_text()
    source = re.sub(r'\s+','',re.sub(r'//[^\n]*','',shader))
    for expression in (
        '#defineLOOK_FULL_LUM3.0',
        'floatreachLum=0.0;',
        'unshadowedWeight=surfaceWeight;',
        'visibility=previousVisibility;',
        'surfaceWeight*=visibility;',
        'radiance+=lCol*(lInt*surfaceWeight);',
        'floatunshadowedLum=dot(lCol,vec3(0.2125,0.7154,0.0721))*lInt*unshadowedWeight;',
        'reachLum+=min(unshadowedLum,LOOK_FULL_LUM)*visibility;',
        'floatenv=smoothstep(0.0,LOOK_FULL_LUM,reachLum);',
        'vec3hueDir=radiance/radLum;',
    ):
        assert expression in source, 'Update response reference after shader change: '+expression
    assert source.index('unshadowedWeight=surfaceWeight;') < source.index('surfaceWeight*=visibility;')

    # Live dense pair t5.3175301 ->5.3371349: source moved .00718 blocks;
    # visibility0 ->2/16 caused green17 ->129. The unoccluded cyan luminance
    # below is independently derived from that source, wall normal and falloff.
    energy = 43.158941891589315
    old_step, new_step = response(energy/16), response(min(energy,FULL)/16)
    assert old_step>.97 and new_step<.012
    assert response(energy*.125)==1 and response(FULL*.125)<.043

    rng = random.Random(530)
    maximum_error = 0.0
    for _ in range(2000):
        colors = [tuple(10**rng.uniform(-4,2)*rng.random() for _ in range(3))
                  for _ in range(rng.randint(1,12))]
        albedo = tuple(rng.random()*.7 for _ in range(3))
        full = [(color,1.0) for color in colors]
        before,after = output(albedo,full,False),output(albedo,full)
        maximum_error = max(maximum_error,max(abs(a-b) for a,b in zip(before,after)))
        assert max(abs(a-b) for a,b in zip(before,after))<1e-12
        partial = [(color,rng.random()) for color in colors]
        assert aggregate(partial,False)[1]==aggregate(partial)[1], 'Visible colour mixture must stay unchanged'
        assert output(albedo,partial+[((0,0,1e6),0)])==output(albedo,partial), 'A closed lamp must not dim other lamps'
        assert output(albedo,[(color,0) for color in colors])==albedo

    # The rejected global visible/full ratio would dim this clear red to3/103.
    red,blue = (3/LUMA[0],0,0),(0,0,100/LUMA[2])
    assert aggregate([(red,1),(blue,0)])==aggregate([(red,1)])
    assert aggregate([(red,1),(blue,0)])[0]==1
    for energy in (.001,.1,1,3,43.16,1000):
        color = (0,energy/(LUMA[1]+LUMA[2]),energy/(LUMA[1]+LUMA[2]))
        values = [aggregate([(color,i/1024)])[0] for i in range(1025)]
        assert all(0<=v<=1 for v in values)
        assert all(a<=b for a,b in zip(values,values[1:]))
        # smoothstep's maximum slope is1.5: one of16 samples cannot produce
        # an almost fully lit pixel, regardless of this lamp's intensity.
        assert max(b-a for a,b in zip(values,values[64:]))<=1.5/16+1e-12

    print(f'PASS: high-gain one-sample reach {old_step:.6f}->{new_step:.6f}; '
          'two-sample reach1->0.042969; single-sample response step<=0.09375')
    print(f'PASS:2000 fully lit coloured mixtures unchanged (max error{maximum_error:.2g}); '
          'visible hue preserved, blocked sources isolated, all-blocked/monotonic/bounded response')


if __name__=='__main__':
    main()
