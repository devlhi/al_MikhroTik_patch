"""Pinned 7.24.4 PPC keyman/mode LICENSE construction, not runtime support.

Only two pristine whole-ELF SHA256s are accepted. These source fingerprints
are from docs/evidence/non-x86-key-inspection-2026-10-05.json, NOT vendor
signature verification. No loader preservation, limb conversion, ARM, or MIPS
fallback is provided. Returned envelopes participate in patch.py's pristine
all-mapping overlap preflight. Eight stores count as ONE replacement.
"""

import hashlib
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class _Profile:
    start: int
    base: int
    displacement: int
    triples: tuple
    fixed: tuple


_KEYMAN = _Profile(
    28016, 1, 104,
    ((0, 4, 12), (16, 20, 28), (32, 36, 44), (48, 52, 56),
     (60, 64, 68), (72, 76, 80), (84, 88, 92), (96, 100, 104)),
    # Independent interleaved setup; last LWZ kills the changed r9 value.
    ((8, 0x39400010), (24, 0x391E000F), (40, 0x7D4903A6),
     (108, 0x81210048)),
)
_MODE = _Profile(
    57768, 31, 5360,
    ((0, 8, 16), (20, 24, 32), (36, 40, 48), (52, 56, 60),
     (64, 68, 72), (76, 80, 84), (88, 92, 96), (100, 104, 108)),
    ((4, 0x39000010), (12, 0x39400000), (28, 0x38DF1028),
     (44, 0x7D0903A6), (112, 0x813F1510)),
)
_PROFILES = {
    '66c2ef6de43b9916f59f6f62109cfae5e1d4da62bcd62994128f05dd4d602aa6': _KEYMAN,
    '6544de9285b34b04e6941c3487d353316dfb8cfb230797745afe15a6bf6c3d95': _MODE,
}


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _disjoint(ranges):
    ordered = sorted(ranges)
    return all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:]))


def _elf(data, start, end):
    """Validate file/VA ownership, relocations, symbols and direct branch entry.

    Indirect-entry assumptions are restricted to the two whole-file pins; this
    is deliberately NOT a generic arbitrary-ELF control-flow proof.
    """
    if len(data) < 52 or data[:7] != b'\x7fELF\x01\x02\x01':
        return None
    (ident, kind, machine, version, entry, phoff, shoff, flags, ehsize,
     phsize, phnum, shsize, shnum, shstr) = struct.unpack_from('>16sHHIIIIIHHHHHH', data)
    if (kind != 2 or machine != 20 or version != 1 or flags != 0 or ehsize != 52
            or phsize != 32 or not 0 < phnum < 0xffff or shsize != 40
            or not 0 < shnum < 0xff00 or not 0 < shstr < shnum
            or phoff < 52 or shoff < 52):
        return None
    metadata = [(0, 52), (phoff, phoff + phnum * 32), (shoff, shoff + shnum * 40)]
    if max(r[1] for r in metadata) > len(data) or not _disjoint(metadata):
        return None
    loads = []
    for i in range(phnum):
        ptype, off, va, _, filesz, memsz, perms, align = struct.unpack_from('>8I', data, phoff + i * 32)
        if off + filesz > len(data) or va + memsz > 1 << 32:
            return None
        if ptype != 1:
            continue
        if (filesz > memsz or not memsz or perms & ~7
                or (align not in (0, 1) and (align & (align - 1) or (va - off) % align))):
            return None
        loads.append((off, va, filesz, memsz, perms))
    if (not loads or not _disjoint([(p[0], p[0] + p[2]) for p in loads if p[2]])
            or not _disjoint([(p[1], p[1] + p[3]) for p in loads])):
        return None
    sections = [struct.unpack_from('>10I', data, shoff + i * 40) for i in range(shnum)]
    if any(sections[0]) or sections[shstr][1] != 3:
        return None
    file_ranges, allocated, code = [], [], []
    for _, stype, sf, va, off, size, link, info, align, entsize in sections[1:]:
        if (va + size > 1 << 32 or link >= shnum
                or (align not in (0, 1) and align & (align - 1))):
            return None
        if stype != 8 and size:
            r = (off, off + size)
            if off + size > len(data) or any(_overlap(r, m) for m in metadata):
                return None
            file_ranges.append(r)
        if sf & 2 and size:
            allocated.append((va, va + size))
        if sf & 4 and size:
            if stype != 1 or sf != 6 or off % 4 or va % 4 or size % 4:
                return None
            owners = [p for p in loads if p[0] <= off and off + size <= p[0] + p[2]
                      and p[1] + off - p[0] == va and p[4] == 5]
            if len(owners) != 1:
                return None
            code.append((off, off + size, va))
    if not _disjoint(file_ranges) or not _disjoint(allocated):
        return None
    owners = [s for s in code if s[0] <= start < end <= s[1]]
    if len(owners) != 1 or start % 4 or end % 4:
        return None
    off, _, va = owners[0]
    first, last = va + start - off, va + end - off
    if first < entry < last:
        return None
    for _, stype, _, _, off, size, link, info, _, entsize in sections:
        if stype in (4, 9):  # RELA / REL: any relocation touching the envelope is refused.
            width = 12 if stype == 4 else 8
            if entsize != width or size % width or info >= shnum:
                return None
            for pos in range(off, off + size, width):
                target = struct.unpack_from('>I', data, pos)[0]
                if _overlap((target, target + 4), (first, last)):
                    return None
        if stype in (2, 11):
            if entsize != 16 or size % 16:
                return None
            for pos in range(off, off + size, 16):
                _, value, _, sinfo, _, _ = struct.unpack_from('>IIIBBH', data, pos)
                if sinfo & 15 == 2 and first < value < last:
                    return None
    # Fixed-width PPC branches: reject all direct entries into the middle,
    # including entries at a low-half, a store, or the final register kill.
    for off, limit, va in code:
        for pos in range(off, limit, 4):
            word = struct.unpack_from('>I', data, pos)[0]
            opcode = word >> 26
            if opcode not in (16, 18):
                continue
            bits = 16 if opcode == 16 else 26
            delta = word & ((1 << bits) - 4)
            if delta & (1 << (bits - 1)):
                delta -= 1 << bits
            target = (delta if word & 2 else va + pos - off + delta) & 0xffffffff
            if first < target < last:
                return None
    return first


def ppc_license_matches(data: bytes, old: bytes, new: bytes):
    """Return zero or one (start, end, replacement) on pristine pinned input.

    Unsupported input returns no match, so it cannot contribute coverage.
    All bits outside the sixteen immediate fields remain byte-identical.
    """
    if (not isinstance(old, bytes) or not isinstance(new, bytes)
            or len(old) != 32 or len(new) != 32 or old == new):
        return []
    profile = _PROFILES.get(hashlib.sha256(data).hexdigest())
    if profile is None:
        return []
    start = profile.start
    end = start + profile.fixed[-1][0] + 4
    address = _elf(data, start, end)
    if address is None:
        return []
    try:
        from capstone import Cs, CS_ARCH_PPC, CS_MODE_32, CS_MODE_BIG_ENDIAN
    except (ImportError, OSError):
        return []
    decoder = Cs(CS_ARCH_PPC, CS_MODE_32 | CS_MODE_BIG_ENDIAN)
    decoder.skipdata = False
    decoded = list(decoder.disasm(data[start:end], address))
    if (len(decoded) != (end - start) // 4
            or any(ins.size != 4 or ins.address != address + i * 4
                   for i, ins in enumerate(decoded))):
        return []
    words = struct.unpack_from('>' + 'I' * len(decoded), data, start)
    checked = set()
    replacement = bytearray(data[start:end])
    for i, (hi, lo, store) in enumerate(profile.triples):
        # LIS r9, imm; ORI r9,r9,imm; STW r9,base+4*i. No signed
        # low-half addition, CR updates, base update, or other register allowed.
        if (words[hi // 4] >> 16 != 0x3d20 or words[lo // 4] >> 16 != 0x6129
                or words[store // 4] != (0x91200000 | profile.base << 16
                                         | (profile.displacement + 4 * i))
                or decoded[hi // 4].mnemonic != 'lis'
                or decoded[lo // 4].mnemonic != 'ori'
                or decoded[store // 4].mnemonic != 'stw'):
            return []
        value = (words[hi // 4] & 0xffff) << 16 | (words[lo // 4] & 0xffff)
        if value.to_bytes(4, 'big') != old[i * 4:i * 4 + 4]:
            return []
        replacement[hi + 2:hi + 4] = new[i * 4:i * 4 + 2]
        replacement[lo + 2:lo + 4] = new[i * 4 + 2:i * 4 + 4]
        checked.update((hi, lo, store))
    for offset, word in profile.fixed:
        if words[offset // 4] != word or offset in checked:
            return []
        checked.add(offset)
    if checked != set(range(0, end - start, 4)):
        return []
    return [(start, end, bytes(replacement))]
