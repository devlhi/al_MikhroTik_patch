"""Synthetic keys/ELFs only; optional pinned-cache inspection never transforms.

MIKPATCH_MIPS_FIXTURES names the existing inspection cache. Real anchor values
are reconstructed only in memory, never used in assertion diagnostics or logs.
No configured keys, firmware output, signing or runtime operations.
"""
import contextlib
import dataclasses
import hashlib
import io
import os
from pathlib import Path
import struct
import unittest
from unittest import mock

import mips_license as subject


OLD = bytes(range(32))
NEW = bytes((i*113 + 128) % 256 for i in range(32))
# Independent instruction indices, not matcher triples.
LAYOUT = [(0, 2, 4), (5, 7, 8), (9, 10, 11), (12, 13, 14),
          (15, 16, 17), (18, 19, 20), (21, 22, 23), (24, 25, 27)]
CONFIGS = [(endian, mode) for endian in ('>', '<') for mode in (False, True)]
BASE_VA = 0x400000
START = 272
CALLEE = 640


def construction(endian, mode, key, callee=CALLEE):
    order = 'big' if endian == '>' else 'little'
    signed = {0, 6, 7} if endian == '>' else {0, 1, 5, 7}
    base, disp = (30, 0x1510) if mode else (29, 0x78)
    words = [0] * (30 if mode else 31)
    for i, (hi, lo, store) in enumerate(LAYOUT):
        value = int.from_bytes(key[4*i:4*i+4], order)
        low = value % 65536
        # Independent carry calculation rather than matcher encoder formula.
        signed_low = low - 65536 if low & 32768 else low
        high = ((value - (signed_low if i in signed else low)) // 65536) % 65536
        words[hi] = (15 << 26) | (2 << 16) | high
        words[lo] = ((9 if i in signed else 13) << 26) | (2 << 21) | (2 << 16) | low
        words[store] = (43 << 26) | (base << 21) | (2 << 16) | (disp+4*i)
    extras = {1: 0x27c51530 if mode else 0x27a50058, 3: 0x24060020,
              6: 0x27c414d0 if mode else 0x27a40018,
              26: (3 << 26) | ((BASE_VA+callee) >> 2)}
    extras.update({28: 0x27c31028, 29: 0x27c214d0} if mode else
                  {28: 0x27a30018, 29: 0x26050020, 30: 0x02201025})
    for index, word in extras.items():
        words[index] = word
    return struct.pack(endian + 'I'*len(words), *words)


def fixture(endian='>', mode=False, key=OLD):
    data = bytearray(1224)
    ident = b'\x7fELF\x01' + bytes((2 if endian == '>' else 1, 1)) + bytes(9)
    struct.pack_into(endian+'16sHHIIIIIHHHHHH', data, 0,
                     ident, 2, 8, 1, BASE_VA+256, 52, 1024, 0x70001005,
                     52, 32, 1, 40, 5, 2)
    struct.pack_into(endian+'8I', data, 52, 1, 256, BASE_VA+256, BASE_VA+256,
                     512, 512, 5, 256)
    encoded = construction(endian, mode, key)
    data[START:START+len(encoded)] = encoded
    struct.pack_into(endian+'3I', data, CALLEE, 0x00801025, 0x03e00008, 0)
    data[800] = 0
    struct.pack_into(endian+'10I', data, 1064, 0, 1, 6, BASE_VA+256, 256, 512, 0, 0, 4, 0)
    struct.pack_into(endian+'10I', data, 1104, 0, 3, 0, 0, 800, 1, 0, 0, 1, 0)
    struct.pack_into(endian+'10I', data, 1144, 0, 9, 0, 0, 832, 8, 4, 1, 4, 8)
    struct.pack_into(endian+'10I', data, 1184, 0, 2, 0, 0, 864, 16, 2, 0, 4, 16)
    source_profile = next(p for p in subject._PROFILES.values() if p.endian == endian and (p.base == 30) == mode)
    fixed = tuple((off, int.from_bytes(encoded[off:off+4], 'big' if endian == '>' else 'little'))
                  for off, _ in source_profile.fixed)
    profile = dataclasses.replace(source_profile, start=START, fixed=fixed)
    return bytes(data), profile


def repin(data, profile):
    return mock.patch.dict(subject._PROFILES, {hashlib.sha256(data).hexdigest(): profile}, clear=True)


def reconstruct(data, start, endian):
    """Independent raw MIPS evaluator: registers and ordered stores.

    Skip only unrelated fixed instructions; signed ADDIU wraps at 32 bits.
    Returned bytes are solely for boolean comparisons on real-source tests.
    """
    order = 'big' if endian == '>' else 'little'
    value, memory = None, {}
    for pos in range(start, start+112, 4):
        w = int.from_bytes(data[pos:pos+4], order)
        op, rs, rt, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 65535
        if op == 15 and rs == 0 and rt == 2:
            value = imm << 16
        elif op == 13 and rs == rt == 2:
            value |= imm
        elif op == 9 and rs == rt == 2:
            value = (value + (imm - 65536 if imm & 32768 else imm)) & 0xffffffff
        elif op == 43 and rt == 2:
            if imm in memory or value is None:
                raise ValueError('invalid synthetic store')
            memory[imm] = value.to_bytes(4, order)
    if len(memory) != 8:
        raise ValueError('incomplete construction')
    return b''.join(memory[offset] for offset in sorted(memory))


class MIPSMatcherTests(unittest.TestCase):
    def matches(self, data, profile, old=OLD, new=NEW, **kwargs):
        with repin(data, profile):
            return subject.mips_license_matches(data, old, new, **kwargs)

    def reject_word(self, offset, value, endian='>', mode=False):
        data, profile = fixture(endian, mode)
        changed = bytearray(data)
        struct.pack_into(endian+'I', changed, offset, value)
        self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_all_four_layouts_exact_bytes_one_replacement(self):
        for endian, mode in CONFIGS:
            data, profile = fixture(endian, mode)
            matches = self.matches(data, profile)
            self.assertEqual(len(matches), 1)
            start, end, replacement = matches[0]
            self.assertEqual(replacement, construction(endian, mode, NEW))
            self.assertEqual(end-start, len(replacement))
            output = data[:start]+replacement+data[end:]
            self.assertEqual(len(output), len(data))
            self.assertEqual(reconstruct(output, start, endian), NEW)
            self.assertEqual(output[:start], data[:start])
            self.assertEqual(output[end:], data[end:])
            order = 'big' if endian == '>' else 'little'
            for hi, lo, _ in LAYOUT:
                for index in (hi, lo):
                    before = int.from_bytes(data[start+4*index:start+4*index+4], order)
                    after = int.from_bytes(output[start+4*index:start+4*index+4], order)
                    self.assertEqual(before & 0xffff0000, after & 0xffff0000)
            # Delay-slot SW and post-return kill are retained byte-exact.
            self.assertEqual(output[start+104:end], data[start+104:end])

    def test_signed_carry_boundaries_and_wrap_both_directions(self):
        values = (0x00007fff, 0x00008000, 0x0000ffff, 0xffff7fff,
                  0xffff8000, 0xffffffff, 0x80008000, 0)
        for endian, mode in CONFIGS:
            order = 'big' if endian == '>' else 'little'
            for value in values:
                boundary = value.to_bytes(4, order)*8
                for old, new in ((OLD, boundary), (boundary, NEW)):
                    data, profile = fixture(endian, mode, old)
                    a, b, replacement = self.matches(data, profile, old, new)[0]
                    self.assertEqual(replacement, construction(endian, mode, new))
                    self.assertEqual(reconstruct(data[:a]+replacement+data[b:], a, endian), new)

    def test_hash_gate_any_outside_change_and_repatched_rejected(self):
        data, profile = fixture()
        self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])
        with repin(data, profile):
            changed = bytearray(data)
            changed[900] = 1
            self.assertEqual(subject.mips_license_matches(bytes(changed), OLD, NEW), [])
            a, b, replacement = subject.mips_license_matches(data, OLD, NEW)[0]
            self.assertEqual(subject.mips_license_matches(data[:a]+replacement+data[b:], NEW, OLD), [])

    def test_invalid_keys_and_data(self):
        data, profile = fixture()
        for old, new in ((OLD, OLD), (NEW, OLD), (OLD[:-1], NEW), (OLD, NEW[:-1]),
                         (None, NEW), (OLD, None), (bytearray(OLD), NEW)):
            self.assertEqual(self.matches(data, profile, old, new), [])
        with repin(data, profile):
            self.assertEqual(subject.mips_license_matches(bytearray(data), OLD, NEW), [])

    def test_all_truncated_prefixes_rejected_even_repinned(self):
        data, profile = fixture()
        for length in range(len(data)):
            self.assertEqual(self.matches(data[:length], profile), [])

    def test_header_class_endian_machine_flags_version_type(self):
        data, profile = fixture()
        for off, value in ((4, 2), (5, 1), (6, 2), (17, 3), (19, 20), (23, 2),
                           (39, 1), (41, 51), (43, 31), (47, 39)):
            changed = bytearray(data)
            changed[off] = value
            self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_metadata_bounds_overlap_and_strict_alignment(self):
        for off, value in ((28, 1024), (32, 0xfffffff0), (32, 52), (1064+16, 52),
                           (1064+20, 511), (1104+16, 52), (1104+20, 0xffffffff),
                           (1064+32, 3), (52+28, 3), (52+20, 511)):
            self.reject_word(off, value)

    def test_mandatory_section_load_ownership(self):
        for off, value in ((1064+8, 2), (52+24, 4), (52+24, 7), (52+8, 0x500100),
                           (1064+12, 0x500100), (52+16, 8), (1064+4, 8)):
            self.reject_word(off, value)

    def test_alias_sections_and_segments(self):
        data, profile = fixture()
        for kind in ('section', 'segment'):
            changed = bytearray(data)
            if kind == 'section':
                changed[1144:1184] = data[1064:1104]
            else:
                struct.pack_into('>H', changed, 44, 2)
                changed[84:116] = data[52:84]
            self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_every_opcode_register_store_checked_both_endians(self):
        for endian, mode in CONFIGS:
            data, _ = fixture(endian, mode)
            for hi, lo, store in LAYOUT:
                for index in (hi, lo, store):
                    off = START+4*index
                    word = struct.unpack_from(endian+'I', data, off)[0]
                    for bit in (16, 21, 26):
                        self.reject_word(off, word ^ (1 << bit), endian, mode)

    def test_mixed_signed_unsigned_layout_not_interchangeable(self):
        for endian, mode in CONFIGS:
            data, _ = fixture(endian, mode)
            for _, lo, _ in LAYOUT:
                off = START+4*lo
                word = struct.unpack_from(endian+'I', data, off)[0]
                self.reject_word(off, (word & 0x03ffffff) | ((13 if word >> 26 == 9 else 9) << 26), endian, mode)

    def test_incomplete_duplicate_and_wrong_displacement(self):
        self.reject_word(START+108, 0)
        self.reject_word(START+32, 0xafa20078)
        self.reject_word(START+32, 0xafa20080)
        self.reject_word(START+32, 0xafc2007c)
        self.reject_word(START, 0x3c020000)

    def test_all_fixed_setup_call_and_kill_required(self):
        for endian, mode in CONFIGS:
            _, profile = fixture(endian, mode)
            for offset, _ in profile.fixed:
                self.reject_word(START+offset, 0, endian, mode)

    def test_delay_store_not_nop_or_register_leak(self):
        for endian, mode in CONFIGS:
            self.reject_word(START+108, 0x00402025, endian, mode)  # move a0,v0
            self.reject_word(START+108, 0, endian, mode)
            self.reject_word(START+108, 0xafa30094, endian, mode)

    def test_callee_reads_v0_before_kill_or_no_kill_rejected(self):
        for value in (0x00402025, 0, 0x24420000, 0x03e00008):
            self.reject_word(CALLEE, value)
        self.reject_word(CALLEE+4, 0x00402025)
        self.reject_word(CALLEE+8, 0x00402025)

    def test_unresolved_dynamic_stub_is_inspectable_but_blocked(self):
        data, profile = fixture()
        changed = bytearray(data)
        struct.pack_into('>4I', changed, CALLEE, 0x3c0f0042, 0x8df9d000, 0x03200008, 0x25f8d000)
        data = bytes(changed)
        with repin(data, profile):
            reports = subject.inspect_mips_license(data, OLD)
            self.assertEqual(len(reports), 1)
            self.assertEqual(reports[0]['replacement_count'], 0)
            self.assertEqual(reports[0]['status'], 'blocked-unproven-call-dispatch')
            self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])
            self.assertEqual(subject.mips_license_plan(data, [(OLD, NEW)]), [])
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                subject.mips_license_matches(data, OLD, NEW, occupied=[(START+104, START+108)])

    def test_direct_jump_branch_likely_and_coprocessor_interior_entry(self):
        for target in (START+4, START+8, START+108, START+120, CALLEE+4):
            delta = (target-256-4)//4
            for word in ((2 << 26) | ((BASE_VA+target) >> 2),
                         (3 << 26) | ((BASE_VA+target) >> 2),
                         0x10000000 | (delta & 65535),
                         0x50000000 | (delta & 65535),
                         0x04110000 | (delta & 65535),
                         0x45010000 | (delta & 65535)):
                self.reject_word(256, word)

    def test_starting_in_delay_slot_rejected(self):
        self.reject_word(START-4, 0x10000000)
        self.reject_word(START-4, 0x03e00008)
        self.reject_word(CALLEE-4, 0x10000000)

    def test_entry_and_any_defined_symbol_interior_rejected(self):
        for target in (START+8, START+108, CALLEE+4):
            self.reject_word(24, BASE_VA+target)
            data, profile = fixture()
            changed = bytearray(data)
            for info in (1, 2):
                struct.pack_into('>IIIBBH', changed, 864, 0, BASE_VA+target, 4, info, 0, 1)
                self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_relocations_any_envelope_byte_and_callee(self):
        for target in (START-2, START, START+8, START+108, START+122, CALLEE-2, CALLEE):
            self.reject_word(832, BASE_VA+target)
        for off, value in ((1144+36, 12), (1144+20, 7), (1144+28, 9),
                           (1144+24, 2), (836, 0x100), (1184+36, 8)):
            self.reject_word(off, value)

    def test_malformed_names_and_null_section(self):
        self.reject_word(1024, 1)
        self.reject_word(1064, 1)
        self.reject_word(1104+4, 1)
        self.reject_word(800, 0x41000000)

    def test_decoder_required_partial_and_boundary_mismatch(self):
        data, profile = fixture()
        with repin(data, profile), mock.patch.dict('sys.modules', {'capstone': None}):
            self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])
        with repin(data, profile), mock.patch('capstone.Cs') as cs:
            cs.return_value.disasm.return_value = []
            self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])
            cs.return_value.disasm.return_value = [mock.Mock(size=2, address=BASE_VA+START)]*31
            self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])

    def test_decoder_wrong_mnemonic_rejected(self):
        data, profile = fixture()
        real = subject._decode(data, START, START+124, BASE_VA+START, '>')
        decoded = [mock.Mock(size=i.size, address=i.address, mnemonic=i.mnemonic) for i in real]
        decoded[2].mnemonic = 'ori'
        with repin(data, profile), mock.patch.object(subject, '_decode', return_value=decoded):
            self.assertEqual(subject.mips_license_matches(data, OLD, NEW), [])

    def test_full_envelope_overlap_fixed_arg_delay_and_kill(self):
        data, profile = fixture()
        for a, b in ((START, START+1), (START+4, START+8), (START+104, START+108),
                     (START+108, START+112), (START+120, START+124), (START-1, START+1)):
            with self.assertRaisesRegex(ValueError, 'overlapping'):
                self.matches(data, profile, occupied=[(a, b)])
        self.assertEqual(len(self.matches(data, profile, occupied=[
            (0, START), (START+124, CALLEE), (CALLEE+12, len(data))])), 1)

    def test_callee_proof_overlap_occupied_all_bytes_all_layouts(self):
        for endian, mode in CONFIGS:
            data, profile = fixture(endian, mode)
            for offset in range(12):
                with self.subTest(endian=endian, mode=mode, offset=offset):
                    with self.assertRaisesRegex(ValueError, 'overlapping'):
                        self.matches(data, profile, occupied=[(CALLEE+offset, CALLEE+offset+1)])
            for span in ((CALLEE-1, CALLEE+1), (CALLEE+11, CALLEE+13),
                         (CALLEE, CALLEE+12)):
                with self.subTest(endian=endian, mode=mode, span=span):
                    with self.assertRaisesRegex(ValueError, 'overlapping'):
                        self.matches(data, profile, occupied=[span])

    def test_callee_kill_literal_mapping_rejected_both_orders_all_layouts(self):
        for endian, mode in CONFIGS:
            data, profile = fixture(endian, mode)
            literal = data[CALLEE:CALLEE+4]
            # MOVE a0,v0 reads the modified incoming v0 instead of killing it.
            leak = struct.pack(endian+'I', 0x00402025)
            for mappings in ([(OLD, NEW), (literal, leak)],
                             [(literal, leak), (OLD, NEW)]):
                with self.subTest(endian=endian, mode=mode, order=mappings[0] == (OLD, NEW)):
                    with repin(data, profile), self.assertRaisesRegex(ValueError, 'overlapping'):
                        subject.mips_license_plan(data, mappings)

    def test_report_returns_callee_range_and_whole_leaf_mapping_rejected(self):
        for endian, mode in CONFIGS:
            data, profile = fixture(endian, mode)
            leaf = data[CALLEE:CALLEE+12]
            with repin(data, profile):
                report = subject.inspect_mips_license(data, OLD)[0]
                self.assertEqual(report['callee_range'], (CALLEE, CALLEE+12))
                self.assertEqual(report['replacement_count'], 1)
                for offset in range(12):
                    changed = bytearray(leaf)
                    changed[offset] ^= 1
                    pair = (leaf, bytes(changed))
                    for mappings in ([(OLD, NEW), pair], [pair, (OLD, NEW)]):
                        with self.assertRaisesRegex(ValueError, 'overlapping'):
                            subject.mips_license_plan(data, mappings)
                a, b, replacement = subject.mips_license_matches(data, OLD, NEW,
                    occupied=[(CALLEE-1, CALLEE), (CALLEE+12, CALLEE+13)])[0]
                self.assertEqual((data[:a]+replacement+data[b:])[CALLEE:CALLEE+12], leaf)

    def test_occupied_spans_invalid_and_mutually_overlapping(self):
        data, profile = fixture()
        for spans in ([(1, 1)], [(-1, 1)], [(0, len(data)+1)], [(True, 3)],
                      [('1', 3)], [(1, 4), (3, 6)], [(1, 2, 3)]):
            with self.assertRaises(ValueError):
                self.matches(data, profile, occupied=spans)

    def test_all_mapping_preflight_order_counts_and_no_mutation(self):
        data, profile = fixture()
        altered = bytearray(data)
        altered[900:911] = b'literal-old'
        data = bytes(altered)
        for mappings in ([(OLD, NEW), (b'literal-old', b'literal-new')],
                         [(b'literal-old', b'literal-new'), (OLD, NEW)]):
            before = data
            with repin(data, profile):
                plans = subject.mips_license_plan(data, mappings)
            self.assertEqual(len(plans), 1)
            self.assertEqual(plans[0][0], mappings.index((OLD, NEW)))
            self.assertEqual(data, before)

    def test_plan_rejects_literal_and_envelope_overlap_before_call_proof(self):
        data, profile = fixture()
        for offset in (4, 104, 108, 120):
            literal = data[START+offset:START+offset+4]
            for mappings in ([(OLD, NEW), (literal, b'XXXX')], [(literal, b'XXXX'), (OLD, NEW)]):
                with repin(data, profile), self.assertRaisesRegex(ValueError, 'overlapping'):
                    subject.mips_license_plan(data, mappings)
        changed = bytearray(data)
        changed[900:906] = b'abcdef'
        data = bytes(changed)
        with repin(data, profile), self.assertRaisesRegex(ValueError, 'overlapping'):
            subject.mips_license_plan(data, [(OLD, NEW), (b'abcd', b'1234'), (b'cdef', b'5678')])
        with repin(data, profile), self.assertRaisesRegex(ValueError, 'overlapping'):
            subject.mips_license_plan(data, [(OLD, NEW), (OLD, NEW)])

    def test_plan_invalid_containment_and_no_cascading(self):
        data, profile = fixture()
        for mappings in ([], [(b'', b'')], [(OLD, OLD)], [(OLD, NEW[:-1])],
                         [(b'abc', b'abc')], [(b'abc', b'xyz'), (b'xyz', b'123')]):
            with self.assertRaises(ValueError):
                subject.mips_license_plan(data, mappings)
        with repin(data, profile), self.assertRaisesRegex(ValueError, 'contains'):
            subject.mips_license_plan(data, [(OLD, NEW), (NEW, b'Q'*32)])

    def test_production_detached_zero_coverage_and_no_logs(self):
        import patch
        for endian, mode in CONFIGS:
            data, profile = fixture(endian, mode)
            stats = {b'existing': 7}
            log = io.StringIO()
            with repin(data, profile), contextlib.redirect_stdout(log):
                self.assertEqual(len(subject.mips_license_matches(data, OLD, NEW)), 1)
                result = patch._replace_keys(data, {OLD: NEW}, 'synthetic-mips', stats)
            self.assertEqual(result, data)
            self.assertEqual(stats, {b'existing': 7})
            self.assertEqual(log.getvalue(), '')


class VendorReadOnlyTests(unittest.TestCase):
    def test_pinned_candidates_remain_blocked_no_real_transforms(self):
        root = os.environ.get('MIKPATCH_MIPS_FIXTURES')
        if not root:
            self.skipTest('MIKPATCH_MIPS_FIXTURES unset; no real-cache claim')
        for arch in ('mipsbe', 'mmips', 'smips'):
            for name in ('keyman', 'mode'):
                data = (Path(root)/arch/name).read_bytes()
                profile = subject._PROFILES.get(hashlib.sha256(data).hexdigest())
                self.assertIsNotNone(profile, 'unexpected source fingerprint')
                old = reconstruct(data, profile.start, profile.endian)
                sentinel = NEW if old != NEW else b'Q'*32
                log = io.StringIO()
                with contextlib.redirect_stdout(log):
                    report = subject.inspect_mips_license(data, old)
                    self.assertTrue(len(report) == 1, 'candidate validation failed')
                    self.assertEqual(report[0]['replacement_count'], 0)
                    self.assertEqual(report[0]['status'], 'blocked-unproven-call-dispatch')
                    self.assertEqual(subject.mips_license_matches(data, old, sentinel), [])
                    self.assertEqual(subject.mips_license_plan(data, [(old, sentinel)]), [])
                    for offset in (4, 104, 108, profile.fixed[-1][0]):
                        literal = data[profile.start+offset:profile.start+offset+4]
                        for mappings in ([(old, sentinel), (literal, b'XXXX')],
                                         [(literal, b'XXXX'), (old, sentinel)]):
                            with self.assertRaisesRegex(ValueError, 'overlapping'):
                                subject.mips_license_plan(data, mappings)
                self.assertEqual(log.getvalue(), '')
            loader = (Path(root)/arch/'loader').read_bytes()
            self.assertEqual(subject.mips_license_matches(loader, OLD, NEW), [])


if __name__ == '__main__':
    unittest.main()
