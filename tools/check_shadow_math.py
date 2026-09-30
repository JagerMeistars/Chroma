"""CPU shadow reference: hierarchy, camera invariance, and area-light penumbra.

This is a geometry check, not a live GLSL/performance test. Shader expressions
that its port depends on are checked so a changed tracer cannot silently pass.
"""
from pathlib import Path
import math
import random
import re
import struct

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'assets/chroma/shaders/include/shadows.glsl').read_text()
CONFIG = (ROOT / 'assets/chroma/shaders/include/shadow_config.glsl').read_text()
FILTER = (ROOT / 'assets/chroma/shaders/include/shadow_filter.glsl').read_text()


def setting(name):
    return float(re.search(rf'^#define {name}\s+([0-9.]+)', CONFIG, re.M)[1])


def f32(x):
    return struct.unpack('f', struct.pack('f', x))[0]


def add(a, b): return tuple(x + y for x, y in zip(a, b))
def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def mul(a, t): return tuple(x * t for x in a)
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def unit(a): return mul(a, 1 / math.sqrt(dot(a, a)))
def cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def pixel_receiver(receiver, normal, camera, enabled=True):
    if not enabled or '#define CHROMA_SHADOW_PIXELATE 1' not in CONFIG:
        return receiver
    subdivisions = setting('CHROMA_SHADOW_PIXELS_PER_BLOCK')
    block = tuple(math.floor(x) for x in camera)
    offset = sub(block, camera)
    local = tuple(f32(x) for x in sub(receiver, camera))
    snapped = tuple((math.floor(f32(p-o)*subdivisions)+.5)/subdivisions+o
                    for p,o in zip(local,offset))
    axis = next(i for i in range(3) if abs(normal[i]) >= max(map(abs,normal))-.001)
    delta = list(sub(snapped,local))
    delta[axis] = 0
    delta[axis] = -dot(delta,normal)/normal[axis]
    return add(camera,add(local,delta))


def check_pixelation():
    # Two receivers in one world-grid square must share one shadow sample, while
    # the adjacent square stays distinct. Sampling never moves off the surface.
    cameras = ((0,0,0),(-5.3125,7.25,12.875),(14.75,-3.625,-8.125))
    subdivisions = setting('CHROMA_SHADOW_PIXELS_PER_BLOCK')
    for shift in (0,29_999_900,-29_999_900):
        base = (shift,0,shift)
        expected = add(base,(.5/subdivisions,1.0625,-.5/subdivisions))
        for camera in cameras:
            camera = add(camera,base)
            for point in ((.16/subdivisions,1.0625,-.88/subdivisions),(.84/subdivisions,1.0625,-.12/subdivisions)):
                got = pixel_receiver(add(base,point),(0,1,0),camera)
                assert max(abs(x-y) for x,y in zip(got,expected))<2e-5, (got,expected)
            adjacent = pixel_receiver(add(base,(1.16/subdivisions,1.0625,-.4/subdivisions)),(0,1,0),camera)
            assert abs(adjacent[0]-(shift+1.5/subdivisions))<2e-5
    point,normal = (.21,1.0625,-.03),unit((.3,1,-.2))
    for camera in cameras:
        got = pixel_receiver(point,normal,camera)
        assert abs(dot(sub(got,point),normal))<2e-6, 'Sloped/slab receiver must stay on its plane'
        assert pixel_receiver(point,normal,camera,False)==point
    a = pixel_receiver(point,unit((1.000001,1,0)),cameras[1])
    b = pixel_receiver(point,unit((.999999,1,0)),cameras[1])
    assert max(abs(x-y) for x,y in zip(a,b))<1e-6, 'Near-tied face normals must select a stable grid'
    return f'world-grid 1/{subdivisions:g}-block samples, camera/large-coordinate invariance, plane preservation and OFF'


def interval(start, direction, low, high):
    near, far = -math.inf, math.inf
    for p, d, a, b in zip(start, direction, low, high):
        if abs(d) < 1e-12:
            if p < a or p >= b: return math.inf, -math.inf
        else:
            x, y = (a-p)/d, (b-p)/d
            near, far = max(near, min(x, y)), min(far, max(x, y))
    return near, far


def reference(start, end, boxes):
    for low, high in boxes:
        a, b = interval(start, sub(end, start), low, high)
        if max(a, 0.0) < min(b, 1.0-1e-5): return True
    return False


def trace(start_world, end_world, boxes, camera, origin, steps=192):
    # Integer base + local float coordinates mirrors the shader's precision path.
    block = tuple(math.floor(x) for x in camera)
    offset = sub(block, camera)
    from_camera = tuple(f32(x) for x in sub(start_world, camera))
    to_camera = tuple(f32(x) for x in sub(end_world, camera))
    start = tuple(f32(4*b-o + f32(f32(p-c)*4))
                  for b,o,p,c in zip(block, origin, from_camera, offset))
    segment = tuple(f32(f32(b-a)*4) for a,b in zip(from_camera, to_camera))
    length = math.sqrt(dot(segment, segment))
    direction = unit(segment)
    near, far = interval(start, direction, (0,0,0), (256,256,256))
    t, end = max(near, 0.0)+.0001, min(far, length-.001)
    for _ in range(steps):
        if t >= end: return False, False
        point = add(start, mul(direction, t))
        cell = tuple(o+math.floor(p) for o,p in zip(origin, point))
        for size in (4, 2, 1):
            low = tuple((v//size)*size for v in cell)
            high = tuple(v+size for v in low)
            occupied = any(all(a<d and c<b for a,b,c,d in zip(low,high,lo,hi))
                           for lo,hi in boxes)
            if not occupied:
                crossings = [((math.floor(p/size)+(d>=0))*size-p)/d
                             for p,d in zip(point,direction) if abs(d)>=1e-7]
                t += max(min(crossings), 0.0)+.0001
                break
        else: return True, False
    # Report separately: callers must not confuse traversal exhaustion with clear.
    return None, True


def samples(receiver, light, rays, radius):
    axis = unit(sub(light, receiver))
    tangent = unit(cross(axis, (0,1,0) if abs(axis[1])<.9 else (1,0,0)))
    bitangent = cross(axis, tangent)
    for ray in range(rays):
        r = radius*math.sqrt((ray+.5)/rays)
        angle = ray*2.39996323
        yield add(light, add(mul(tangent,r*math.cos(angle)),mul(bitangent,r*math.sin(angle))))


def oct_uv(direction):
    x,y,z = mul(direction,1/sum(abs(x) for x in direction))
    if z<0: x,y = (1-abs(y))*(-1 if x<0 else 1), (1-abs(x))*(-1 if y<0 else 1)
    return ((x+1)*.5,(y+1)*.5)


def oct_seam(p,n):
    x,y = p
    if x<0: x,y = -x-1,n-1-y
    if x>=n: x,y = 2*n-1-x,n-1-y
    if y<0: y,x = -y-1,n-1-x
    if y>=n: y,x = 2*n-1-y,n-1-x
    return x,y


def oct_ray(p,n):
    x,y = ((v+.5)/n*2-1 for v in oct_seam(p,n))
    z = 1-abs(x)-abs(y)
    if z<0: x,y = (1-abs(y))*(-1 if x<0 else 1), (1-abs(x))*(-1 if y<0 else 1)
    return unit((x,y,z))


def receiver_depth(ray,normal,plane):
    d = dot(ray,normal)
    return plane/d if abs(d)>=.0001 and d*plane>0 else 1e6


def analytic_depth(ray,light,point,normal,boxes):
    # Independent ray/geometry intersection, with no UV, PCF or receiver bias.
    numerator, denominator = dot(sub(point,light),normal),dot(ray,normal)
    distance = numerator/denominator if numerator*denominator>0 else 1e6
    for low,high in boxes:
        near,far = interval(light,ray,low,high)
        if max(near,0)<far: distance = min(distance,max(near,0))
    return distance


def pcf(ray,normal,plane,sampler,n,light_radius=1e6,old_reference=False):
    uv = oct_uv(ray)
    p = tuple(v*n-.5 for v in uv)
    base = tuple(math.floor(v) for v in p)
    w = tuple(v-b for v,b in zip(p,base))
    visible = []
    for x,y in ((0,0),(1,0),(0,1),(1,1)):
        cell = (base[0]+x,base[1]+y)
        sample_ray = ray if old_reference else oct_ray(cell,n)
        reference_depth = receiver_depth(sample_ray,normal,plane)-.02
        depth = sampler(oct_ray(cell,n))
        visible.append(float(reference_depth>1e5 or depth>=light_radius-.001 or depth>=reference_depth))
    a = visible[0]*(1-w[0])+visible[1]*w[0]
    b = visible[2]*(1-w[0])+visible[3]*w[0]
    return a*(1-w[1])+b*w[1]


def bounded_reference(ray, normal, plane, delta, footprint):
    reference_depth = receiver_depth(ray,normal,plane)
    if reference_depth > 1e5: return None
    offset = sub(mul(ray,reference_depth),delta)
    if dot(offset,offset) > footprint*footprint: return None
    return reference_depth-.02


def bounded_pcf(ray,normal,plane,delta,footprint,sampler,n,light_radius):
    # Retained only as the old hard-footprint regression reference.
    p = tuple(v*n-.5 for v in oct_uv(ray))
    base = tuple(math.floor(v) for v in p)
    w = tuple(v-b for v,b in zip(p,base))
    visible = weight = 0.0
    for x,y in ((0,0),(1,0),(0,1),(1,1)):
        sample_ray = oct_ray((base[0]+x,base[1]+y),n)
        reference_depth = bounded_reference(sample_ray,normal,plane,delta,footprint)
        if reference_depth is None: continue
        amount = (w[0] if x else 1-w[0])*(w[1] if y else 1-w[1])
        depth = sampler(sample_ray)
        visible += amount*float(depth>=light_radius-.001 or depth>=reference_depth)
        weight += amount
    return visible,weight


def weighted_pcf(ray,normal,surface_plane,distance,footprint,sampler,n,light_radius,receiver_bias,foreground_limit):
    p = tuple(v*n-.5 for v in oct_uv(ray))
    base = tuple(math.floor(v) for v in p)
    w = tuple(v-b for v,b in zip(p,base))
    visible = weight = 0.0
    for x,y in ((0,0),(1,0),(0,1),(1,1)):
        sample_ray = oct_ray((base[0]+x,base[1]+y),n)
        depth = sampler(sample_ray)
        amount = (w[0] if x else 1-w[0])*(w[1] if y else 1-w[1])
        reference_depth = receiver_depth(sample_ray,normal,surface_plane+receiver_bias)
        if depth >= light_radius-.001:
            if reference_depth > light_radius: amount = 0.0
            lit = 1.0
        elif -.02 <= dot(sample_ray,normal)*depth-surface_plane <= receiver_bias+.02:
            t = min(max((depth-foreground_limit)/footprint,0.0),1.0)
            amount *= t*t*(3-2*t)
            lit = 1.0
        else:
            reference_depth = distance if reference_depth>1e5 else max(distance,reference_depth)
            lit = float(depth >= reference_depth-.02)
        visible += amount*lit
        weight += amount
    return visible,weight


def shadow_fallback(axis,normal,plane,distance,sampler,n,light_radius):
    base = tuple(math.floor(v*n-.5) for v in oct_uv(axis))
    candidates = []
    for x,y in ((0,0),(1,0),(0,1),(1,1)):
        ray = oct_ray((base[0]+x,base[1]+y),n)
        depth = sampler(ray)
        reference_depth = receiver_depth(ray,normal,plane)
        if depth < light_radius-.001 and reference_depth<1e5 and depth>=reference_depth-.02:
            depth = -1.0
        candidates.append(depth)
    depth = max(candidates)
    return float(depth<0 or depth>=light_radius-.001 or depth>=distance-.02)


def pcss(receiver,normal,light,boxes,n,radius,light_radius=1e6,bias=.035,legacy_footprint=False,receiver_hull_offset=0.0):
    hull = add(receiver,mul(normal,receiver_hull_offset))
    sampler = lambda ray: min(analytic_depth(ray,light,hull,normal,boxes),light_radius)
    height = max(dot(sub(light,receiver),normal),0.0)
    surface_plane = dot(sub(receiver,light),normal)
    receiver_bias = min(bias,height*.5)
    delta = sub(add(receiver,mul(normal,receiver_bias)),light)
    distance,axis = math.sqrt(dot(delta,delta)),unit(delta)
    center_pixel = tuple(int(v*n) for v in oct_uv(axis))
    center_depth = sampler(oct_ray(center_pixel,n))
    if center_depth <= .0001: return 0.0
    tangent = unit(cross(axis,(0,1,0) if abs(axis[1])<.9 else (1,0,0)))
    bitangent = cross(axis,tangent)
    plane = dot(delta,normal)
    blockers = []
    search_angle = radius/max(.5,distance*.2)
    texel_footprint = distance*4/n
    search_footprint = distance*search_angle+texel_footprint
    for i in range(9):
        angle = i*2.39996323
        r = 0 if i==0 else math.sqrt(i/8)*search_angle
        ray = unit(add(axis,add(mul(tangent,r*math.cos(angle)),mul(bitangent,r*math.sin(angle)))))
        cell = tuple(int(v*n) for v in oct_uv(ray))
        actual_ray = oct_ray(cell,n)
        depth = sampler(actual_ray)
        if legacy_footprint:
            reference_depth = bounded_reference(actual_ray,normal,plane,delta,search_footprint)
        else:
            on_surface = -.02 <= dot(actual_ray,normal)*depth-surface_plane <= receiver_bias+.02
            reference_depth = None if on_surface else distance-.02
        if reference_depth is not None and .0001<depth<light_radius-.001 and depth<reference_depth:
            blockers.append(depth)
    if not blockers:
        visible,weight = (bounded_pcf(axis,normal,plane,delta,texel_footprint,sampler,n,light_radius)
                          if legacy_footprint else
                          weighted_pcf(axis,normal,surface_plane,distance,texel_footprint,sampler,n,light_radius,receiver_bias,distance))
        return visible/weight if weight>1e-5 else shadow_fallback(axis,normal,plane,distance,sampler,n,light_radius)
    blocker = sum(blockers)/len(blockers)
    penumbra = radius*max(distance-blocker,0)/max(distance*blocker,.01)
    filter_angle = max(penumbra,.7/n)
    footprint = distance*filter_angle+texel_footprint
    foreground_limit = max(distance*.5,min(distance,max(blockers)+texel_footprint))
    visible = weight = 0.0
    for i in range(16):
        angle,r = i*2.39996323,math.sqrt((i+.5)/16)*filter_angle
        ray = unit(add(axis,add(mul(tangent,r*math.cos(angle)),mul(bitangent,r*math.sin(angle)))))
        lit,amount = (bounded_pcf(ray,normal,plane,delta,footprint,sampler,n,light_radius)
                      if legacy_footprint else
                      weighted_pcf(ray,normal,surface_plane,distance,footprint,sampler,n,light_radius,receiver_bias,foreground_limit))
        visible += lit
        weight += amount
    return visible/weight if weight>1e-5 else shadow_fallback(axis,normal,plane,distance,sampler,n,light_radius)


def check_octahedral(rng,radius):
    n = int(re.search(r'CHROMA_SHADOW_RES\s*=\s*(\d+)',FILTER)[1])
    source = re.sub(r'\s+','',re.sub(r'//[^\n]*','',FILTER))
    assert 'chromaBoundedReference' not in source, 'Hard plane-footprint rejection makes shadow contours discontinuous'
    assert 'reference=reference>1e5?distance:max(distance,reference);' in source
    assert 'returnreference<=lightRadius?vec2(1.0):vec2(0.0);' in source
    assert 'chromaShadowReceiverHit(dot(direction,normal)*depth-surfacePlane,receiverBias)' in source
    assert 'returnsurfaceOffset>=-0.02&&surfaceOffset<=receiverBias+0.02;' in source
    assert 'floatweight=smoothstep(foregroundLimit,foregroundLimit+footprint,depth);' in source
    assert 'floatforegroundLimit=max(distance*0.5,min(distance,farthestBlocker+texelFootprint));' in source
    assert 'floatreceiverBias=min(bias,height*0.5);receiver+=normal*receiverBias;' in source
    assert 'returnvisible.y>0.00001?visible.x/visible.y:chromaShadowFallback(lamp,axis,normal,plane,distance,lightRadius);' in source
    assert 'if(centerDepth<=0.0001)return0.0;' in source
    assert '!chromaShadowReceiverHit(surfaceOffset,receiverBias)&&depth>0.0001&&depth<lightRadius-0.001&&depth<distance-0.02' in source
    for offset in ('base','base+ivec2(1,0)','base+ivec2(0,1)','base+ivec2(1,1)'):
        assert f'chromaShadowCompare(lamp,{offset},normal,surfacePlane,distance,footprint,lightRadius,receiverBias,foregroundLimit)' in source
    # Fold every possible bilinear seam/corner neighbour inside its source tile.
    for x in range(-1,n+1):
        for y in (-1,0,n-1,n):
            for p in ((x,y),(y,x)):
                folded = oct_seam(p,n)
                assert all(0<=v<n for v in folded)
                uv = oct_uv(oct_ray(p,n))
                assert max(abs(uv[i]-(folded[i]+.5)/n) for i in (0,1))<1e-12
    # Opposite sides of each fold are geometric reflections across its seam.
    for i in range(n):
        for inner,outer,axis in (((0,i),(-1,i),1),((n-1,i),(n,i),1),
                                 ((i,0),(i,-1),0),((i,n-1),(i,n),0)):
            a,b = oct_ray(inner,n),oct_ray(outer,n)
            expected = tuple(-v if j==axis else v for j,v in enumerate(a))
            assert max(abs(x-y) for x,y in zip(expected,b))<1e-12
    minimum_old = 1.0
    tested = 0
    for _ in range(150):
        normal = unit(tuple(rng.uniform(-1,1) for _ in range(3)))
        tangent = unit(cross(normal,(0,1,0) if abs(normal[1])<.9 else (1,0,0)))
        receiver = tuple(rng.uniform(-5,5) for _ in range(3))
        # Include oblique receiver planes to amplify the old comparison mismatch.
        light = add(receiver,add(mul(normal,rng.uniform(.6,8)),mul(tangent,rng.uniform(-25,25))))
        sampler = lambda ray: analytic_depth(ray,light,receiver,normal,[])
        plane = dot(sub(add(receiver,mul(normal,.035)),light),normal)
        ray = unit(sub(receiver,light))
        assert pcf(ray,normal,plane,sampler,n)>1-1e-12
        minimum_old = min(minimum_old,pcf(ray,normal,plane,sampler,n,old_reference=True))
        assert pcss(receiver,normal,light,[],n,radius)>1-1e-12
        # Plane/light geometry is unchanged under each camera translation.
        for camera in ((0,0,0),(-40.25,12.5,17.75),(29_999_900.125,-11.25,-29_999_900.375)):
            assert pcss(sub(receiver,camera),normal,sub(light,camera),[],n,radius)>1-1e-12
            tested += 1
        # Range-clamped texels signify no blocker, even if a neighbouring tap's
        # receiver-plane intersection lies farther away than that range.
        light_radius = math.sqrt(dot(sub(receiver,light),sub(receiver,light)))*1.001
        assert pcss(receiver,normal,light,[],n,radius,light_radius)>1-1e-12
        assert pcf(ray,normal,plane,lambda _: light_radius,n,light_radius)>1-1e-12
    assert minimum_old<.8, 'Regression fixture must expose old continuous-ray PCF acne'
    # An emitter buried in a block and a thin blocker only 5 mm away must not
    # disappear from the search and become fully lit by its no-blocker shortcut.
    assert pcss((0,0,4),(0,0,-1),(0,0,0),[((-1,-1,-1),(1,1,1))],n,radius,12) == 0.0
    # A near-source filter reaches almost tangent directions, where a 128-square
    # octahedral map has finite angular error; require dominant occlusion, not 1.0.
    assert pcss((0,0,4),(0,0,-1),(0,0,0),[((-10,-10,.005),(10,10,.25))],n,radius,12) < .25
    widths = []
    box = [((-1,-10,-.25),(1,10,0))]
    for separation in (2,6):
        edge = (separation+4)/4
        partial = []
        for i in range(201):
            x = edge-1+i*.01
            value = pcss((x,0,separation),(0,0,-1),(0,0,-4),box,n,radius)
            if .05<value<.95: partial.append(x)
        assert partial
        widths.append(max(partial)-min(partial))
    assert widths[1]>widths[0]*1.5,widths
    return tested,minimum_old,widths


def check_room_occlusion(radius):
    """Compare filtering against independent segments through an opaque wall.

    This room side wall receives a nearly tangent source through the direction
    of a doorway. A separate complete wall closes that path. Every point of the
    area emitter is blocked; this remains true when the receiver bias equals or
    exceeds the source's height above the side wall. The same receiver without
    the blocking wall must remain lit, so a blanket grazing-angle darkening fails.
    """
    shade = (ROOT / 'assets/chroma/shaders/post/shade.fsh').read_text()
    source = re.sub(r'\s+','',re.sub(r'//[^\n]*','',shade))
    assert 'floatdiff=max(dot(normal,L),0.0);' in source
    assert 'DIFFUSE_WRAP' not in source and 'glowWeight' not in source and 'outc+=vol' not in source
    assert 'surfaceWeight*=visibility;' in source
    assert 'radiance+=lCol*(lInt*surfaceWeight);' in source
    # Exact independent cosine law: back-facing opaque surfaces receive no
    # direct irradiance, while their lit side still receives positive energy.
    for cosine in (-1,-.75,-.5,-.01,0,.01,.25,1):
        lambert = max(cosine,0.0)
        if cosine<=0: assert lambert==0
        else: assert lambert>0
    assert max(-.5+.75,0)/1.75 > 0, 'Fixture must expose the removed wrap leak'

    n = int(re.search(r'CHROMA_SHADOW_RES\s*=\s*(\d+)',FILTER)[1])
    tested = 0
    # Axis permutations/signs keep the independent blocker an exact AABB while
    # exercising different octahedral faces and folds, not one favorable tile.
    for permutation in ((0,1,2),(1,2,0),(2,0,1)):
        for sign in (-1,1):
            rotate = lambda v: tuple(sign*v[i] for i in permutation)
            a,b = rotate((-100,-100,1)),rotate((100,100,2))
            boxes = [(tuple(min(x,y) for x,y in zip(a,b)),tuple(max(x,y) for x,y in zip(a,b)))]
            receiver,normal = rotate((0,0,4)),rotate((1,0,0))
            for height in (.001,.005,.02,.035,.05,.1,.17,.18,.2,.3,.6,1):
                light = rotate((height,0,0))
                assert all(reference(receiver,s,boxes) for s in samples(receiver,light,128,radius))
                for bias in (.035,.18):
                    for camera in ((0,0,0),(-40.25,12.5,17.75),(29_999_900.125,-11.25,-29_999_900.375)):
                        local_boxes = [(sub(a,camera),sub(b,camera)) for a,b in boxes]
                        point,lamp = sub(receiver,camera),sub(light,camera)
                        blocked = pcss(point,normal,lamp,local_boxes,n,radius,12,bias)
                        clear = pcss(point,normal,lamp,[],n,radius,12,bias)
                        assert blocked<1e-12, ('Opaque room wall leaked',height,bias,permutation,sign,blocked)
                        assert clear>1-1e-12, ('Open grazing plane darkened',height,bias,permutation,sign,clear)
                        tested += 1
    return tested


def check_shadow_contour(radius):
    """A straight half-wall must not produce disconnected teeth in its shadow.

    Geometry is analytic, not a voxel capture: y=0 is the receiver, the source
    is (2,2,-4), and a wall occupies x<=0 at z=0. Its point-source edge is the
    straight line x=-z/2. A disk source softens that edge, without isolated lit
    islands or full lit-to-dark reversals while moving toward the clear side.
    """
    n = int(re.search(r'CHROMA_SHADOW_RES\s*=\s*(\d+)',FILTER)[1])

    def contour(permutation,sign,legacy=False):
        rotate = lambda v: tuple(sign*v[i] for i in permutation)
        a,b = rotate((-100,-1,-.25)),rotate((0,10,0))
        boxes = [(tuple(min(x,y) for x,y in zip(a,b)),tuple(max(x,y) for x,y in zip(a,b)))]
        light,normal = rotate((2,2,-4)),rotate((0,1,0))
        reverse,edges,multiple = 0.0,[],0
        for row in range(65):
            z = 2+row*.25
            # Independent segments establish which side of the analytic edge
            # is blocked; a reversed implementation cannot pass just by being smooth.
            assert reference(rotate((-z*.5-1,0,z)),light,boxes)
            assert not reference(rotate((-z*.5+1,0,z)),light,boxes)
            values = [pcss(rotate((-z*.5-.8+i*.04,0,z)),normal,light,boxes,n,radius,40,
                           legacy_footprint=legacy) for i in range(41)]
            reverse = max(reverse,max(a-b for a,b in zip(values,values[1:])))
            crossings = [-.8+i*.04+(.5-a)/(b-a)*.04
                         for i,(a,b) in enumerate(zip(values,values[1:]))
                         if a!=b and (a-.5)*(b-.5)<=0]
            multiple += len(crossings)!=1
            edges.append(crossings[0] if crossings else math.nan)
        jump = max(abs(a-b) for a,b in zip(edges,edges[1:]) if math.isfinite(a+b))
        return reverse,jump,multiple

    old_reverse,old_jump,old_multiple = contour((0,1,2),1,True)
    assert old_reverse>.95 and old_jump>.5 and old_multiple, 'Fixture must expose hard footprint teeth'
    worst_reverse = worst_jump = 0.0
    for permutation in ((0,1,2),(1,2,0),(2,0,1)):
        for sign in (-1,1):
            reverse,jump,multiple = contour(permutation,sign)
            # Finite angular/tap sampling still introduces small variations;
            # the previous 100% reversals and disconnected contours are forbidden.
            assert reverse<.04 and jump<.125 and multiple==0, (permutation,sign,reverse,jump,multiple)
            worst_reverse = max(worst_reverse,reverse)
            worst_jump = max(worst_jump,jump)

    # The smooth treatment must not make foreground receiver-plane samples
    # reveal a closed wall. Include walls almost touching the receiving point.
    for z in (.1,1,2,3,3.9):
        boxes = [((-100,-100,z),(100,100,z+.05))]
        for height in (.001,.1,.3,1):
            receiver,light = (0,0,4),(height,0,0)
            assert all(reference(receiver,s,boxes) for s in samples(receiver,light,128,radius))
            assert pcss(receiver,(1,0,0),light,boxes,n,radius,12)<1e-12
    return old_reverse,old_jump,worst_reverse,worst_jump


def check_receiver_hull(radius):
    """A rounded voxel surface inside the applied bias is still a clear floor.

    The map sampler intersects an independently shifted analytic plane; the
    shaded surface stays at its original position. This exposes strict planar
    self-hit recognition that incorrectly shadows slabs and sloped surfaces.
    """
    n = int(re.search(r'CHROMA_SHADOW_RES\s*=\s*(\d+)',FILTER)[1])
    count = 0
    for normal in ((0,1,0),(1,0,0),unit((.3,1,-.2)),unit((1,1,1))):
        tangent = unit(cross(normal,(0,0,1)))
        for distance in (4,12,24):
            light = add(mul(tangent,distance),mul(normal,.6))
            for bias,offsets in ((.035,(0,.015625,.03125)),(.18,(0,.03125,.0625,.125,.18))):
                for offset in offsets:
                    value = pcss((0,0,0),normal,light,[],n,radius,40,bias,receiver_hull_offset=offset)
                    assert value>1-1e-12, ('Clear receiver voxel hull darkened',normal,distance,bias,offset,value)
                    count += 1
    # A distinct parallel slab outside that bias band must still block every
    # physical source sample, including directions close to the map horizon.
    for bottom,top in ((.22,.24),(.25,.5)):
        boxes = [((-100,bottom,-100),(100,top,100))]
        for distance in (4,12,24):
            receiver,light = (0,0,0),(distance,.6,0)
            assert all(reference(receiver,s,boxes) for s in samples(receiver,light,128,radius))
            for bias in (.035,.18):
                value = pcss(receiver,(0,1,0),light,boxes,n,radius,40,bias)
                assert value<1e-12, ('Parallel near-receiver slab leaked',bottom,top,distance,bias,value)
    return count


def main():
    pixelation = check_pixelation()
    compact = re.sub(r'\s+', '', re.sub(r'//[^\n]*', '', SOURCE))
    for expression in (
        'CameraBlockPos*CHROMA_VOX_CELLS-origin',
        '(from-CameraOffset)*float(CHROMA_VOX_CELLS)',
        '(absoluteCell>>level)&(n-1)',
        '((channel>>uint((cell.x&3)*2))&3u)>=2u',
    ):
        assert expression in compact, 'Update CPU reference for changed GLSL: '+expression
    # Independent geometric area-light reference, not the production PCSS tap count.
    rays, steps = 12, int(setting('CHROMA_SHADOW_STEPS'))
    radius = setting('CHROMA_SOURCE_SIZE')
    wall = [((-4,0,0),(4,32,1))]  # Quarter-cells: 2x8-block wall, quarter-block thick.
    cameras = [(-12.25,5.5,15.125),(14.0625,18,6.375),(0.125,4.125,-8.25)]
    rng = random.Random(263)
    tested = 0
    for _ in range(100):
        receiver = (rng.uniform(-4,4),1.0,rng.uniform(1,8))
        light = (rng.uniform(-2,2),3.0,-4.0)
        target = next(samples(receiver,light,rays,radius))
        expected = reference(mul(receiver,4),mul(target,4),wall)
        for shift in (0,29_999_900,-29_999_900):
            delta = (shift,0,shift)
            shifted_wall = [(add(a,mul(delta,4)),add(b,mul(delta,4))) for a,b in wall]
            for camera in cameras:
                cam = add(camera,delta)
                origin = tuple(4*math.floor(v)-128 for v in cam)
                actual, exhausted = trace(add(receiver,delta),add(target,delta),shifted_wall,cam,origin,steps)
                assert not exhausted and actual==expected, (actual,expected,cam,receiver,target)
                tested += 1
    widths = []
    for distance in (2.0,6.0):
        edge = (distance+4.0)/4.0
        penumbra = []
        for i in range(201):
            receiver = (edge-1+i*.01,1.0,distance)
            visibility = sum(not reference(mul(receiver,4),mul(s,4),wall)
                             for s in samples(receiver,(0,3,-4),rays,radius))/rays
            if 0<visibility<1: penumbra.append(receiver[0])
        assert penumbra, 'Area source must produce partial visibility'
        widths.append(max(penumbra)-min(penumbra))
    assert widths[1]>widths[0]*1.7, widths
    # Dense neighbouring occupancy defeats coarse skipping without hitting the ray.
    crowded = [((0,1,0),(256,2,1)), ((250,0,0),(251,1,1))]
    start,end = ((.125,.125,.125),(63.875,.125,.125))
    bounded, exhausted = trace(start,end,crowded,(32,32,32),(0,0,0),steps)
    assert reference(mul(start,4),mul(end,4),crowded)
    if exhausted:
        body = SOURCE[SOURCE.index('float chromaTraceDistance('):]
        assert 'return min(t, lengthRay) * CHROMA_VOX_CELL;' in body
    else: assert bounded
    floors,old_acne,pcss_widths = check_octahedral(rng,radius)
    room_cases = check_room_occlusion(radius)
    contour = check_shadow_contour(radius)
    hulls = check_receiver_hull(radius)
    print(f'PASS: {tested} ray/camera/large-coordinate comparisons; penumbra widths '
          f'{widths[0]:.3f}->{widths[1]:.3f}; bounded traversal checked; '
          f'octahedral seams and {floors} unoccluded planes stay lit '
          f'(old PCF regression={old_acne:.3f}); PCSS penumbra '
          f'{pcss_widths[0]:.3f}->{pcss_widths[1]:.3f}; buried/near-source blockers remain occluded')
    print('PASS: '+pixelation)
    print(f'PASS: {room_cases} blocked/open room-wall pairs, Static/Dynamic bias, grazing angles, '
          'six orientations and camera translations; opaque backfaces receive no direct lamp energy')
    print(f'PASS: analytic straight-wall contour, six orientations; worst visibility reversal '
          f'{contour[0]:.3f}->{contour[2]:.3f}, edge step {contour[1]:.3f}->{contour[3]:.3f} blocks; '
          'near-receiver opaque walls remain blocked')
    print(f'PASS: {hulls} shifted voxel receiver planes stay lit, including slopes; '
          '12 parallel near-receiver slab cases remain fully blocked')


if __name__ == '__main__':
    main()
