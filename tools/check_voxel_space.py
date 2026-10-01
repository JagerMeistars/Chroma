"""Check compact quarter-cell confidence addressing and LOD reductions."""
from itertools import product
from pathlib import Path
import random
import re

N = 256


def address(v):
    x, y, z = (a & (N - 1) for a in v)
    return (x // 16 + 16 * z, y, 2 * (x & 15))


def contains(v, origin):
    return all(0 <= a - b < N for a, b in zip(v, origin))


def unpack_cell(pixel, lane, origin):
    x, y = pixel
    wrapped = (16 * (x % 16) + lane, y, x // 16)
    return tuple(o + ((w - o) & (N - 1)) for o, w in zip(origin, wrapped))


def reduce_pairs(word):
    v = ((word >> 1) | (word >> 3)) & 0x11111111
    v = (v | (v >> 2)) & 0x05050505
    v = (v | (v >> 4)) & 0x00550055
    v = (v | (v >> 8)) & 0x00005555
    return v | (v << 1)


def check_lod(rng):
    source = (Path(__file__).resolve().parents[1] /
              'assets/chroma/shaders/post/voxel_lod.fsh').read_text()
    masks = re.findall(r'& (0x[0-9A-Fa-f]+)u', source)
    assert masks[:4] == ['0x11111111', '0x05050505', '0x00550055', '0x00005555']
    # Exhaust every single-cell confidence, especially level 1 (not occupied).
    for i in range(16):
        for level in range(4):
            assert reduce_pairs(level << (i * 2)) == (3 << (i // 2 * 2) if level >= 2 else 0)
    assert reduce_pairs(0x55555555) == 0
    for _ in range(10000):
        words = [rng.getrandbits(32) for _ in range(8)]
        low = high = 0
        for i in range(0, 8, 2):
            low |= words[i]
            high |= words[i + 1]
        packed = reduce_pairs(low) | (reduce_pairs(high) << 16)
        reference = 0
        for parent in range(16):
            half, child = parent // 8, (parent % 8) * 2
            occupied = any(((words[yz*2+half] >> ((child+x)*2)) & 3) >= 2
                           for yz in range(4) for x in range(2))
            reference |= int(occupied) * (3 << (parent * 2))
        assert packed == reference
    # Surface base retains four records per fine cell. Empty alpha masks cannot
    # fill the LOD; conservative overflow can, even with no usable surface.
    def surface_occupied(word):
        return bool(word & 0x80000000 or word & 0x40000000 and word >> 14 & 65535)
    for word, expected in ((0,False),(0x40000000,False),(0x40004000,True),(0x80000000,True)):
        assert surface_occupied(word) == expected
    for _ in range(1000):
        records = [rng.getrandbits(32) for _ in range(512)]
        result = sum((3 if any(surface_occupied(w) for w in records[i*32:(i+1)*32]) else 0) << (i*2) for i in range(16))
        for i in range(16):
            assert ((result >> (i*2)) & 3) == (3 if any((w & 0x80000000) != 0 or (w & 0x40000000) != 0 and (w//16384)%65536 != 0 for w in records[i*32:(i+1)*32]) else 0)
    assert 'textureSize(InSampler, 0).y == 16384' in source
    assert 'int record = index * 4' in source and '(word >> 14u) & 65535u' in source
    # Address the eight distinct input words at both supported mip dimensions.
    for n in (256, 128):
        columns, out_columns = n//16, n//32
        for _ in range(1000):
            px, py = rng.randrange((n//2)**2//16), rng.randrange(n//2)
            base = ((px%out_columns)*2+columns*(px//out_columns)*2, py*2)
            packed_addresses = {(base[0]+z*columns+x, base[1]+y)
                                for z,y,x in product(range(2),repeat=3)}
            scalar_addresses = set()
            for cell,z,y,x in product(range(16),range(2),range(2),range(2)):
                cx = (px%out_columns)*32+cell*2+x
                cz = (px//out_columns)*2+z
                scalar_addresses.add((cx//16+columns*cz,py*2+y))
            assert packed_addresses == scalar_addresses and len(packed_addresses)==8


def check():
    rng = random.Random(263)
    # Cross block zero, storage-wrap boundaries, and Minecraft's distant limits.
    origins = [tuple(4 * a - N // 2 for a in xyz) for xyz in
               [(-65, -1, 63), (-1, 0, 1), (0, 0, 0), (63, 64, 65),
                (29_999_900, -64, -29_999_900)]]
    checks = 0
    for origin in origins:
        for step in product((-260, -4, 0, 4, 260), repeat=3):
            old = tuple(o - s for o, s in zip(origin, step))
            for _ in range(50):
                v = tuple(o + rng.randrange(N) for o in origin)
                x, y, shift = address(v)
                assert unpack_cell((x, y), shift // 2, origin) == v
                assert 0 <= x < 4096 and 0 <= y < 256
                # Every lane maps into the current window, even for X origins
                # not divisible by 16. Existing world cells keep the same slot.
                for lane in range(16):
                    cell = unpack_cell((x, y), lane, origin)
                    assert contains(cell, origin)
                    assert address(cell) == (x, y, lane * 2)
                    retained = contains(cell, old)
                    prior_cell = unpack_cell((x, y), lane, old)
                    assert retained == (prior_cell == cell)
                checks += 1
    for _ in range(1000):
        confidence = [rng.randrange(4) for _ in range(16)]
        word = sum(level << (2 * i) for i, level in enumerate(confidence))
        rgba = [(word >> (8 * i)) & 255 for i in range(4)]
        restored = sum(byte << (8 * i) for i, byte in enumerate(rgba))
        assert [(restored >> (2 * i)) & 3 for i in range(16)] == confidence
    check_lod(rng)
    print(f'PASS: {checks} world cells, every packed lane, negative/large coordinates, '
          'window shifts/teleports, 1000 confidence words; packed LOD equals scalar '
          'reference for 10000 random neighborhoods + both mip address layouts')


if __name__ == '__main__':
    check()
