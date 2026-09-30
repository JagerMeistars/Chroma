"""CPU light-grid regression; native shader/game checks remain separate."""
from pathlib import Path
import math
import random
import re

from check_shadow_math import add, sub, mul, dot, unit, pixel_receiver, setting

ROOT = Path(__file__).resolve().parents[1]


def smooth(a, b, value):
    t = max(0.0, min(1.0, (value-a)/(b-a)))
    return t*t*(3-2*t)


def weight(receiver, normal, light, radius, shape):
    delta = sub(light, receiver)
    distance = math.sqrt(dot(delta, delta))
    if distance >= radius: return 0.0
    direction = mul(delta, 1/max(distance, 1e-4))
    fall = 1-smooth(.15, 1, distance/radius)
    if 1 <= shape <= 3:
        inner, outer = ((.985,.96),(.95,.88),(.88,.74))[shape-1]
        fall *= smooth(outer, inner, dot(mul(direction,-1),unit((-.25,-1,-.05))))
    elif shape == 4:
        fall *= smooth(0,.25,dot(mul(direction,-1),(0,-1,0)))
    return max(dot(normal,direction),0)*fall


def check():
    shade = re.sub(r'\s+', '', (ROOT/'assets/chroma/shaders/post/shade.fsh').read_text())
    tiles = re.sub(r'\s+', '', (ROOT/'assets/chroma/shaders/post/tile_masks.fsh').read_text())
    assert 'vec3lightReceiver=fragPos;#ifCHROMA_SHADOW_PIXELATE' in shade
    assert 'lightReceiver=transpose(cameraInvRot)*worldReceiver;' in shade
    assert 'vec3toL=lPos-lightReceiver;' in shade, 'Light still bypasses the shared grid'
    assert 'radius+=1.25/float(max(CHROMA_SHADOW_PIXELS_PER_BLOCK,1));' in tiles
    subdivisions = setting('CHROMA_SHADOW_PIXELS_PER_BLOCK')
    cases = 0
    for normal in ((0,1,0),unit((.3,1,-.2))):
        # Independent surface equation, same two tangent-grid coordinates.
        points = [(x,1-(normal[0]*x+normal[2]*z)/normal[1],z)
                  for x,z in ((.1/subdivisions,.2/subdivisions),(.8/subdivisions,.9/subdivisions))]
        light = (.5,3,.1)
        for shift in (0,29_999_900,-29_999_900):
            base = (shift,0,shift)
            for camera in ((0,0,0),(8.125,4.5,-6.375),(-9.75,2,7.25)):
                snapped = [pixel_receiver(add(p,base),normal,add(camera,base)) for p in points]
                for shape in range(5):
                    values = [weight(p,normal,add(light,base),6,shape) for p in snapped]
                    assert abs(values[0]-values[1])<2e-6, (shape,values)
                    off = [weight(pixel_receiver(p,normal,camera,False),normal,light,6,shape) for p in points]
                    assert abs(off[0]-off[1])>1e-5, 'OFF must keep continuous light variation'
                    cases += 1
    # Snapping a sloped receiver can move it outside the original light bound.
    # The tile culler must conservatively include that whole grid square.
    rng = random.Random(263)
    bound = 1.25/subdivisions
    for _ in range(2000):
        normal = unit(tuple(rng.uniform(-1,1) for _ in range(3)))
        point = tuple(rng.uniform(-2,2) for _ in range(3))
        snapped = pixel_receiver(point,normal,(.25,-.5,.125))
        displacement = sub(snapped,point)
        assert math.sqrt(dot(displacement,displacement)) < bound
    print(f'PASS: {cases} shared light-grid samples across five shapes, flat/sloped receivers, '
          'camera and large-coordinate changes; OFF preserves continuous falloff; 2000 tile-padding bounds')


if __name__ == '__main__': check()
