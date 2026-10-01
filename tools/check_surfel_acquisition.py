"""Independent CPU acquisition checks for persistent masked surface planes.

Analytic opaque/cutout planes produce raster depth. This does not run GLSL,
Minecraft, or infer runtime frame rate.
"""
from pathlib import Path
import math,json,itertools
import numpy as np
import check_surfel_voxels as surfel
ROOT=Path(__file__).resolve().parents[1]
SIZE=1024;FOCAL=1/math.tan(math.radians(35));CAM=np.array([.125,.125,-2.])
PLANE=.125;MASK=0xF99F;CAPACITY=4


def bit_at(point):
    x,y=np.clip(np.floor(point[:2]*16).astype(int),0,3)
    return int(x+4*y)


def project(point):
    p=(point-CAM);return np.floor((p[:2]/p[2]*FOCAL*.5+.5)*SIZE).astype(int)


def at_depth(pixel,z):
    ray=np.r_[((np.array(pixel)+.5)/SIZE*2-1)/FOCAL,1.]
    return CAM+ray*(z-CAM[2])


def native(pixel,scene):
    point=at_depth(pixel,PLANE)
    in_cell=np.all(point[:2]>=0)&np.all(point[:2]<.25)
    if scene=='occluded':return at_depth(pixel,-.1)
    if scene=='cutout' and in_cell and MASK&(1<<bit_at(point)):return point
    if isinstance(scene,tuple) and in_cell:
        if scene[0]=='mix':
            if scene[1]<=point[0]<=scene[2] or bit_at(point)==scene[3]:return point
        elif scene[0]<=point[0]<=scene[1]:return point
    return at_depth(pixel,1.)


def patch_can_clear(status,positive,retained_positive,footprint):
    if positive or 1 in status or 0 not in status:return False
    if all(s==0 for s in status) and not retained_positive:return True
    return footprint()


def positive_probe_equivalence():
    comparisons=0
    for statuses in itertools.product((-1,0,1),repeat=4):
        for old,positive,retained,vacant in itertools.product((False,True),repeat=4):
            full=old or positive or 1 in statuses
            if not positive and 1 not in statuses and patch_can_clear(statuses,False,retained and old,lambda:vacant):full=False
            seen=[]
            if not positive:
                for status in statuses:
                    seen.append(status)
                    if status==1:break
            fast=old or positive or 1 in seen
            if not positive and 1 not in seen and patch_can_clear(seen,False,retained and old,lambda:vacant):fast=False
            assert full==fast
            if positive:assert len(seen)==0
            if statuses==(1,1,1,1) and not positive:assert len(seen)==1
            comparisons+=1
    assert comparisons==1296


def refine(old_mask,scene,measured=PLANE,positives=0,retained=False):
    mask=old_mask
    for bit in range(16):
        status=[]
        for dx in (.25,.75):
            for dy in (.25,.75):
                point=np.array([(bit%4+dx)/16,(bit//4+dy)/16,measured])
                pixel=project(point);surface=native(pixel,scene)
                if abs(surface[2]-measured)<=.005:
                    neighbours=[native(pixel+offset,scene) for offset in ((-1,0),(1,0),(0,-1),(0,1))]
                    normal,supported=observed_normal([surface-CAM]+[p-CAM for p in neighbours])
                    patch=np.floor(surface[:2]*16).astype(int)
                    same_patch=np.array_equal(patch,[bit%4,bit//4])
                    if not supported:status.append(-1)
                    elif abs(normal[2])>=.95:status.append(1 if same_patch else -1)
                    else:status.append(0 if surface[2]>measured+.0001 else -1)
                elif surface[2]>measured+.0001:status.append(0)
                else:status.append(-1)
        if 1 in status:mask|=1<<bit
        elif patch_can_clear(status, bool(positives&(1<<bit)),
                             bool(retained and old_mask&(1<<bit)),
                             lambda:footprint_air(scene,bit)):mask&=~(1<<bit)
    return mask|positives


def footprint_air(scene,bit=None):
    low=np.array([0.,0.,PLANE]);high=np.array([.25,.25,PLANE])
    if bit is not None:
        low[:2]=np.array([bit%4,bit//4])/16;high[:2]=low[:2]+1/16
    a=project(low);b=project(high)
    tested=0
    for x in range(a[0],b[0]+1):
        for y in range(a[1],b[1]+1):
            point=at_depth((x,y),PLANE)
            if not (np.all(point[:2]>=low[:2])&np.all(point[:2]<=high[:2])):continue
            tested+=1
            if native((x,y),scene)[2]<=PLANE+.0001:return False
    return tested>0


def acquire(records,point,normal,vacant=None,positives=None):
    candidate=surfel.encode(point,normal,(0,0,0));new_normal=np.array(surfel.normal(candidate));new_point=np.array(surfel.point(candidate,(0,0,0)))
    selected=next((i for i,r in enumerate(records)
                   if (abs(new_normal@np.array(surfel.normal(r['word'])))>.99999 or abs(normal@r['normal'])>.98)
                   and abs((new_point-np.array(surfel.point(r['word'],(0,0,0))))@np.array(surfel.normal(r['word'])))<.012),None)
    if selected is None:
        if len(records)==CAPACITY:
            selected=next((i for i,r in enumerate(records)
                           if vacant is not None and not (positives or [0]*CAPACITY)[i] and vacant(r)),None)
            if selected is None:return True
            records[selected]=dict(point=point.copy(),normal=normal.copy(),mask=65535,word=candidate)
            return False
        records.append(dict(point=point.copy(),normal=normal.copy(),mask=65535,word=candidate));return False
    records[selected]['point']=point.copy();records[selected]['normal']=normal.copy();records[selected]['word']=candidate;return False


def observed_normal(points,rotation=None):
    center,*sides=points
    dz=[abs(p[2]-center[2]) for p in sides]
    h=1 if dz[1]<dz[0] else 0;v=3 if dz[3]<dz[2] else 2
    dx=sides[1]-center if h else center-sides[0]
    dy=sides[3]-center if v==3 else center-sides[2]
    normal=np.cross(dx,dy);normal/=np.linalg.norm(normal)
    if normal@center>0:normal=-normal
    world=normal if rotation is None else normal@rotation
    world/=np.linalg.norm(world)
    supported=max(abs(world))>.99999 or all(d<1 and abs((p-center)@normal)<=.002 for d,p in zip(dz,sides))
    return world,supported


def normal_support_controls():
    pixels=((0,0),(-1,0),(1,0),(0,-1),(0,1))
    rays=[np.array([x*.002,y*.002,-1.]) for x,y in pixels]
    # Three tiny, individually axis-aligned rectangles at different depths.
    # Their mixed centre/H/V raster samples invent an oblique plane.
    rectangles=[(-3.,(-.003,.003),(-.003,.003)),
                (-3.03,(.003,.03),(-.03,.03)),
                (-3.02,(-.003,.003),(.003,.03)),
                (-9.,(-1,1),(-1,1))]
    def hit(ray,faces):
        points=[ray*(-z) for z,x,y in faces
                if x[0]<=ray[0]*(-z)<=x[1] and y[0]<=ray[1]*(-z)<=y[1]]
        return min(points,key=lambda p:-p[2])
    fake,supported=observed_normal([hit(r,rectangles) for r in rays])
    assert max(abs(fake))<.99999 and not supported
    # An actual oblique plane produces consistent depth on all four neighbours.
    n=np.array([.3,.5,1.]);n/=np.linalg.norm(n);p=np.array([0.,0.,-3.])
    genuine,supported=observed_normal([r*((p@n)/(r@n)) for r in rays])
    assert supported and abs(genuine@n)>1-1e-10
    # At a real thin edge one unused neighbour sees background. The exact axis
    # normal remains usable, so coarse acquisition can still launch fine probes.
    edge=[(-3.,(0,.25),(-.25,.25)),(-9.,(-1,1),(-1,1))]
    points=[hit(r,edge) for r in rays];normal,supported=observed_normal(points)
    assert supported and max(abs(normal))> .99999
    assert any(abs((p-points[0])@normal)>.002 for p in points[1:])


def captured_corner_controls():
    # Four actual native depth stencils from Surface5 cow pixel [932,697].
    # The empty +Z patch was incorrectly confirmed by a nearby -X/front edge.
    capture=json.loads((ROOT/'tools/fixtures/surfel-corner-evidence.json').read_text())
    values=[]
    for probe in capture['probes']:
        n,supported=observed_normal(np.array(probe['eye_stencil']),np.array(capture['rotation']))
        native=np.array(probe['native_surface']);plane=np.array(capture['plane'])
        assert abs((native-plane)@np.array(capture['normal']))<.005
        patch=np.floor((native-np.array(capture['cell'])*.25)*16).astype(int)
        same_patch=patch[0]==0 and patch[1]==2
        if not supported:result=-1
        elif abs(n@np.array(capture['normal']))>=.95:result=1 if same_patch else -1
        else:result=0 if probe['depth_behind_plane']>.0001 else -1
        values.append(result)
    assert values==[0,0,0,-1],values
    # Complete raster coverage of this exact native patch proves all samples
    # behind the surface despite the unknown fourth point-normal stencil.
    gaps=capture['patch_footprint_depth_gaps']
    assert len(gaps)==14 and min(gaps)>.0001
    proof=lambda:all(gap>.0001 for gap in gaps)
    assert patch_can_clear(values,False,True,proof)
    assert not patch_can_clear(values,True,True,proof)
    assert not patch_can_clear([0,0,1,-1],False,True,proof)
    assert not patch_can_clear([-1]*4,False,True,lambda:True)
    assert not patch_can_clear(values,False,True,lambda:footprint_air((.119,.122),1))
    assert not patch_can_clear(values,False,True,lambda:all(g>.0001 for g in gaps+[0.]))

    # A valid coplanar hit from the adjacent patch is unknown, never positive.
    assert not same_patch and values[-1]!=1


def refinement_slot_equivalence():
    # Compare the old all-record final stage with each independently emitted
    # slot, after acquisition has already resolved capacity/current positives.
    scenes=('cutout','removed','occluded',('mix',.119,.122,0))
    def emit(records,positives,retained,slot,only_slot):
        words=records.copy()
        if not any(w&surfel.OVERFLOW for w in words):
            for i in ([slot] if only_slot else range(CAPACITY)):
                if not words[i]&surfel.VALID:continue
                mask=refine((words[i]>>14)&65535,scenes[i],
                            positives=positives[i],retained=retained[i])
                words[i]=(words[i]&~(65535<<14))|(mask<<14) if mask else 0
        return words[slot]
    words=[surfel.VALID|(mask<<14)|0x77 for mask in (65535,MASK,65535,3)]
    cases=[]
    for count in range(CAPACITY+1):
        records=words[:count]+[0]*(CAPACITY-count)
        cases.append((records,[0]*CAPACITY,[True]*CAPACITY))
        cases.append((records,[1<<(i*3) if i<count else 0 for i in range(CAPACITY)],[False]*CAPACITY))
    for overflow_slot in range(CAPACITY):
        records=words.copy();records[overflow_slot]|=surfel.OVERFLOW
        cases.append((records,[1]*CAPACITY,[True]*CAPACITY))
    for records,positives,retained in cases:
        for slot in range(CAPACITY):
            assert emit(records,positives,retained,slot,False)==emit(records,positives,retained,slot,True)


def persistent_phase_equivalence():
    # Native persistent targets are not cleared before drawing. Compare sparse
    # writes with the old full update/history copies through moves and invalid
    # packets, including first use and a jump larger than the cache window.
    n=8
    wrapped=np.stack(np.meshgrid(*([np.arange(n)]*3),indexing='ij'),axis=-1).reshape(-1,3)
    full=np.zeros((n**3,4),dtype=np.uint32);sparse=full.copy();history=full.copy()
    previous=None;frame=0
    origins=[(-12,-8,-4)]*17+[(-8,-8,-4)]*8+[(-8,-4,0)]*8+[(24,0,-32)]*9
    for step,origin in enumerate(origins):
        valid=step not in (0,7,22)
        world=np.array(origin)+(wrapped-np.array(origin))%(n)
        retained=np.zeros(n**3,dtype=bool) if previous is None else np.all(
            (world>=previous)&(world<np.array(previous)+n),axis=1)
        phase=(world[:,1]^(world[:,2]>>3))%8
        changed=~retained|(phase==frame%8)
        values=((world[:,0]*73471+world[:,1]*193+world[:,2]*983+step*8191)&0xffffffff).astype(np.uint32)
        values=values[:,None]+np.arange(4,dtype=np.uint32)
        reference=full.copy()
        if valid:
            reference[changed]=values[changed]
            sparse[changed]=values[changed]
            history[changed]=sparse[changed]
            previous=origin;frame+=1
        full=reference
        assert np.array_equal(full,sparse) and np.array_equal(sparse,history)
    history_source=(ROOT/'assets/chroma/shaders/post/voxel_history.fsh').read_text()
    assert 'retained && !chromaVoxUpdateSlice(voxel, frame)) discard;' in history_source
    from build_shadows import configure,CHAIN
    chain=configure(json.loads((ROOT/CHAIN).read_text()))
    copy=next(p for p in chain['passes'] if p['output']=='voxel_history')
    assert copy['fragment_shader']=='chroma:post/voxel_history'
    assert copy['vertex_shader']=='chroma:post/voxel_update'
    assert next(i['target'] for i in copy['inputs'] if i['sampler_name']=='Meta')=='voxel_meta_history'
    assert chain['targets']['voxel']['persistent'] and chain['targets']['voxel_history']['persistent']
    assert np.bincount((wrapped[:,0]^wrapped[:,1]^wrapped[:,2])%8).tolist()==[n**3//8]*8
    floor=wrapped[wrapped[:,1]==0]
    assert np.bincount((floor[:,0]^floor[:,2])%8).tolist()==[n**2//8]*8


def normal_cache_controls():
    from build_shadows import configure, CHAIN
    import hashlib
    support=(ROOT/'assets/chroma/shaders/include/depth_support.glsl').read_text()
    source=(ROOT/'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    cache=(ROOT/'assets/chroma/shaders/post/surface_normal.fsh').read_text()
    # The cache producer retains native reconstruction, including exclusion
    # rules and strict support. Vacancy proofs below inspect the full footprint.
    # Evidence now also handles entity modes; check_entity_mask.py validates
    # those native/visibility contracts. Reconstruction itself is unchanged.
    for signature,expected in [('vec3 eyeAt(','99d684a8b441'),
                               ('bool depthNormal(','dbc608c6b43c')]:
        start=support.index(signature);end=support.index('{',start)+1;depth=1
        while depth:
            depth+=(support[end]=='{')-(support[end]=='}');end+=1
        assert hashlib.sha256(support[start:end].encode()).hexdigest().startswith(expected)
    assert 'q.y << 15u' in support and '/ 32766.0' in support
    assert source.count('texelFetch(SurfaceNormalSampler, p, 0)')==2
    assert '(cachedNormal & 0xc0000000u) != 0xc0000000u' in source
    assert '(cachedNormal & 0x80000000u) != 0u ? normal : vec3(0.0)' in source
    observer=source[source.index('void observeBox('):source.index('// A mask is attached')]
    assert 'previous' not in observer and 'clearPlane' not in observer
    assert 'depthNormal(' not in observer, 'Reconstruction is shared through the current-frame cache'
    # Both callers consume only the positive/hit out parameters. The removed
    # confidence calculation cannot erase any retained plane or mask.
    calls=[line.strip() for line in source.splitlines() if 'observeBox(' in line]
    assert len(calls)==3 and calls[0].startswith('void observeBox(')
    assert all(line.startswith('observeBox(') for line in calls[1:])
    assert 'fragColor = vec4(0.0);' in cache and 'discard;' not in cache
    assert 'depth > 0.000001 && depth < 0.999999' in cache
    assert '!evidencePixel(p, size)' in cache and 'dot(supportedNormal, supportedNormal) > 0.5' in cache
    chain=configure(json.loads((ROOT/CHAIN).read_text()))
    assert configure(chain)==chain
    names=[p['fragment_shader'] for p in chain['passes']]
    assert names.index('chroma:post/surface_normal') < names.index('chroma:post/voxel_update')
    assert chain['targets']['surface_normal']=={}, 'Normal cache is current-frame framebuffer size'
    producer=chain['passes'][names.index('chroma:post/surface_normal')]
    assert producer['vertex_shader']=='chroma:post/voxel_update'
    bound={i['sampler_name']:i['target'] for i in producer['inputs']}
    assert bound==dict(MatDec='matdec',Meta='voxel_meta_history',InDepth='minecraft:main',MainColor='minecraft:main',Catalog='catalog')
    assert next(i for i in producer['inputs'] if i['sampler_name']=='InDepth')['use_depth_buffer']
    consumer=chain['passes'][names.index('chroma:post/voxel_update')]
    assert next(i['target'] for i in consumer['inputs'] if i['sampler_name']=='SurfaceNormal')=='surface_normal'
    static=configure(chain,dict(dims=[256]*3))
    assert 'surface_normal' not in static['targets']
    assert not any(p['fragment_shader']=='chroma:post/surface_normal' for p in static['passes'])
    assert configure(static)==chain

    def packed(n,bits,supported):
        n=np.asarray(n,dtype=np.float32);n=n/np.sum(np.abs(n));oct=n[:2].copy()
        if n[2]<0:oct=(1-np.abs(oct[::-1]))*np.where(oct>=0,1.,-1.)
        levels=(1<<bits)-2
        q=np.clip(np.floor((oct*.5+.5)*levels+.5),0,levels).astype(np.uint32)
        return int(q[0])|(int(q[1])<<bits)|0x40000000|(0x80000000 if supported else 0)
    def decoded(word,bits):
        levels=(1<<bits)-2;mask=(1<<bits)-1
        oct=np.array([word&mask,(word>>bits)&mask],dtype=np.float32)/levels*2-1
        n=np.r_[oct,1-np.abs(oct).sum()]
        if n[2]<0:n[:2]=(1-np.abs(n[1::-1]))*np.where(n[:2]>=0,1.,-1.)
        return n/np.linalg.norm(n)
    axes=np.r_[np.eye(3),-np.eye(3)]
    for n in axes:
        for supported in (False,True):
            word=packed(n,15,supported)
            assert bool(word&0x80000000)==supported and word&0x40000000
            assert np.array_equal(decoded(word,15),n), 'All six axes, including -Z, must encode exactly'
    rng=np.random.default_rng(263);normals=rng.normal(size=(5000,3));normals/=np.linalg.norm(normals,axis=1)[:,None]
    errors={}
    for bits in (14,15):
        errors[bits]=max(np.linalg.norm(decoded(packed(n,bits,False),bits)-n) for n in normals)
        assert errors[bits]<5/((1<<bits)-2)
    assert errors[15]<errors[14]
    for n in normals[:200]:
        quant=decoded(packed(n,15,True),15)
        for grid in (4,8):
            for sign in (-1,1):
                # Actual pushed hit safely on either side of a cell threshold;
                # near-threshold equivalence is deliberately not claimed.
                target=np.array([-.25+sign*.0001,.12,-.37])
                hit=target+n*(.08/grid)
                assert np.array_equal(np.floor(target*grid),np.floor((hit-quant*(.08/grid))*grid))
    # Support is stored, not reclassified from a near-axis quantized normal.
    for x in (.999989,.99999,.999991):
        n=np.array([x,math.sqrt(1-x*x),0.])
        for supported in (False,True):
            assert bool(packed(n,15,supported)&0x80000000)==supported
    print('PASS normal cache: unchanged native stencil/exclusions; six exact axes; 5000 normals at14/15 bits, max errors',errors,
          '; support flags; negative cell-threshold controls; current-frame Dynamic/Static bindings. Not exact float equivalence.')


def run():
    normal_cache_controls()
    positive_probe_equivalence()
    normal_support_controls()
    captured_corner_controls()
    refinement_slot_equivalence()
    persistent_phase_equivalence()
    source=(ROOT/'assets/chroma/shaders/post/voxel_update.fsh').read_text()
    assert 'int slot = index & 3;' in source and 'index >>= 2;' in source
    assert 'records[slot] = refineSurface(records[slot], voxel, points[slot], normals[slot], positives[slot], hadPlane[slot], size);' in source and 'records[i] = refineSurface(' not in source
    fast=source.index('if (retained && !updateSlice)')
    assert source.index('discard;',fast)<source.index('uvec4 records = uvec4(0u);',fast)
    assert source.index('uvec4 records = uvec4(0u);')<source.index('chromaVoxSurfaceTexel(voxel, i)')
    assert 'chromaSurfelEncode(hit, normal, voxel, mask)' in source
    acquire_source=source[source.index('void acquireSurface('):source.index('int planeEvidence(')]
    assert acquire_source.index('0x80000000u) != 0u) return;')<acquire_source.index('records[chosen] = encoded;')
    assert 'mask |= positives;' in source and '!planeFootprintVacant(voxel, point, normal, size)' in source
    assert 'for (int probe = 0; probe < 4; ++probe)' in source
    assert 'if (occupied) break;' in source
    assert 'if ((positives & (1u << uint(bit))) != 0u) { mask |= 1u << uint(bit); continue; }' in source
    assert 'surfaceW > planeW + 0.0001' in source
    support=(ROOT/'assets/chroma/shaders/include/depth_support.glsl').read_text()
    assert support.count('bool depthNormal(')==1 and 'depthNormal(' not in source
    assert 'abs(dot(supportedNormal, normal)) >= 0.95' in source
    assert 'observedNormal = vec3(0.0);' in support and 'positive = true;' in source
    assert 'chromaMd' not in source,'Draw-constant camera decode belongs to vertex stage'
    assert refine(65535,'cutout')==MASK
    # Retained quantized plane is displaced by less than the axis tolerance.
    assert refine(65535,'cutout',.125+.25/126)==MASK
    assert refine(MASK,'occluded')==MASK,'Hidden alpha knowledge must persist'
    assert refine(MASK,'removed')==0 and footprint_air('removed')
    # A visible sliver lying between all 64 patch probes: the complete raster
    # footprint sees it, so deleting the existing plane would be unsafe.
    stripe=(.119,.122)
    assert refine(65535,stripe)==0
    assert not footprint_air(stripe)
    assert not footprint_air('cutout') and not footprint_air('occluded')
    mixed=('mix',.119,.122,0);old=(1<<0)|(1<<1)
    assert refine(old,mixed)==1, 'Fixture must reproduce partial-mask thin-strip deletion'
    assert refine(old,mixed,retained=True)==old, 'Retained patch footprint preserves the missed strip'
    assert refine(0,'removed',positives=1<<6)==1<<6,'A current positive wins over coarse empty probes'
    records=[];p=np.array([.125,.125,.125])
    assert not acquire(records,p,np.array([1.,0,0]))
    assert not acquire(records,p,np.array([-1.,0,0])) and len(records)==1
    assert not acquire(records,p,np.array([0.,1,0])) and len(records)==2
    assert not acquire(records,p,np.array([0.,0,1.])) and len(records)==3
    assert not acquire(records,p+np.array([.06,0,0]),np.array([1.,0,0])) and len(records)==4
    assert acquire(records,p+np.array([0,.06,0]),np.array([0.,1,0])), 'Fifth distinct plane must use conservative overflow'
    # A post/rail/top junction has four real axis planes inside one quarter.
    records=[]
    for point,normal in (([.125,.25,.125],[0,1,0]),([.125,.125,.125],[1,0,0]),
                         ([.1875,.125,.125],[1,0,0]),([.125,.125,.0625],[0,0,1])):
        assert not acquire(records,np.array(point),np.array(normal,dtype=float))
    assert len(records)==CAPACITY
    # This measured normal differs from its8-bit encoding by~17 degrees.
    # Re-observing the SAME plane must not consume additional slots then overflow.
    n=np.array([-.614239,.614852,.494639]);n/=np.linalg.norm(n)
    assert abs(n@np.array(surfel.normal(surfel.encode(p,n,(0,0,0)))))<.98
    records=[];tangent=np.cross(n,[0,0,1]);tangent/=np.linalg.norm(tangent)
    levels=[]
    for offset in (-.08,0,.08,0):
        hit=p+tangent*offset
        assert not acquire(records,hit,n) and len(records)==1
        levels.append(records[0]['word']>>8&63)
        records[0]['normal']=np.array(surfel.normal(records[0]['word']))
        records[0]['point']=np.array(surfel.point(records[0]['word'],(0,0,0)))
    assert len(set(levels))==1,levels
    word=surfel.encode(p,n,(0,0,0))
    assert surfel.axis(n)!=surfel.axis(surfel.normal(word)), 'Fixture must exercise changed dominantaxis'
    positives=1<<2
    for position in (p+tangent*.03,p-tangent*.03):
        candidate=surfel.encode(position,n,(0,0,0))
        if surfel.axis(surfel.normal(word))!=surfel.axis(surfel.normal(candidate)):positives=0
        positives|=1<<7;word=candidate
    assert positives==(1<<2)|(1<<7), 'Repeatedencodedplane must retain earlierpositivepatch'
    assert 'chromaSurfelAxis(chromaSurfelNormal(records[chosen]))' in source
    # A moving thin solid leaves four old faces in visible air. Its new face
    # is still inside the same occupied quarter-cell, so whole-cell vacancy
    # cannot release an overflow latch. Recycle only at this would-overflow.
    def old_faces():
        result=[]
        for z in (.02,.06,.10,.14):acquire(result,np.array([.125,.125,z]),np.array([0.,0,-1.]))
        return result
    new=np.array([.125,.125,.20]);normal=np.array([0.,0,-1.])
    assert acquire(old_faces(),new,normal), 'Fixture must trigger former overflow'
    visible_air=lambda r:.20>surfel.point(r['word'],(0,0,0))[2]+.0001
    records=old_faces();assert not acquire(records,new,normal,vacant=visible_air)
    assert records[0]['point'][2]==.20 and records[1]['point'][2]==.06
    records=old_faces();assert not acquire(records,new,normal,vacant=visible_air,positives=[1,0,0,0])
    assert records[0]['point'][2]==.02 and records[1]['point'][2]==.20
    records=old_faces();assert acquire(records,new,normal,vacant=visible_air,positives=[1,1,1,1])
    hidden=lambda r:0.>surfel.point(r['word'],(0,0,0))[2]+.0001
    assert acquire(old_faces(),new,normal,vacant=hidden), 'Occluded old planes must be retained'
    assert 'retainedPlanes[i] && positives[i] == 0u' in source
    assert source.index('&& planeFootprintVacant(voxel, points[i], normals[i], size)')<source.index('records.w |= 0x80000000u')
    print('PASS surface acquisition: analytic4x4 alpha mask, quantized retainedplane, unknown retention, wholeplane removal and thin-sliver protection; positive precedence; four-plane junction/merge/overflow; sparse persistent phase equivalence; vertex hoist/layout contract.')


if __name__=='__main__':run()
