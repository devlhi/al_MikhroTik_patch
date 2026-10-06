"""Detached, fail-closed ELF32 MIPS construction analysis (not firmware support).

Four whole-file pins describe six 7.24.4 keyman/mode fixtures: mipsbe and
smips are byte-identical; mmips is little-endian, NOT microMIPS. The real
candidates remain BLOCKED: their final word is live in v0 across a dynamic
PLT dispatch. The local memcpy entry kills v0, but resolver/interposition
safety has not been proved. No caller flag can waive that requirement.

Only a pinned direct three-instruction leaf that kills v0 before use can
pass the narrow call proof below (exercised with synthetic fixtures only).
Loader ten-limb representations, dynamic dispatch and production integration
are unsupported. Never log reconstructed keys or anchor fingerprints.
"""

import hashlib
import struct
from dataclasses import dataclass


@dataclass(frozen=True)
class _Profile:
    start: int
    endian: str
    base: int
    displacement: int
    signed: tuple
    fixed: tuple


_TRIPLES = ((0, 8, 16), (20, 28, 32), (36, 40, 44), (48, 52, 56),
            (60, 64, 68), (72, 76, 80), (84, 88, 92), (96, 100, 108))


def _profile(start, endian, mode, jal):
    return _Profile(
        start, endian, 30 if mode else 29, 0x1510 if mode else 0x78,
        (0, 6, 7) if endian == '>' else (0, 1, 5, 7),
        ((4, 0x27c51530 if mode else 0x27a50058), (12, 0x24060020),
         (24, 0x27c414d0 if mode else 0x27a40018), (104, jal)) +
        (((112, 0x27c31028), (116, 0x27c214d0)) if mode else
         ((112, 0x27a30018), (116, 0x26050020), (120, 0x02201025))),
    )


_PROFILES = {
    '2878f385b84c8da36a8f98ab10cde6f2f77020704b722e56a24a43a6335c90f8':
        _profile(25916, '>', False, 0x0c103398),
    'e43f5642729892be7196128108a1646fcccb6c421f18273be3037bf0dbad92e1':
        _profile(59528, '>', True, 0x0c10453c),
    '6537534a1a4bde10dea0694e9f97d256e9f83df9cb35cdab0211f8210df3fe16':
        _profile(28956, '<', False, 0x0c1033c0),
    '48457c4a8fcc136a9407043514dc4e5e947ae80d9437421bd5ecee338ab09711':
        _profile(59720, '<', True, 0x0c104584),
}


def _overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


def _disjoint(ranges):
    ordered = sorted(ranges)
    return all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:]))


def _signed16(value):
    return value if value < 0x8000 else value - 0x10000


def _control(word):
    op = word >> 26
    return (op in (1, 2, 3, 4, 5, 6, 7, 20, 21, 22, 23, 29)
            or (op == 0 and word & 63 in (8, 9))
            or (op in (16, 17, 18, 19) and (word >> 21) & 31 == 8))


def _target(word, pc):
    op = word >> 26
    if op in (2, 3, 29):
        return ((pc + 4) & 0xf0000000) | ((word & 0x3ffffff) << 2)
    if (op in (1, 4, 5, 6, 7, 20, 21, 22, 23)
            or (op in (16, 17, 18, 19) and (word >> 21) & 31 == 8)):
        return (pc + 4 + 4 * _signed16(word & 0xffff)) & 0xffffffff
    return None


def _elf(data, profile, ranges):
    """Strict ownership plus conservative relocation/direct-entry exclusion.

    Indirect entry cannot be proved generically; identity is restricted by the
    whole-file pins. No arbitrary ELF, MIPS16, microMIPS or writable code.
    """
    e = profile.endian
    marker = 2 if e == '>' else 1
    if len(data) < 52 or data[:7] != b'\x7fELF\x01' + bytes((marker, 1)):
        return None
    h = struct.unpack_from(e + '16sHHIIIIIHHHHHH', data)
    _, kind, machine, ver, entry, phoff, shoff, flags, eh, ps, pn, ss, sn, names = h
    if (kind != 2 or machine != 8 or ver != 1 or flags != 0x70001005
            or eh != 52 or ps != 32 or not 0 < pn <= 128 or ss != 40
            or not 0 < sn <= 4096 or not 0 < names < sn or phoff < 52 or shoff < 52):
        return None
    metadata = [(0, 52), (phoff, phoff + pn * 32), (shoff, shoff + sn * 40)]
    if max(b for a, b in metadata) > len(data) or not _disjoint(metadata):
        return None
    loads = []
    for i in range(pn):
        typ, off, va, _, fs, ms, perm, align = struct.unpack_from(e + '8I', data, phoff + 32*i)
        if off + fs > len(data) or va + ms > 1 << 32:
            return None
        if typ == 1:
            if (fs > ms or not ms or perm & ~7
                    or (align not in (0, 1) and (align & (align-1) or (va-off) % align))):
                return None
            loads.append((off, va, fs, ms, perm))
    if (not loads or not _disjoint([(p[0], p[0]+p[2]) for p in loads if p[2]])
            or not _disjoint([(p[1], p[1]+p[3]) for p in loads])):
        return None
    sections = [struct.unpack_from(e + '10I', data, shoff + i*40) for i in range(sn)]
    if any(sections[0]) or sections[names][1] != 3:
        return None
    file_ranges, allocated, code = [], [], []
    for _, typ, sf, va, off, size, link, info, align, entsize in sections[1:]:
        if (va + size > 1 << 32 or link >= sn
                or (align not in (0, 1) and align & (align-1))):
            return None
        if typ != 8 and size:
            r = (off, off+size)
            if r[1] > len(data) or any(_overlap(r, m) for m in metadata):
                return None
            file_ranges.append(r)
        if sf & 2 and size:
            allocated.append((va, va+size))
        if sf & 4 and size:
            if typ != 1 or sf != 6 or off % 4 or va % 4 or size % 4:
                return None
            owners = [p for p in loads if p[0] <= off and off+size <= p[0]+p[2]
                      and p[1]+off-p[0] == va and p[4] == 5]
            if len(owners) != 1:
                return None
            code.append((off, off+size, va))
    if not _disjoint(file_ranges) or not _disjoint(allocated):
        return None
    string_sec = sections[names]
    strings = data[string_sec[4]:string_sec[4]+string_sec[5]]
    if not strings or strings[0] or strings[-1]:
        return None
    if any(s[0] >= len(strings) for s in sections):
        return None
    addresses = []
    for start, end in ranges:
        owners = [s for s in code if s[0] <= start < end <= s[1]]
        if len(owners) != 1 or start % 4 or end % 4:
            return None
        off, _, va = owners[0]
        first, last = va+start-off, va+end-off
        if first < entry < last:
            return None
        # Starting in an existing delay slot is not a valid construction entry.
        if start > off and _control(struct.unpack_from(e+'I', data, start-4)[0]):
            return None
        addresses.append((first, last))
    for _, typ, _, _, off, size, link, info, _, entsize in sections:
        if typ in (4, 9):
            width = 12 if typ == 4 else 8
            if (entsize != width or size % width or info >= sn
                    or sections[link][1] not in (2, 11)):
                return None
            for pos in range(off, off+size, width):
                target, rinfo = struct.unpack_from(e+'II', data, pos)
                if rinfo >> 8 >= sections[link][5] // 16:
                    return None
                if any(_overlap((target, target+4), a) for a in addresses):
                    return None
        if typ in (2, 11):
            if entsize != 16 or size % 16 or sections[link][1] != 3:
                return None
            for pos in range(off, off+size, 16):
                _, value, _, _, _, idx = struct.unpack_from(e+'IIIBBH', data, pos)
                if idx and any(a < value < b for a, b in addresses):
                    return None
    for off, limit, va in code:
        for pos in range(off, limit, 4):
            word = struct.unpack_from(e+'I', data, pos)[0]
            target = _target(word, va+pos-off)
            if target is not None and any(a < target < b for a, b in addresses):
                return None
    return addresses, code


def _decode(data, start, end, address, endian):
    try:
        from capstone import Cs, CsError, CS_ARCH_MIPS, CS_MODE_MIPS32, CS_MODE_BIG_ENDIAN, CS_MODE_LITTLE_ENDIAN
    except (ImportError, OSError):
        return None
    try:
        decoder = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 |
                     (CS_MODE_BIG_ENDIAN if endian == '>' else CS_MODE_LITTLE_ENDIAN))
        decoder.skipdata = False
        instructions = list(decoder.disasm(data[start:end], address))
        if (len(instructions) != (end-start)//4
                or any(i.size != 4 or i.address != address+4*n for n, i in enumerate(instructions))):
            return None
        return instructions
    except CsError:
        return None


def _candidate(data, old):
    if (not isinstance(data, bytes) or len(data) > 4*1024*1024
            or not isinstance(old, bytes) or len(old) != 32):
        return None
    p = _PROFILES.get(hashlib.sha256(data).hexdigest())
    if p is None:
        return None
    start, end = p.start, p.start + p.fixed[-1][0] + 4
    layout = _elf(data, p, [(start, end)])
    if layout is None:
        return None
    addresses, code = layout
    decoded = _decode(data, start, end, addresses[0][0], p.endian)
    if decoded is None:
        return None
    words = struct.unpack_from(p.endian + 'I'*len(decoded), data, start)
    checked = set()
    order = 'big' if p.endian == '>' else 'little'
    for i, (hi, lo, store) in enumerate(_TRIPLES):
        signed = i in p.signed
        if (words[hi//4] >> 16 != 0x3c02
                or words[lo//4] >> 16 != (0x2442 if signed else 0x3442)
                or words[store//4] != (0xac020000 | p.base << 21 | (p.displacement+4*i))
                or decoded[hi//4].mnemonic != 'lui'
                or decoded[lo//4].mnemonic != ('addiu' if signed else 'ori')
                or decoded[store//4].mnemonic != 'sw'):
            return None
        low = words[lo//4] & 0xffff
        value = (((words[hi//4] & 0xffff) << 16) + (_signed16(low) if signed else low)) & 0xffffffff
        if value.to_bytes(4, order) != old[i*4:i*4+4]:
            return None
        checked.update((hi, lo, store))
    for offset, word in p.fixed:
        if words[offset//4] != word or offset in checked:
            return None
        checked.add(offset)
    if checked != set(range(0, end-start, 4)) or decoded[26].mnemonic != 'jal':
        return None
    # The fixed post-return instructions also kill v0 before any caller use.
    return p, start, end, addresses[0][0], code


def _call_proved(data, candidate):
    """Only an exact direct, in-file leaf is accepted; NO dynamic trust flag.

    MOVE v0,a0; JR ra; NOP neither reads the changed v0 nor preserves it on
    return. Real PLT stubs do not satisfy this proof and stay rejected.
    Returns (callee_start, callee_end) on proof, or None if unproven.
    """
    p, start, end, address, code = candidate
    jal = dict(p.fixed)[104]
    target = _target(jal, address+104)
    owners = [s for s in code if s[2] <= target and target+12 <= s[2]+s[1]-s[0]]
    if len(owners) != 1:
        return None
    off, _, va = owners[0]
    begin = off+target-va
    if _overlap((begin, begin+12), (start, end)):
        return None
    if struct.unpack_from(p.endian+'3I', data, begin) != (0x00801025, 0x03e00008, 0):
        return None
    if _elf(data, p, [(start, end), (begin, begin+12)]) is None:
        return None
    decoded = _decode(data, begin, begin+12, target, p.endian)
    if decoded is None or [i.mnemonic for i in decoded] != ['move', 'jr', 'nop']:
        return None
    return (begin, begin+12)


def inspect_mips_license(data, old):
    """Sanitized candidate report, with no key bytes, digest or replacement.

    Recognizing eight stores is one candidate, NOT one successful replacement.
    Reports reserve the entire envelope, including argument setup, JAL delay
    store and post-return kill, and the immutable leaf callee proof range
    when call dispatch proof succeeds.
    """
    candidate = _candidate(data, old)
    if candidate is None:
        return []
    _, start, end, _, _ = candidate
    callee = _call_proved(data, candidate)
    report = {'start': start, 'end': end, 'buffers': 1,
              'replacement_count': int(callee is not None),
              'status': 'direct-leaf-proved' if callee is not None else 'blocked-unproven-call-dispatch'}
    if callee is not None:
        report['callee_range'] = callee
    return [report]


def _occupied(spans, length):
    result = []
    for span in spans:
        if (not isinstance(span, (tuple, list)) or len(span) != 2
                or any(type(x) is not int for x in span) or not 0 <= span[0] < span[1] <= length):
            raise ValueError('invalid pristine overlap span')
        result.append(tuple(span))
    if not _disjoint(result):
        raise ValueError('overlapping pristine spans')
    return result


def mips_license_matches(data, old, new, *, occupied=()):
    """Zero or one (start, end, replacement) on pristine input, memory only.

    Every occupied pristine span must be supplied by a multi-pattern caller;
    prefer mips_license_plan for automatic all-mapping literal preflight.
    Construction and the full proved callee range are protected from occupied
    spans. A blocked candidate still reserves construction; it NEVER counts as
    coverage. inspect_mips_license exposes the immutable callee_range separately.
    """
    if (not isinstance(data, bytes) or not isinstance(new, bytes)
            or len(new) != 32 or old == new):
        return []
    spans = _occupied(occupied, len(data))
    candidate = _candidate(data, old)
    if candidate is None:
        return []
    p, start, end, _, _ = candidate
    callee = _call_proved(data, candidate)
    protected = [(start, end)] + ([callee] if callee is not None else [])
    if any(_overlap(prot, span) for prot in protected for span in spans):
        raise ValueError('overlapping pristine MIPS envelope or callee')
    if callee is None:
        return []
    replacement = bytearray(data[start:end])
    order = 'big' if p.endian == '>' else 'little'
    for i, (hi, lo, _) in enumerate(_TRIPLES):
        value = int.from_bytes(new[i*4:i*4+4], order)
        high = ((value + (0x8000 if i in p.signed else 0)) >> 16) & 0xffff
        # Change only immediate bits, not byte-order dependent opcode bytes.
        for offset, immediate in ((hi, high), (lo, value & 0xffff)):
            word = struct.unpack_from(p.endian+'I', replacement, offset)[0]
            struct.pack_into(p.endian+'I', replacement, offset, (word & 0xffff0000) | immediate)
    return [(start, end, bytes(replacement))]


def mips_license_plan(data, mappings):
    """Preflight ALL pristine literals/envelopes and immutable callee proof ranges.

    Entries are (mapping_index, start, end, replacement). No mutation, logging,
    literal application, statistics mutation or production coverage integration.
    One returned entry is one 32-byte buffer, never sixteen immediates/eight stores.
    """
    pairs = list(mappings)
    if not isinstance(data, bytes) or not pairs:
        raise ValueError('invalid offline mappings')
    for old, new in pairs:
        if (not isinstance(old, bytes) or not isinstance(new, bytes) or not old
                or len(old) != len(new) or old == new):
            raise ValueError('invalid offline mapping')
    if any(old in new for old, _ in pairs for _, new in pairs):
        raise ValueError('replacement contains a source pattern')
    spans, candidates = [], []
    for index, (old, new) in enumerate(pairs):
        pos = data.find(old)
        while pos >= 0:
            spans.append((pos, pos+len(old)))
            pos = data.find(old, pos+len(old))
        candidate = _candidate(data, old)
        if candidate is not None:
            spans.append((candidate[1], candidate[2]))
            callee = _call_proved(data, candidate)
            if callee is not None:
                spans.append(callee)
            candidates.append((index, old, new))
    if not _disjoint(spans):
        raise ValueError('overlapping pristine literals or MIPS envelopes')
    plans = []
    for index, old, new in candidates:
        plans.extend((index, a, b, replacement) for a, b, replacement in mips_license_matches(data, old, new))
    return plans
