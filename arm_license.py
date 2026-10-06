"""Detached, pinned A32 offline matcher; NOT firmware/runtime support.

Only arm/mode 7.24.4's derived fourth dword may change. Literal pools are
read-only: stripped input has no complete pool-alias proof. All other words
must remain identical. Keyman and ARM64-package targets cross an unaudited
call with live values, and loaders have no runtime policy. They are refused.
Whole-file pin is provenance, not vendor signature authentication.
"""
import hashlib
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class _Profile:
    start: int
    pools: tuple


_MODE = _Profile(59732, tuple(range(62244, 62272, 4)))
_PROFILES = {
    '52b6136fb21df26f0ee25167b04b7f219d444721ac6c164129fbe9aa60cbe701': _MODE,
}
_LOADS = (0, 12, 24, 48, 56, 64, 72)
_ADDS = (32, 36, 40)
_FIXED = {4: 0xe5043348, 8: 0xe244ee37, 16: 0xe1a0c004,
          20: 0xe5043344, 28: 0xe5043340, 44: 0xe504333c,
          52: 0xe5043338, 60: 0xe5043334, 68: 0xe5043330,
          76: 0xe504332c, 80: 0xe8be000f}
_MASK = 0xffffffff


def _immediate(bits):
    shift = (bits >> 8) * 2
    byte = bits & 255
    return ((byte >> shift) | (byte << (32 - shift))) & _MASK


# Non-key ISA encoding table; canonical duplicate encodings are deterministic.
_ENCODINGS = {}
for _bits in range(4096):
    _ENCODINGS.setdefault(_immediate(_bits), _bits)
_VALUES = tuple(sorted(_ENCODINGS))


def _solve(delta):
    """Exact modulo-2**32 sum of at most three ARM modified immediates.

    No key-derived cache, no signed/carry approximation. Worst-case bounded
    3073**2 membership probes; refuse values outside this instruction budget.
    """
    delta &= _MASK
    if delta in _ENCODINGS:
        return (_ENCODINGS[delta], 0, 0)
    for a in _VALUES:
        b = (delta - a) & _MASK
        if b in _ENCODINGS:
            return (_ENCODINGS[a], _ENCODINGS[b], 0)
    for a in _VALUES:
        rest = (delta - a) & _MASK
        for b in _VALUES:
            c = (rest - b) & _MASK
            if c in _ENCODINGS:
                return (_ENCODINGS[a], _ENCODINGS[b], _ENCODINGS[c])
    return None


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _disjoint(ranges):
    ordered = sorted(ranges)
    return all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:]))


@dataclass(frozen=True, repr=False)
class OfflineMatch:
    """ONE reconstruction, not three replacements. No production coverage.

    writes are immutable pristine-offset (start,end,bytes) triples. envelopes
    include all instructions (including register kill) AND read-only pools;
    callers must preflight other mappings against ALL of these ranges. No
    data/key-bearing repr is supplied. Never sign/publish from this result.
    """
    writes: tuple
    envelopes: tuple
    count: int = 1

    def preflight(self, other_ranges):
        for start, end in other_ranges:
            if (not isinstance(start, int) or not isinstance(end, int)
                    or start < 0 or end <= start):
                raise ValueError('invalid offline preflight range')
            if any(_overlap((start, end), r) for r in self.envelopes):
                raise ValueError('offline instruction/literal dependency overlap')


def _elf(data, profile):
    """Strict ELF32 LE EM_ARM ownership + static direct-entry/alias checks.

    No claim of a whole-program computed-pointer/Thumb CFG proof. Because
    pools never change, unproven indirect pool aliases remain byte-identical.
    Interior instruction entry assumptions are restricted to the whole-file
    pin, supplemented by exhaustive aligned A32 direct-branch scans.
    """
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x01\x01':
        return None
    (_, kind, machine, version, entry, phoff, shoff, flags, ehsize,
     phsize, phnum, shsize, shnum, shstr) = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    if (kind != 2 or machine != 40 or version != 1 or flags != 0x05000200
            or ehsize != 52 or phsize != 32 or not 0 < phnum < 0xffff
            or shsize != 40 or not 0 < shnum < 0xff00 or not 0 < shstr < shnum
            or phoff < 52 or shoff < 52):
        return None
    metadata = [(0, 52), (phoff, phoff + phnum * 32), (shoff, shoff + shnum * 40)]
    if max(r[1] for r in metadata) > len(data) or not _disjoint(metadata):
        return None
    loads = []
    for i in range(phnum):
        pt, off, va, _, size, mem, perms, align = struct.unpack_from('<8I', data, phoff + 32*i)
        if off + size > len(data) or va + mem > 1 << 32:
            return None
        if pt == 1:
            if (size > mem or not mem or perms & ~7 or
                    (align not in (0, 1) and (align & (align-1) or (va-off) % align))):
                return None
            loads.append((off, va, size, mem, perms))
    if (not loads or not _disjoint([(o, o+s) for o, _, s, _, _ in loads if s])
            or not _disjoint([(v, v+m) for _, v, _, m, _ in loads])):
        return None
    sections = [struct.unpack_from('<10I', data, shoff + 40*i) for i in range(shnum)]
    if any(sections[0]) or sections[shstr][1] != 3:
        return None
    files, allocated, code = [], [], []
    for _, st, sf, va, off, size, link, _, align, _ in sections[1:]:
        if (va+size > 1 << 32 or link >= shnum or
                (align not in (0, 1) and align & (align-1))):
            return None
        if st != 8 and size:
            r = (off, off+size)
            if r[1] > len(data) or any(_overlap(r, m) for m in metadata):
                return None
            files.append(r)
        if sf & 2 and size:
            allocated.append((va, va+size))
        if sf & 4 and size:
            if st != 1 or sf != 6 or off % 4 or va % 4 or size % 4:
                return None
            owners = [p for p in loads if p[0] <= off and off+size <= p[0]+p[2]
                      and p[1]+off-p[0] == va and p[4] == 5]
            if len(owners) != 1:
                return None
            code.append((off, off+size, va))
    if not _disjoint(files) or not _disjoint(allocated):
        return None
    ranges = ((profile.start, profile.start+84),) + tuple((p, p+4) for p in profile.pools)
    if len(profile.pools) != 7 or not _disjoint(ranges):
        return None
    virtual = []
    for a, b in ranges:
        owners = [s for s in code if s[0] <= a < b <= s[1]]
        if len(owners) != 1 or a % 4 or b % 4:
            return None
        off, _, va = owners[0]
        virtual.append((va+a-off, va+b-off))
    first, last = virtual[0]
    if first < entry < last:
        return None
    for _, st, _, _, off, size, _, info, _, entsize in sections:
        if st in (4, 9):
            width = 12 if st == 4 else 8
            if entsize != width or size % width or info >= shnum:
                return None
            for pos in range(off, off+size, width):
                target = struct.unpack_from('<I', data, pos)[0]
                if any(_overlap((target, target+4), r) for r in virtual):
                    return None
        if st in (2, 11):
            if entsize != 16 or size % 16:
                return None
            for pos in range(off, off+size, 16):
                _, value, _, si, _, _ = struct.unpack_from('<IIIBBH', data, pos)
                if si & 15 == 2 and first < (value & ~1) < last:
                    return None
    refs = {p: [] for p in profile.pools}
    for off, limit, va in code:
        for pos in range(off, limit, 4):
            w = struct.unpack_from('<I', data, pos)[0]
            pc = va+pos-off+8
            if w & 0x0e000000 == 0x0a000000:  # B/BL/BLX immediate, all conditions
                delta = (w & 0xffffff) << 2
                if delta & (1 << 25):
                    delta -= 1 << 26
                target = (pc+delta+(2 if w >> 28 == 15 and w & (1 << 24) else 0)) & _MASK
                if first < target < last or any(a <= target < b for a, b in virtual[1:]):
                    return None
            if w & 0x0f7f0000 == 0x051f0000:  # immediate PC-relative LDR incl conditional
                target = pc + ((w & 4095) if w & (1 << 23) else -(w & 4095))
                for p, (a, b) in zip(profile.pools, virtual[1:]):
                    if _overlap((target, target+4), (a, b)):
                        if target != a:
                            return None
                        refs[p].append(pos)
    if any(refs[p] != [profile.start+r] for p, r in zip(profile.pools, _LOADS)):
        return None
    # Explicit absolute pointers into pools refused (even though pools immutable).
    for a, _ in virtual[1:]:
        if struct.pack('<I', a) in data:
            return None
    return first, virtual


def arm_license_matches(data: bytes, old: bytes, new: bytes):
    """Zero/one OfflineMatch. Restricted derived-word-only transformation.

    No literal pool edits; input/output keys never logged or hashed separately.
    Unknown/malformed/unencodable/call-bearing input and repatches fail closed.
    """
    if (not isinstance(data, bytes) or not isinstance(old, bytes) or not isinstance(new, bytes)
            or len(old) != 32 or len(new) != 32 or old == new
            or old[:12] != new[:12] or old[16:] != new[16:]):
        return []
    profile = _PROFILES.get(hashlib.sha256(data).hexdigest())
    if profile is None:
        return []
    checked = _elf(data, profile)
    if checked is None:
        return []
    address, virtual = checked
    try:
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM, CS_MODE_LITTLE_ENDIAN
        decoder = Cs(CS_ARCH_ARM, CS_MODE_ARM | CS_MODE_LITTLE_ENDIAN)
        decoder.skipdata = False
        decoded = list(decoder.disasm(data[profile.start:profile.start+84], address))
    except (ImportError, OSError):
        return []
    if (len(decoded) != 21 or any(i.size != 4 or i.address != address+4*j
                                  for j, i in enumerate(decoded))):
        return []
    words = struct.unpack_from('<21I', data, profile.start)
    for offset, expected in _FIXED.items():
        if words[offset//4] != expected:
            return []
    for offset, pool, (va, _) in zip(_LOADS, profile.pools, virtual[1:]):
        delta = va-(address+offset+8)
        if not 0 <= delta <= 4095 or words[offset//4] != 0xe59f3000 | delta:
            return []
        if decoded[offset//4].mnemonic != 'ldr':
            return []
    for offset in _ADDS:
        if words[offset//4] & ~4095 != 0xe2833000 or decoded[offset//4].mnemonic != 'add':
            return []
    # The exact kill loads r0..r3 from lr, whose setup is unchanged. Therefore
    # intermediate arithmetic results cannot escape in r3 or flags (S=0).
    if decoded[20].mnemonic not in ('ldm', 'ldmip', 'ldmia'):
        return []
    values = [struct.unpack_from('<I', data, p)[0] for p in profile.pools]
    values.insert(3, (values[2]+sum(_immediate(words[o//4] & 4095) for o in _ADDS)) & _MASK)
    if struct.pack('<8I', *values) != old:
        return []
    delta = (int.from_bytes(new[12:16], 'little')-values[2]) & _MASK
    encoded = _solve(delta)
    if encoded is None or sum(_immediate(b) for b in encoded) & _MASK != delta:
        return []
    writes = tuple((profile.start+o, profile.start+o+4, struct.pack('<I', 0xe2833000 | b))
                   for o, b in zip(_ADDS, encoded))
    changed = b''.join(w[2] for w in writes)
    roundtrip = list(decoder.disasm(changed, address+32))
    if len(roundtrip) != 3 or any(i.size != 4 or i.mnemonic != 'add' for i in roundtrip):
        return []
    envelopes = ((profile.start, profile.start+84),) + tuple((p, p+4) for p in profile.pools)
    return [OfflineMatch(writes, envelopes)]
