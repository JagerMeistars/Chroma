"""CPU/source checks for bounded entity screen-contact shadows. No GPU/game/FPS.
Analytic finite planes independently supply the visible depth/tag buffer.
Run: python -B tools/check_entity_shadow.py
"""
from pathlib import Path
import math
import re

ROOT=Path(__file__).resolve().parents[1]
SIZE=(640,360)
IDENTITY=((1.,0.,0.,0.),(0.,1.,0.,0.),(0.,0.,1.,0.),(0.,0.,0.,1.))

def add(a,b):return tuple(x+y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def mul(a,s):return tuple(x*s for x in a)
def dot(a,b):return sum(x*y for x,y in zip(a,b))
def length(a):return math.sqrt(dot(a,a))
def unit(a):return mul(a,1/length(a))
def mv(a,v):return tuple(dot(row,v) for row in a)
def mm(a,b):return tuple(tuple(sum(a[i][k]*b[k][j] for k in range(4)) for j in range(4)) for i in range(4))
def inverse(m):
    a=[list(row)+list(eye) for row,eye in zip(m,IDENTITY)]
    for c in range(4):
        k=max(range(c,4),key=lambda i:abs(a[i][c]));a[c],a[k]=a[k],a[c]
        a[c]=[v/a[c][c] for v in a[c]]
        for r in range(4):
            if r!=c:
                f=a[r][c];a[r]=[x-f*y for x,y in zip(a[r],a[c])]
    return tuple(tuple(row[4:]) for row in a)
def transform(m,p):
    v=mv(m,(*p,1.));return tuple(x/v[3] for x in v[:3])
def project_clip(c):
    if not all(math.isfinite(v) for v in c) or c[3]<=1e-6 or not 0<c[2]<c[3]:return None
    return ((c[0]/c[3]+1)*.5,(c[1]/c[3]+1)*.5),c[2]/c[3]
def project(m,p):return project_clip(mv(m,(*p,1.)))
def unproject(inv,uv,depth):return transform(inv,(uv[0]*2-1,uv[1]*2-1,depth))
def smooth(a,b,x):
    t=max(0.,min(1.,(x-a)/(b-a)));return t*t*(3-2*t)
def tag(alpha):return math.floor(alpha*255+.5)==1

# Infinite reversed-Z projection composed with an arbitrary native bob transform.
P=((1.05,0.,0.,0.),(0.,1.8666666666667,0.,0.),(0.,0.,0.,.05),(0.,0.,-1.,0.))

def raster(proj,planes):
    inv=inverse(proj)
    def sample(pixel):
        uv=tuple((p+.5)/n for p,n in zip(pixel,SIZE))
        start=unproject(inv,uv,.9);direction=unit(sub(unproject(inv,uv,.1),start))
        closest=float('inf');result=(0.,1.)
        for point,normal,covered,alpha in planes:
            den=dot(normal,direction)
            if abs(den)<1e-12:continue
            t=dot(normal,sub(point,start))/den
            if t<0 or t>=closest:continue
            hit=add(start,mul(direction,t))
            if not covered(hit):continue
            value=project(proj,hit)
            if value is not None:closest=t;result=(value[1],alpha)
        return result
    return sample


def trace(receiver,normal,light,proj,sample,receiver_tag=False,world=1.,maximum=4.,steps=24,refine=True,hoist=True):
    if receiver_tag or world<=0:return world,0,'skip'
    distance=length(sub(light,receiver))
    if not math.isfinite(distance) or distance<=.0001:return world,0,'degenerate'
    origin=add(receiver,mul(normal,min(.01,distance*.1)))
    segment=sub(light,origin);distance=length(segment)
    if not math.isfinite(distance) or distance<=.0001:return world,0,'degenerate'
    direction=unit(segment);limit=min(max(maximum,0.),distance-.0001)
    if limit<=.0001:return world,0,'range'
    steps=max(1,min(24,steps));inv=inverse(proj)
    clip_origin=mv(proj,(*origin,1.));clip_direction=mv(proj,(*direction,0.))
    def probe(travel):
        q=project_clip(add(clip_origin,mul(clip_direction,travel))) if hoist else project(proj,add(origin,mul(direction,travel)))
        if q is None:return -1,None,'clip'
        uv,raydepth=q
        if any(v<0 or v>=1 for v in uv):return -1,None,'offscreen'
        pixel=tuple(math.floor(v*n) for v,n in zip(uv,SIZE));depth,alpha=sample(pixel)
        if depth<=1e-6:return 0,None,'sky'
        if depth>=.999999 or not math.isfinite(depth):return -1,None,'interface'
        return 1,(uv,raydepth,pixel,depth,alpha),'valid'
    def hit(data):
        uv,raydepth,pixel,depth,alpha=data
        if depth<raydepth or not tag(alpha):return None
        centre=tuple((p+.5)/n for p,n in zip(pixel,SIZE))
        scene=unproject(inv,centre,depth);at=unproject(inv,centre,raydepth)
        gap=length(sub(at,scene))
        if not math.isfinite(gap) or gap>.15:return None
        along=dot(sub(scene,origin),direction)
        if along<=.0001 or along>=limit or along>=distance-.0001:return None
        edge=min(min(v,1-v)*n for v,n in zip(uv,SIZE))
        opacity=smooth(0.,8.,edge)*(1-smooth(.75*maximum,maximum,along))
        return world*(1-opacity)
    previous=None;refinement_budget=8
    for i in range(steps):
        travel=(i+.5)*(limit/steps);status,data,reason=probe(travel)
        if status<0:return world,i+1,reason
        if status==0:previous=None;continue
        behind=data[3]>=data[1];entity=behind and tag(data[4])
        if refine and refinement_budget>=4 and previous is not None:
            prevtravel,prevdata,prevbehind,preventity=previous
            if behind!=prevbehind and (entity or preventity):
                refinement_budget-=4
                bt,ft=(travel,prevtravel) if behind else (prevtravel,travel)
                hd=data if behind else prevdata;valid=True
                for _ in range(4):
                    middle=(bt+ft)*.5;ms,md,_=probe(middle)
                    if ms!=1:valid=False;break
                    if md[3]>=md[1]:bt=middle;hd=md
                    else:ft=middle
                if valid:
                    result=hit(hd)
                    if result is not None:return result,i+1,'refined entity'
        if behind:
            if not entity:return world,i+1,'world foreground'
            result=hit(data)
            if result is not None:return result,i+1,'entity'
        previous=(travel,data,behind,entity)
    return world,steps,'clear'


def contracts():
    shader=(ROOT/'assets/chroma/shaders/include/entity_shadow.glsl').read_text()
    shade=(ROOT/'assets/chroma/shaders/post/shade.fsh').read_text()
    vertex=(ROOT/'assets/chroma/shaders/post/shade.vsh').read_text()
    config=(ROOT/'assets/chroma/shaders/include/shadow_config.glsl').read_text()
    for token in ('CHROMA_ENTITY_SHADOWS == 2 && CHROMA_TRANSPARENT_DEPTH_MASK',
                  'clamp(CHROMA_ENTITY_SHADOW_STEPS, 1, 24)', 'const float thickness = 0.15',
                  'cameraProj * vec4(origin, 1.0)', 'int(floor(alpha * 255.0 + 0.5)) == 1',
                  'depth < projected.z', 'gap > thickness',
                  'if (!entity) return 1.0;', 'refine < 4', 'behind != previousBehind', 'refinementBudget = 8', 'refinementBudget -= 4',
                  'chromaAutoHeaderPixel', 'chromaCatalogHas', 'ponytail:'):
        assert token in shader,token
    assert shader.count('cameraProj *')==2
    probe_source=shader.split('int chromaEntityProbe(',1)[1].split('float chromaEntityHit(',1)[0]
    assert probe_source.index('if (depth >= 0.999999)')<probe_source.index('chromaCatalogHas(')
    assert probe_source.index('chromaAutoHeaderPixel(')<probe_source.index('texelFetch(InDepthSampler,')
    for name in ('entity.vsh','item.vsh'):
        native=(ROOT/'assets/minecraft/shaders/core'/name).read_text()
        assert 'gl_Position = vec4(pixel / ScreenSize * 2.0 - 1.0, 1.0, 1.0);' in native
    hit_source=shader.split('float chromaEntityHit(',1)[1].split('float chromaEntityShadow(',1)[0]
    assert hit_source.index('depth < projected.z')<hit_source.index('vec3 scene = reconstructEyePosAt')
    assert hit_source.index('!chromaEntityShadowTag(texelFetch')<hit_source.index('vec3 scene = reconstructEyePosAt')
    assert shader.count('reconstructEyePosAt(')==2
    assert 'layout(location = 6) flat in mat4 cameraProj;' in shade
    assert 'layout(location = 6) flat out mat4 cameraProj;' in vertex
    miss=shade.split('if (any(notEqual(shadowSource, previousShadowSource))) {',1)[1].split('previousShadowSource = shadowSource;',1)[0]
    assert miss.index('chromaShadow(')<miss.index('chromaEntityShadow(')
    assert 'previousVisibility > 0.0 && !entityReceiver' in miss
    assert 'chromaEntityShadow(lightReceiver, normal, lPos, frameSize)' in miss
    assert 'previousVisibility *= chromaEntityShadow' in miss
    assert '#include <chroma:entity_shadow.glsl>' in shade
    for name,value in (('CHROMA_ENTITY_SHADOWS','1'),('CHROMA_ENTITY_SHADOW_DISTANCE','4.0'),('CHROMA_ENTITY_SHADOW_STEPS','24')):
        assert re.search(r'#define\s+'+name+r'\s+'+re.escape(value)+r'\b',config),(name,value)


def check_comb():
    global SIZE
    old_size=SIZE;n=(0.,1.,0.);light=(0.,2.,-4.)
    floor=((0.,-2.,0.),n,lambda p:True,1.)
    body=((0.,-.5,0.),n,lambda p:abs(p[0])<1 and -8<p[2]<-3,1/255)
    receivers=[(0.,-2.,-10+i*.01) for i in range(501)]
    # Independent exact segment-plane oracle: all501 receiver rays intersect
    # the finite plane within3blocks; receiver camera rays do not hit the body.
    for receiver in receivers:
        t=dot(n,sub(body[0],receiver))/dot(n,sub(light,receiver))
        crossing=add(receiver,mul(sub(light,receiver),t))
        assert 0<t<1 and body[2](crossing) and length(sub(crossing,receiver))<3
    counts=[]
    for SIZE in ((1920,1080),(640,360)):
        sample=raster(P,[floor,body])
        old=[trace(r,n,light,P,sample,refine=False)[0] for r in receivers]
        new=[trace(r,n,light,P,sample)[0] for r in receivers]
        previous=[trace(r,n,light,P,sample,hoist=False)[0] for r in receivers]
        assert max(abs(a-b) for a,b in zip(new,previous))<1e-12,(SIZE,'projection parity')
        old_lit=sum(v>.9 for v in old);new_lit=sum(v>.9 for v in new)
        bands=sum((a>.9)!=(b>.9) for a,b in zip(old,old[1:]))
        assert old_lit>100 and bands>4,(SIZE,old_lit,bands)
        if SIZE==(1920,1080):
            assert new_lit==0 and max(new)<1e-9,(new_lit,max(new))
            # A genuine broad cutout at the exact crossing is still clear;
            # depth discontinuities must not be bridged as a filled surface.
            hole=(*body[:2],lambda p:body[2](p) and abs(p[2]+5.875)>.4,1/255)
            assert trace((0.,-2.,-7.),n,light,P,raster(P,[floor,hole]))[0]==1.
        else:
            # Known ceiling: coarse native pixels still staircase at grazing
            # angles. Preserve/report this limitation instead of hiding it.
            assert 0<new_lit<old_lit
        counts.append((SIZE,old_lit,new_lit))
    SIZE=old_size
    return counts


def check_capture(path):
    # Optional replay of tester-owned native buffers; no NumPy/image/GPU needed.
    import array,json,sys
    global SIZE
    old_size=SIZE;SIZE=(1920,1080)
    fixture=json.loads(Path(path).read_text());base=Path(fixture['native_capture'])
    depths=array.array('f');depths.frombytes((base/'minecraft_materials_depth-color.bin').read_bytes())
    if sys.byteorder!='little':depths.byteswap()
    colors=(base/'minecraft_materials_color-color.bin').read_bytes()
    proj=fixture['projection'];rotation=fixture['rotation_world_to_eye']
    camera=fixture['camera_eye_world'];light=fixture['lamp_eye']
    normal=tuple(row[1] for row in rotation)
    def sample(pixel):
        offset=pixel[0]+pixel[1]*SIZE[0]
        return depths[offset],colors[offset*4+3]/255
    # The deferred catalog branch is equivalent for all valid packet pixels
    # in this capture, plus cleared packets and ordinary depth/HUD controls.
    import struct
    catalog=struct.unpack('<2048I',(base/'minecraft_catalog-color.bin').read_bytes())
    active=[32*i+j for i,w in enumerate(catalog) for j in range(32) if w&(1<<j)]
    packet_pixels=0
    for address in active:
        x=4*(address%480);y=1080-4-3*(address//480)
        for dy in range(2):
            for dx in range(4):
                depth=depths[(y+dy)*1920+x+dx]
                assert depth<=1e-6 or depth>=.999999,(address,depth)
                packet_pixels+=1
    outcomes=[]
    for pair in fixture['pairs']:
        point=list(pair['world_receiver'])
        # Captured fixture is the flat y=1 receiver. Shader shared pixelation
        # snaps its tangential worldaxes while preserving the receiving plane.
        for axis in (0,2):point[axis]=(math.floor(point[axis]*16)+.5)/16
        receiver=tuple(dot(row,sub(point,camera)) for row in rotation)
        old=trace(receiver,normal,light,proj,sample,refine=False)[0]
        new=trace(receiver,normal,light,proj,sample)[0]
        previous=trace(receiver,normal,light,proj,sample,hoist=False)[0]
        assert new==previous,(pair['pixel_bottom_up'],'projection parity')
        assert abs(old-pair['visibility'])<1e-9,(pair['pixel_bottom_up'],old,pair['visibility'])
        assert new==0.,(pair['pixel_bottom_up'],new)
        outcomes.append((pair['pixel_bottom_up'],old,new))
    SIZE=old_size
    return {'pairs':outcomes,'packet_pixels_with_depth0_or1':packet_pixels}


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,help='Optional tester comb-points JSON with native buffer paths')
    args=parser.parse_args()
    contracts()
    for depth,packet in ((0.,True),(1.,True),(.005,False),(.2,False),(1.,False),(0.,False)):
        old_status=0 if packet or depth<=1e-6 else (-1 if depth>=.999999 else 1)
        new_status=0 if depth<=1e-6 else ((0 if packet else -1) if depth>=.999999 else 1)
        assert old_status==new_status
    n=(0.,0.,1.);receiver=(1.,0.,-5.);light=(-1.,0.,-3.)
    floor=((0.,0.,-5.),n,lambda p:True,1.)
    body=((0.,0.,-4.),n,lambda p:abs(p[0])<.22 and abs(p[1])<.5,1/255)
    planes=[floor,body];sample=raster(P,planes)
    baseline=trace(receiver,n,light,P,sample)
    assert baseline[0]==0. and 'entity' in baseline[2],baseline
    # Independent analytic segment-plane hit is inside the finite caster.
    t=dot(n,sub(body[0],receiver))/dot(n,sub(light,receiver))
    assert 0<t<1 and body[2](add(receiver,mul(sub(light,receiver),t)))
    assert trace(receiver,n,light,P,sample,receiver_tag=True)==(1.,0,'skip')
    assert trace(receiver,n,light,P,sample,world=0.)==(0.,0,'skip')
    assert trace(receiver,n,light,P,sample,world=.25)[0]==0.
    # Ordinary terrain/particle alpha is never a screen caster; a foreground
    # wall hiding the body returns neutral and does not turn opaque into glass.
    for alpha in (0.,254/255,1.):
        assert trace(receiver,n,light,P,raster(P,[floor,(*body[:3],alpha)]))[0]==1.
    wall=((0.,0.,-2.),n,lambda p:True,1.)
    assert trace(receiver,n,light,P,raster(P,[floor,body,wall]))[0]==1.
    for z in (-6.,-2.): # behind receiver or beyond source
        misplaced=((0.,0.,z),n,lambda p:abs(p[0])<.5,1/255)
        assert trace(receiver,n,light,P,raster(P,[floor,misplaced]))[0]==1.
    assert trace(receiver,n,light,P,lambda p:(1.,1/255))[0]==1. # HUD/OIT sentinel
    assert trace(receiver,n,light,P,lambda p:(0.,1/255))[0]==1. # sky
    assert trace(receiver,n,light,P,sample,maximum=0.)[0]==1.
    assert trace(receiver,n,receiver,P,sample)[0]==1.
    assert trace((10.,0.,-1.),n,(12.,0.,-1.),P,sample)[2]=='offscreen'
    assert trace((0.,0.,-.01),n,(1.,0.,-.01),P,sample)[2]=='clip'
    # The native projection itself carries bob rotation/translation. Exact
    # inverse-projection reconstructs the original scene, not a guessed eye ray.
    angle=.07;c=math.cos(angle);s=math.sin(angle)
    bob=((c,-s,0.,.015),(s,c,0.,-.02),(0.,0.,1.,.012),(0.,0.,0.,1.))
    bobbed=mm(P,bob);inv=inverse(bobbed)
    for point in ((1.,0.,-5.),(-1.,.25,-3.),(0.,-.5,-4.)):
        uv,depth=project(bobbed,point)
        assert length(sub(unproject(inv,uv,depth),point))<1e-12
    assert trace(receiver,n,light,bobbed,raster(bobbed,planes))[0]==0.
    # Independent sign equivalence: on one native projection ray, increasing
    # reversed depth is nearer even with bob. The positive gap equals Euclidean
    # separation, so no extra near/far inverse projections are needed per probe.
    for matrix in (P,bobbed):
        inverse_matrix=inverse(matrix)
        for uv in ((.01,.1),(.5,.5),(.99,.9)):
            view=unit(sub(unproject(inverse_matrix,uv,.1),unproject(inverse_matrix,uv,.9)))
            for scene_depth,ray_depth in ((.9,.1),(.2,.02),(.005,.001),(.02,.2)):
                a=unproject(inverse_matrix,uv,ray_depth);b=unproject(inverse_matrix,uv,scene_depth)
                signed=dot(sub(a,b),view)
                assert (signed>=0)==(scene_depth>=ray_depth)
                assert abs(abs(signed)-length(sub(a,b)))<1e-10

    # Large negative world positions cancel through camera-relative coordinates.
    camera=(-100000.,-64.,-200000.)
    eye_receiver=sub(add(receiver,camera),camera);eye_light=sub(add(light,camera),camera)
    assert trace(eye_receiver,n,eye_light,P,sample)[0]==baseline[0]
    # Edge/range fade weights and loop ceiling are bounded, deterministic.
    assert smooth(0.,8.,0.)==0 and smooth(0.,8.,8.)==1
    assert 1-smooth(3.,4.,3.)==1 and 1-smooth(3.,4.,4.)==0
    for count in (1,16,24,240):
        result=trace(receiver,n,light,P,lambda p:(0.,1.),steps=count)
        assert result[1]<=24 and result[0]==1.
    assert [i for i in range(256) if tag(i/255)]==[1]
    comb=check_comb()
    print(f'Comb CPU501points (resolution, old false-lit, refined false-lit): {comb};1080row fullycontiguous;640nativepixel ceiling remains.')
    if args.capture:print(f'Native capture replay (pixel, old, refined): {check_capture(args.capture)}')
    print('PASS entity contact CPU/source: finite caster; world/self skip; nonentity/particle tags; wall/behind/source/sky/interface/offscreen/nearclip; bob inverse projection; negative world coordinates; bounded24coarse+8refinement probes; fades.')
    print('Independent analytic depth fixtures only; no GLSL execution, gameplay quality or FPS claim.')

if __name__=='__main__':main()
