"""Four-surface CPU contract and independent finite-triangle ray oracle. No GPU."""
from pathlib import Path
import math
import random

ROOT = Path(__file__).resolve().parents[1]
CELL = .25
VALID = 1 << 30
OVERFLOW = 1 << 31
SURFACES = 4
EMPTY = (0,) * SURFACES

def add(a, b): return tuple(x+y for x,y in zip(a,b))
def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def mul(a, s): return tuple(x*s for x in a)
def dot(a, b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def normalize(a): return mul(a,1/math.sqrt(dot(a,a)))
def sign(x): return -1 if x<0 else 1
def base(q): return mul(q,CELL)
def center(q): return add(base(q),(.125,)*3)
def axis(n): return max(range(3),key=lambda a:abs(n[a]))
def mask(word): return word>>14&65535

def address(q,slot=0):
    x,y,z=(v&255 for v in q)
    flat=SURFACES*(x+256*(y+256*z))+slot
    return flat&4095,flat>>12

def normal(word):
    x,y=(word&15)/14*2-1,(word>>4&15)/14*2-1
    z=1-abs(x)-abs(y)
    if z<0:x,y=(1-abs(y))*sign(x),(1-abs(x))*sign(y)
    return normalize((x,y,z))

def point(word,q):
    n=normal(word)
    extent=CELL*sum(abs(x) for x in n)
    return add(center(q),mul(n,((word>>8&63)/63-.5)*extent))

def encode(hit,n,q,alpha=65535):
    n=normalize(n)
    anchor=add(center(q),mul(n,dot(n,sub(hit,center(q)))))
    n=mul(n,1/sum(abs(v) for v in n))
    x,y=n[:2]
    if n[2]<0:x,y=(1-abs(y))*sign(x),(1-abs(x))*sign(y)
    x,y=(min(14,max(0,math.floor((v*.5+.5)*14+.5))) for v in (x,y))
    word=x|(y<<4)
    n=normal(word)
    level=dot(n,sub(anchor,center(q)))/(CELL*sum(abs(v) for v in n))+.5
    level=min(63,max(0,math.floor(level*63+.5)))
    return word|(level<<8)|((alpha&65535)<<14)|VALID

def covered(word,q,p):
    v=mul(sub(p,base(q)),1/CELL)
    if any(x<-.00004 or x>1.00004 for x in v):return False
    a=axis(normal(word));u=(a+1)%3;w=(a+2)%3
    i,j=(min(3,max(0,math.floor(v[k]*4))) for k in (u,w))
    return bool(mask(word)&(1<<(i+j*4)))

def box_hit(lo,hi,s,d,limit):
    enter,leave=0.,limit
    for a in range(3):
        if abs(d[a])<1e-8:
            if not lo[a]<=s[a]<hi[a]:return None
        else:
            x,y=(lo[a]-s[a])/d[a],(hi[a]-s[a])/d[a]
            enter=max(enter,min(x,y));leave=min(leave,max(x,y))
    return enter if enter<leave else None

def ray_hit(records,q,s,d,limit=10.):
    if limit<=0:return None
    if any(w&OVERFLOW for w in records):return box_hit(base(q),add(base(q),(.25,)*3),s,d,limit)
    best=None
    for word in records:
        if not word&VALID or not mask(word):continue
        n=normal(word);height=dot(n,sub(point(word,q),s));den=dot(n,d)
        if abs(den)<1e-7:
            if abs(height)<1e-5 and covered(word,q,s):return 0.
            continue
        t=height/den
        if 0<=t<limit and covered(word,q,add(s,mul(d,t))):
            best=t if best is None else min(best,t)
    return best

def ray_any(records,q,s,d,limit=10.):
    if limit<=0:return False
    # Overflow in a later record still takes precedence over finite masks.
    if any(w&OVERFLOW for w in records):return box_hit(base(q),add(base(q),(.25,)*3),s,d,limit) is not None
    for word in records:
        if not word&VALID or not mask(word):continue
        n=normal(word);height=dot(n,sub(point(word,q),s));den=dot(n,d)
        if abs(den)<1e-7:
            if abs(height)<1e-5 and covered(word,q,s):return True
            continue
        t=height/den
        if 0<=t<limit and covered(word,q,add(s,mul(d,t))):return True
    return False

def check_lod_visibility(rng):
    # Independent LOD oracle: OR eight complete child cells, then encode just
    # that parent's two bits among unrelated random neighboring parent bits.
    comparisons=0;empty_skips=0
    for case in range(5000):
        q=tuple(rng.randrange(-120_000_000,120_000_000) for _ in range(3))
        parent=tuple(v//2 for v in q);siblings={}
        for child in range(8):
            c=tuple(parent[a]*2+((child>>a)&1) for a in range(3))
            records=[]
            for slot in range(SURFACES):
                n=normalize(tuple(rng.uniform(-1,1) for _ in range(3)))
                h=add(base(c),tuple(rng.uniform(.005,.245) for _ in range(3)))
                # Include empty groups, active upper slots, masked-out valid
                # records, and overflow independent of surface validity.
                word=encode(h,n,c,rng.getrandbits(16)) if case%3==0 and rng.random()<.2 else 0
                if case%7==0:word=encode(h,n,c,0)
                if case%31==0 and child==case%8 and slot==3:word|=OVERFLOW
                records.append(word)
            siblings[c]=records
        occupied=any(w&OVERFLOW or (w&VALID and mask(w)) for records in siblings.values() for w in records)
        storage=tuple((v>>1)&127 for v in q)
        pixel=(storage[0]//16+8*storage[2],storage[1]);shift=(storage[0]&15)*2
        packed=(rng.getrandbits(32)&~(3<<shift))|((3 if occupied else 0)<<shift)
        byte=(packed>>(((storage[0]&15)>>2)*8))&255
        sampled=math.floor((byte/255)*255+.5)
        lod=(sampled>>((storage[0]&3)*2))&3
        assert (lod>=2)==occupied and 0<=pixel[0]<1024 and 0<=pixel[1]<128
        s=add(base(q),tuple(rng.uniform(-.25,.5) for _ in range(3)))
        target=add(base(q),tuple(rng.uniform(0,.25) for _ in range(3)))
        d=normalize(sub(target,s));limit=rng.uniform(.05,1.)
        origin=tuple((v//4)*4-128 for v in q)
        if case%19==0:origin=(origin[0]+256,origin[1],origin[2])
        inside=all(0<=v-o<256 for v,o in zip(q,origin))
        records=siblings[q] if inside else EMPTY
        nearest=ray_hit(records,q,s,d,limit)
        any_hit=inside and lod>=2 and ray_any(siblings[q],q,s,d,limit)
        assert any_hit==(nearest is not None),(case,q,records,s,d,limit,nearest,any_hit)
        empty_skips+=inside and lod<2
        comparisons+=1
    return comparisons,empty_skips

def clip_polygon(poly,a,bound,keep_greater):
    if not poly:return []
    out=[]
    for p,q in zip(poly,poly[1:]+poly[:1]):
        pin=(p[a]>=bound) if keep_greater else (p[a]<=bound)
        qin=(q[a]>=bound) if keep_greater else (q[a]<=bound)
        if pin:out.append(p)
        if pin!=qin:
            f=(bound-p[a])/(q[a]-p[a]);out.append(add(p,mul(sub(q,p),f)))
    return out

def triangles(word,q):
    # Independent representation: build each covered projected patch as a
    # polygon on the plane, clip it by the cell, then triangulate the result.
    n=normal(word);p=point(word,q);a=axis(n);u=(a+1)%3;v=(a+2)%3;lo=base(q)
    result=[]
    for bit in range(16):
        if not mask(word)&(1<<bit):continue
        poly=[]
        for du,dv in ((0,0),(1,0),(1,1),(0,1)):
            h=list(lo);h[u]+=((bit&3)+du)/16;h[v]+=((bit>>2)+dv)/16
            h[a]=p[a]-(n[u]*(h[u]-p[u])+n[v]*(h[v]-p[v]))/n[a]
            poly.append(tuple(h))
        for k in range(3):
            poly=clip_polygon(poly,k,lo[k],True)
            poly=clip_polygon(poly,k,lo[k]+CELL,False)
        for i in range(1,len(poly)-1):result.append((poly[0],poly[i],poly[i+1]))
    return result

def triangle_hit(tri,s,d,limit):
    a,b,c=tri;e1=sub(b,a);e2=sub(c,a);p=cross(d,e2);det=dot(e1,p)
    if abs(det)<1e-10:return None
    tvec=sub(s,a);u=dot(tvec,p)/det
    if not 0<=u<=1:return None
    q=cross(tvec,e1);v=dot(d,q)/det
    if v<0 or u+v>1:return None
    t=dot(e2,q)/det
    return t if 0<=t<limit else None

def guide_hit(volume,s,d,guide_point,limit):
    # A guide reconstructed just beyond a boundary may identify the EMPTY side.
    # Test both cells adjoining every candidate grid-plane crossing.
    seed=tuple(math.floor(v*4) for v in add(guide_point,mul(d,.0001)))
    for a in range(3):
        if abs(d[a])<1e-6:continue
        for side in (0,1):
            t=((seed[a]+side)*CELL-s[a])/d[a]
            if not 0<t<limit-.0001:continue
            for epsilon in (-.0001,.0001):
                q=tuple(math.floor(v*4) for v in add(s,mul(d,t+epsilon)))
                found=ray_hit(volume.get(q,EMPTY),q,s,d,limit-.0001)
                if found is not None:return found
    return None

def run():
    source=(ROOT/'assets/chroma/shaders/include/voxel_space.glsl').read_text()
    shader=(ROOT/'assets/chroma/shaders/include/shadow_filter.glsl').read_text()
    assert 'uvec4 chromaVoxSurfaceData(' in source and 'bool chromaVoxDataRayHit(uvec4 data' in source
    assert '#define CHROMA_VOX_SURFACES 4' in source
    assert 'CHROMA_VOX_SURFACES * (v.x + CHROMA_VOX_N * (v.y + CHROMA_VOX_N * v.z))' in source
    assert 'data.x | data.y | data.z | data.w' in source
    assert 'bool chromaVoxDataRayAny(' in source and 'bool chromaOccupiedLod(' in source
    assert '(data >> 14u) & 65535u' in source and '0x40000000u' in source and '0x80000000u' in source
    assert '#include <chroma:shadow_filter_static.glsl>' in shader
    assert 't - 0.0001' in shader and 't + 0.0001' in shader
    assert 'if (all(equal(cell, receiverCell)))' not in shader
    assert 'if (!chromaVoxContains(cell, chromaVoxOrigin())) return false;' in shader
    assert 'if (!chromaOccupiedLod(VoxelLod1Sampler, cell, 1)) return false;' in shader
    assert 'chromaAreaCellBlocked(chromaVoxOf(light)' in shader and 'chromaAreaCellBlocked(before' in shader and 'chromaAreaCellBlocked(after' in shader
    rng=random.Random(7303)
    # One unchanged oblique plane must encode identically when the camera
    # observes different points. Quantized normals otherwise cause offset drift.
    phase_cases=0
    n=normalize((-.614239,.614852,.494639));q=(0,0,0);c=center(q);a=axis(n);uv=[k for k in range(3) if k!=a]
    for phase in range(63):
        true_point=add(c,mul(n,(phase-31)*.002))
        codes=[]
        for u in (.01,.04,.08,.125,.17,.21,.24):
            for v in (.01,.04,.08,.125,.17,.21,.24):
                h=list(c);h[uv[0]]=u;h[uv[1]]=v
                h[a]=true_point[a]-(n[uv[0]]*(u-true_point[uv[0]])+n[uv[1]]*(v-true_point[uv[1]]))/n[a]
                if 0<=h[a]<=CELL:codes.append(encode(tuple(h),n,q))
        assert codes and len(set(codes))==1,(phase,sorted(set(codes)))
        phase_cases+=1
    for a in range(3):
        for direction in (-1,1):
            n=tuple(float(direction) if i==a else 0. for i in range(3))
            w=encode((.125,)*3,n,(0,0,0));assert dot(n,normal(w))==1
    for _ in range(1000):
        q=tuple(rng.randrange(-120_000_000,120_000_000) for _ in range(3))
        for slot in range(SURFACES):
            x,y=address(q,slot);flat=x+4096*y;assert flat&3==slot
            i=flat>>2;assert (i&255,i>>8&255,i>>16)==tuple(v&255 for v in q)
            assert 0<=x<4096 and 0<=y<16384
            assert address(q,slot)==(address(q,0)[0]+slot,address(q,0)[1])
        word=rng.getrandbits(32);rgba=[word>>i&255 for i in (0,8,16,24)]
        assert sum(v<<(8*i) for i,v in enumerate(rgba))==word
    # Camera changes and large/negative worlds preserve relative geometry.
    for camera in ((0,0,0),(-30_000_000,-64,29_999_999),(29_999_999,300,-30_000_000)):
        q=tuple(v*4-1 for v in camera);offset=(.375,-.125,-.875)
        lower=tuple((q[a]-camera[a]*4)*CELL+offset[a] for a in range(3))
        assert lower==(.125,-.375,-1.125)
        for jump in (-260,-4,0,4,260):
            old=tuple(v*4-128-jump for v in camera);current=tuple(v*4-128 for v in camera)
            wrapped=tuple(v&255 for v in q)
            newq=tuple(o+((w-o)&255) for o,w in zip(current,wrapped))
            oldq=tuple(o+((w-o)&255) for o,w in zip(old,wrapped))
            assert (oldq==newq)==all(0<=v-o<256 for v,o in zip(newq,old))
    # Finite alpha patches, both sides, and a source inside a partially occupied
    # cell. The source cell guard must intersect the remaining outgoing segment.
    q=(0,0,0);w=encode((.125,.125,.125),(1,0,0),q,65535^(1<<9))
    assert ray_hit((w,0),q,(-1,.09375,.15625),(1,0,0)) is None
    assert ray_hit((w,0),q,(-1,.03125,.03125),(1,0,0)) is not None
    assert ray_hit((w,0),q,(1,.03125,.03125),(-1,0,0)) is not None
    assert ray_hit((w,0),q,(-1,.3,.03125),(1,0,0)) is None
    assert ray_hit((w,0),q,(.0625,.03125,.03125),(1,0,0)) is not None
    assert ray_hit((OVERFLOW,0),q,(-1,.1,.1),(1,0,0))==1
    assert ray_hit((w&~VALID,0),q,(-1,.1,.1),(1,0,0)) is None
    assert ray_hit((w,0),q,point(w,q),(0,0,1),0) is None
    # Every slot participates, including overflow in either upper record.
    for slot in range(SURFACES):
        records=list(EMPTY);records[slot]=w
        assert ray_hit(records,q,(-1,.03125,.03125),(1,0,0)) is not None
        records[slot]=OVERFLOW
        assert ray_hit(records,q,(-1,.1,.1),(1,0,0))==1
    # Real fence junction: two parallel post/rail sides, the rail top and a
    # post end occupy one quarter cell. Each of four independent rays requires
    # its own record; replacing the missing surface by a filled cube is wrong.
    fence_q=(1,6,-6)
    fence_faces=(((.375,1.625,-1.375),(1,0,0)),
                 ((.4375,1.625,-1.375),(1,0,0)),
                 ((.375,1.5625,-1.375),(0,1,0)),
                 ((.375,1.625,-1.375),(0,0,1)))
    fence_records=tuple(encode(p,n,fence_q) for p,n in fence_faces)
    fence_rays=(((.30,1.70,-1.48),(1,0,0),.1),
                ((.49,1.70,-1.48),(-1,0,0),.07),
                ((.47,1.51,-1.48),(0,1,0),.1),
                ((.47,1.70,-1.49),(0,0,1),.2))
    for slot,(s,d,limit) in enumerate(fence_rays):
        actual=ray_hit(fence_records,fence_q,s,d,limit)
        mesh=[tri for record in fence_records for tri in triangles(record,fence_q)]
        hits=[t for tri in mesh if (t:=triangle_hit(tri,s,d,limit)) is not None]
        assert actual is not None and hits and abs(actual-min(hits))<1e-8
        removed=list(fence_records);removed[slot]=0
        assert ray_hit(removed,fence_q,s,d,limit) is None,(slot,actual)
    # Exact quarter-boundary surfaces must cast from both directions even when
    # map-hit+epsilon identifies the opposite, empty cell.
    for a in range(3):
        for side in (0.,.25):
            h=[.125]*3;h[a]=side;n=[0.]*3;n[a]=1.;record=encode(tuple(h),tuple(n),q)
            for sign_ in (-1,1):
                s=list(h);s[a]-=sign_;d=[0.]*3;d[a]=sign_
                result=guide_hit({q:(record,0)},tuple(s),tuple(d),tuple(h),2.)
                assert result is not None and abs(result-1)<1e-8,(a,side,sign_,result)
    # Independent triangle oracle, including oblique planes near cell corners.
    comparisons=0
    for _ in range(150):
        records=[]
        for slot in range(SURFACES):
            n=normalize(tuple(rng.uniform(-1,1) for _ in range(3)))
            h=tuple(rng.uniform(.005,.245) for _ in range(3))
            records.append(encode(h,n,q,rng.getrandbits(16)))
        mesh=[tri for record in records for tri in triangles(record,q)]
        for _ in range(10):
            s=tuple(rng.uniform(-.5,.75) for _ in range(3));target=tuple(rng.uniform(0,.25) for _ in range(3));d=normalize(sub(target,s))
            actual=ray_hit(records,q,s,d,2.)
            hits=[t for tri in mesh if (t:=triangle_hit(tri,s,d,2.)) is not None]
            expected=min(hits) if hits else None
            assert (actual is None)==(expected is None),(records,s,d,actual,expected)
            if actual is not None:assert abs(actual-expected)<1e-8
            comparisons+=1
    # Closed six-face room: every center-to-outside direction crosses its real
    # surface; opening a covered patch releases only rays through that patch.
    for _ in range(300):
        d=normalize(tuple(rng.uniform(-1,1) for _ in range(3)));a=axis(d);t=1/abs(d[a]);h=mul(d,t)
        n=tuple(-sign(d[a]) if i==a else 0. for i in range(3))
        cell=tuple(math.floor(v*4) for v in sub(h,mul(n,.02)))
        record=encode(h,n,cell)
        result=ray_hit((record,0),cell,(0,0,0),d,4.)
        assert result is not None and abs(result-t)<1e-8
    lod_cases,lod_skips=check_lod_visibility(rng)
    print(f'PASS Surface128:1000 four-slot packing/address cases; exact six-axis normals; {phase_cases} stable oblique-plane phases; window/world invariance; '
          f'alpha/source/boundary controls; four independently required fence faces; {comparisons} independent four-surface triangle rays;300 closed-room rays; '
          f'{lod_cases} LOD/any-hit equivalence rays ({lod_skips} proved-empty skips)')

if __name__=='__main__':run()
