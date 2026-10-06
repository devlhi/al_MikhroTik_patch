"""Synthetic semantic tests plus opt-in read-only pinned vendor-cache checks.

Set MIKPATCH_PPC_FIXTURES to the inspection cache root (containing ppc/keyman
and ppc/mode) for real-source checks. No configured keys, signing, or output
firmware files are used. Keys reconstructed in memory are never logged.
"""
import contextlib
import dataclasses
import hashlib
import io
import os
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import patch
import ppc_license as subject
from npk import NovaPackage, NpkPartID, NpkNameInfo, NpkFileContainer


OLD = bytes(range(32))
NEW = bytes((i * 113 + 0x80) % 256 for i in range(32))
# Deliberately independent layout/encoder, not matcher profile.triples.
LAYOUTS = {
    'keyman': [(0, 1, 3), (4, 5, 7), (8, 9, 11), (12, 13, 14),
               (15, 16, 17), (18, 19, 20), (21, 22, 23), (24, 25, 26)],
    'mode': [(0, 2, 4), (5, 6, 8), (9, 10, 12), (13, 14, 15),
             (16, 17, 18), (19, 20, 21), (22, 23, 24), (25, 26, 27)],
}


def construction(name, value):
    base, disp = (1, 104) if name == 'keyman' else (31, 5360)
    words = [0] * (28 if name == 'keyman' else 29)
    for i, (hi, lo, store) in enumerate(LAYOUTS[name]):
        words[hi] = (15 << 26) | (9 << 21) | int.from_bytes(value[i*4:i*4+2], 'big')
        words[lo] = (24 << 26) | (9 << 21) | (9 << 16) | int.from_bytes(value[i*4+2:i*4+4], 'big')
        words[store] = (36 << 26) | (9 << 21) | (base << 16) | (disp + i*4)
    extras = ({2: 0x39400010, 6: 0x391e000f, 10: 0x7d4903a6, 27: 0x81210048}
              if name == 'keyman' else
              {1: 0x39000010, 3: 0x39400000, 7: 0x38df1028, 11: 0x7d0903a6, 28: 0x813f1510})
    for i, w in extras.items():
        words[i] = w
    return struct.pack('>' + 'I' * len(words), *words)


def fixture(name='keyman'):
    blob = bytearray(1224)
    struct.pack_into('>16sHHIIIIIHHHHHH', blob, 0,
                     b'\x7fELF\x01\x02\x01' + bytes(9), 2, 20, 1,
                     0x10000, 52, 1024, 0, 52, 32, 1, 40, 5, 2)
    struct.pack_into('>8I', blob, 52, 1, 256, 0x10000, 0x10000, 256, 256, 5, 256)
    blob[256:512] = struct.pack('>I', 0x60000000) * 64
    encoded = construction(name, OLD)
    blob[272:272+len(encoded)] = encoded
    struct.pack_into('>10I', blob, 1064, 0, 1, 6, 0x10000, 256, 256, 0, 0, 4, 0)
    struct.pack_into('>10I', blob, 1104, 0, 3, 0, 0, 768, 1, 0, 0, 1, 0)
    struct.pack_into('>10I', blob, 1144, 0, 4, 0, 0, 800, 12, 4, 1, 4, 12)
    struct.pack_into('>10I', blob, 1184, 0, 2, 0, 0, 832, 16, 2, 0, 4, 16)
    profile = dataclasses.replace(subject._KEYMAN if name == 'keyman' else subject._MODE, start=272)
    return bytes(blob), profile


def repin(data, profile):
    return mock.patch.dict(subject._PROFILES, {hashlib.sha256(data).hexdigest(): profile}, clear=True)


def reconstruct(data, start, name):
    """Independent raw PPC evaluator: model signed LIS, logical OR, stack STW."""
    base, displacement = (1, 104) if name == 'keyman' else (31, 5360)
    regs, memory = {}, {}
    end = start + len(construction(name, OLD))
    for offset in range(start, end, 4):
        w = int.from_bytes(data[offset:offset+4], 'big')
        op, rt, ra, imm = w >> 26, (w >> 21) & 31, (w >> 16) & 31, w & 65535
        if op == 15 and rt == 9 and ra == 0:
            signed = imm if imm < 32768 else imm - 65536
            regs[rt] = (signed << 16) & 0xffffffff
        elif op == 24 and rt == 9:
            regs[ra] = regs[rt] | imm
        elif op == 36 and rt == 9:
            if ra != base or imm in memory:
                raise ValueError('invalid synthetic store')
            memory[imm] = regs[rt].to_bytes(4, 'big')
    return b''.join(memory[displacement + 4*i] for i in range(8))


class PPCMatcherTests(unittest.TestCase):
    def matches(self, data, profile):
        with repin(data, profile):
            return subject.ppc_license_matches(data, OLD, NEW)

    def reject_word(self, offset, value, name='keyman'):
        data, profile = fixture(name)
        changed = bytearray(data)
        struct.pack_into('>I', changed, offset, value)
        self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_positive_both_layouts_exact_bytes_and_reconstruction(self):
        for name in LAYOUTS:
            data, profile = fixture(name)
            matches = self.matches(data, profile)
            self.assertEqual(len(matches), 1)
            start, end, replacement = matches[0]
            self.assertEqual(replacement, construction(name, NEW))
            output = data[:start] + replacement + data[end:]
            self.assertEqual(len(output), len(data))
            self.assertTrue(reconstruct(output, start, name) == NEW)
            changed = {i for i, (a, b) in enumerate(zip(data, output)) if a != b}
            expected = {start + 4*p + j for hi, lo, _ in LAYOUTS[name] for p in (hi, lo) for j in (2, 3)}
            self.assertEqual(changed, {i for i in expected if data[i] != output[i]})

    def test_high_and_low_half_boundaries(self):
        data, profile = fixture()
        for word in (0, 0x7fff7fff, 0x80008000, 0xffffffff, 0x00008000, 0x80000000):
            new = word.to_bytes(4, 'big') * 8
            with repin(data, profile):
                a, b, replacement = subject.ppc_license_matches(data, OLD, new)[0]
            output = data[:a] + replacement + data[b:]
            self.assertTrue(reconstruct(output, a, 'keyman') == new)

    def test_production_hash_gate(self):
        data, _ = fixture()
        self.assertEqual(subject.ppc_license_matches(data, OLD, NEW), [])

    def test_wrong_anchor_and_unchanged_mapping(self):
        data, profile = fixture()
        with repin(data, profile):
            for old, new in ((NEW, OLD), (OLD, OLD), (OLD[:-1], NEW), (OLD, NEW[:-1]), (None, NEW)):
                self.assertEqual(subject.ppc_license_matches(data, old, new), [])

    def test_all_truncated_prefixes(self):
        data, profile = fixture()
        for length in range(len(data)):
            self.assertEqual(self.matches(data[:length], profile), [])

    def test_header_machine_endian_class_version_type_and_flags(self):
        data, profile = fixture()
        for off, value in ((4, 2), (5, 1), (6, 2), (17, 3), (19, 8), (19, 40), (23, 2), (39, 1), (41, 51), (43, 31), (47, 39)):
            changed = bytearray(data)
            changed[off] = value
            self.assertEqual(self.matches(bytes(changed), profile), [])

    def test_metadata_overlap_and_out_of_bounds(self):
        for offset, value in ((28, 1024), (32, 0xfffffff0), (32, 52), (1104+16, 52), (1064+16, 40), (1064+20, 0xffffffff)):
            self.reject_word(offset, value)

    def test_executable_mapping_required(self):
        for off, value in ((1064+8, 2), (52+24, 4), (52+24, 7), (52+8, 0x20000), (1064+12, 0x20000), (52+16, 8), (52+20, 4)):
            self.reject_word(off, value)

    def test_alias_sections_and_segments(self):
        data, profile = fixture()
        for kind in ('section', 'segment'):
            altered = bytearray(data)
            if kind == 'section':
                altered[1144:1184] = data[1064:1104]
            else:
                struct.pack_into('>H', altered, 44, 2)
                altered[84:116] = data[52:84]
            self.assertEqual(self.matches(bytes(altered), profile), [])

    def test_wrong_register_or_opcode_each_source(self):
        data, _ = fixture()
        for hi, lo, store in LAYOUTS['keyman']:
            for word_index in (hi, lo, store):
                off = 272 + word_index*4
                word = int.from_bytes(data[off:off+4], 'big')
                self.reject_word(off, word ^ (1 << 21))
                self.reject_word(off, word ^ (1 << 26))

    def test_wrong_word_and_duplicate_nonconsecutive_store(self):
        data, _ = fixture()
        self.reject_word(272+2*4, 0x39490010)  # interleaved use of r9
        self.reject_word(272, int.from_bytes(data[272:276], 'big') ^ 1)
        self.reject_word(272+7*4, 0x91210068)  # duplicate word destination
        self.reject_word(272+7*4, 0x91210070)  # non-consecutive
        self.reject_word(272+7*4, 0x9122006c)  # different base

    def test_all_interleaved_instructions_and_kill_required(self):
        for name in LAYOUTS:
            _, profile = fixture(name)
            for off, _ in profile.fixed:
                self.reject_word(272+off, 0x60000000, name)

    def test_register_leak_or_store_update_rejected(self):
        self.reject_word(272+108, 0x7d234b78)  # mr r3,r9 instead of kill
        self.reject_word(272+12, 0x95210068)  # stwu changes base
        self.reject_word(272+4, 0x39290001)  # addi instead of ORI

    def test_direct_interior_branch_targets(self):
        # relative B, relative BC, absolute B; target low-half / store / kill.
        for target in (276, 284, 380):
            delta = target - 256
            self.reject_word(256, 0x48000000 | delta)
            self.reject_word(256, 0x41820000 | delta)
            self.reject_word(256, 0x48000002 | (0x10000 + target - 256))

    def test_entry_and_symbol_interior_targets(self):
        self.reject_word(24, 0x10014)
        data, profile = fixture()
        altered = bytearray(data)
        struct.pack_into('>IIIBBH', altered, 832, 0, 0x10014, 4, 2, 0, 1)
        self.assertEqual(self.matches(bytes(altered), profile), [])

    def test_relocations_and_malformed_relocation_tables(self):
        for target in (0x10010, 0x10012, 0x1000e, 0x1007c):
            self.reject_word(800, target)
        self.reject_word(1144+36, 8)
        self.reject_word(1144+20, 11)
        self.reject_word(1144+28, 9)

    def test_decoder_unavailable(self):
        data, profile = fixture()
        with repin(data, profile), mock.patch.dict('sys.modules', {'capstone': None}):
            self.assertEqual(subject.ppc_license_matches(data, OLD, NEW), [])

    def test_decoder_partial_or_wrong_boundary(self):
        data, profile = fixture()
        with repin(data, profile), mock.patch('capstone.Cs') as cs:
            cs.return_value.disasm.return_value = []
            self.assertEqual(subject.ppc_license_matches(data, OLD, NEW), [])

    def test_production_only_counts_literal_mapping_not_ppc(self):
        marker = b'synthetic-signing-pattern'
        for name in LAYOUTS:
            data, profile = fixture(name)
            altered = bytearray(data)
            altered[900:900+len(marker)] = marker
            data = bytes(altered)
            for mapping in ({marker: b'X'*len(marker), OLD: NEW}, {OLD: NEW, marker: b'X'*len(marker)}):
                stats = {}
                with repin(data, profile), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(len(subject.ppc_license_matches(data, OLD, NEW)), 1)
                    output = patch._replace_keys(data, mapping, 'synthetic', stats)
                self.assertEqual(stats, {marker: 1})
                self.assertTrue(reconstruct(output, 272, name) == OLD)
                self.assertEqual(output, data[:900] + b'X'*len(marker) + data[900+len(marker):])

    def test_production_does_not_transform_pinned_synthetic_ppc_or_add_coverage(self):
        for name in LAYOUTS:
            data, profile = fixture(name)
            stats = {b'existing': 7}
            log = io.StringIO()
            with repin(data, profile), contextlib.redirect_stdout(log):
                self.assertEqual(len(subject.ppc_license_matches(data, OLD, NEW)), 1)
                output = patch._replace_keys(data, {OLD: NEW}, 'synthetic', stats)
            self.assertEqual(output, data)
            self.assertEqual(stats, {b'existing': 7})
            self.assertEqual(log.getvalue(), '')

    def test_no_ppc_preservation_policy(self):
        data, profile = fixture()
        with repin(data, profile), self.assertRaisesRegex(ValueError, 'loader'):
            patch._replace_keys(data, {OLD: NEW}, 'synthetic', {}, preserve_license=OLD)

    def test_unsupported_has_zero_instruction_coverage(self):
        data, _ = fixture()
        stats = {}
        with contextlib.redirect_stdout(io.StringIO()):
            output = patch._replace_keys(data, {OLD: NEW}, 'unsupported', stats)
        self.assertEqual(output, data)
        self.assertEqual(stats, {})


class PPCProductionSafetyTests(unittest.TestCase):
    def test_partial_ppc_package_cannot_sign_or_write_output(self):
        # Signing literal is present, and both offline LICENSE anchors match,
        # but PPC loader behavior is unresolved: none adds production coverage.
        marker = b'synthetic-signing-pattern'
        mapping = {OLD: NEW, marker: b'X' * len(marker)}
        files = {name: fixture(name) for name in LAYOUTS}
        profiles = {hashlib.sha256(data).hexdigest(): profile
                    for data, profile in files.values()}
        with tempfile.TemporaryDirectory(prefix='ppc-production-safety-') as directory:
            root = Path(directory)
            source = root / 'source.npk'
            package = NovaPackage()
            package[NpkPartID.NAME_INFO].data = NpkNameInfo('system', '7.24.4.final')
            package[NpkPartID.ARCHITECTURE].data = b'ppc'
            package[NpkPartID.FILE_CONTAINER].data = NpkFileContainer([]).serialize()
            package[NpkPartID.SQUASHFS].data = b'synthetic filesystem'
            package.save(source)
            before = source.read_bytes()
            commands = []

            def tools(args, work_dir):
                commands.append(list(args))
                if args[0] != 'unsquashfs':
                    raise AssertionError('partial PPC must stop before repack')
                target = Path(args[args.index('-d') + 1]) / 'nova' / 'bin'
                target.mkdir(parents=True)
                for name, (data, _) in files.items():
                    (target / name).write_bytes(data)
                (target / 'loader').write_bytes(b'unresolved loader')
                (target / 'signing').write_bytes(marker)
                return b'', b''

            for destination_kind in ('existing', 'new', 'in-place'):
                with self.subTest(destination=destination_kind):
                    destination = root / (destination_kind + '.npk')
                    if destination_kind == 'existing':
                        destination.write_bytes(b'existing output must survive')
                    elif destination_kind == 'in-place':
                        destination = None
                    commands.clear()
                    with mock.patch.dict(subject._PROFILES, profiles, clear=True), \
                            mock.patch.object(patch, '_run_tools', side_effect=tools), \
                            mock.patch.object(NovaPackage, 'sign', autospec=True) as sign, \
                            mock.patch.object(NovaPackage, 'save', autospec=True) as save, \
                            contextlib.redirect_stdout(io.StringIO()):
                        for data, _ in files.values():
                            self.assertEqual(len(subject.ppc_license_matches(data, OLD, NEW)), 1)
                        with self.assertRaisesRegex(ValueError, 'mapping.*1.*signing blocked'):
                            patch.patch_npk_file(mapping, b'test-only', b'test-only', source, destination)
                    sign.assert_not_called()
                    save.assert_not_called()
                    self.assertEqual(source.read_bytes(), before)
                    if destination_kind == 'existing':
                        self.assertEqual(destination.read_bytes(), b'existing output must survive')
                    elif destination_kind == 'new':
                        self.assertFalse(destination.exists())
                    self.assertEqual([args[0] for args in commands], ['unsquashfs'])


class VendorReadOnlyTests(unittest.TestCase):
    def test_pinned_ppc_sources_exact_diffs_and_independent_reconstruction(self):
        root = os.environ.get('MIKPATCH_PPC_FIXTURES')
        if not root:
            self.skipTest('MIKPATCH_PPC_FIXTURES not set; no vendor-cache claim')
        for name in LAYOUTS:
            data = (Path(root) / 'ppc' / name).read_bytes()
            # Never assertEqual on real anchor bytes: assertion messages must
            # not expose values even on failure.
            profile = subject._PROFILES.get(hashlib.sha256(data).hexdigest())
            self.assertIsNotNone(profile, 'fixture does not match pinned source')
            old = reconstruct(data, profile.start, name)
            stats = {}
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                production = patch._replace_keys(data, {old: NEW}, 'pinned-source', stats)
            self.assertTrue(production == data, 'production must leave PPC anchor unchanged')
            self.assertFalse(stats, 'PPC anchor must not contribute production coverage')
            self.assertEqual(log.getvalue(), '')
            matches = subject.ppc_license_matches(data, old, NEW)
            self.assertEqual(len(matches), 1)
            start, end, changed = matches[0]
            output = data[:start] + changed + data[end:]
            self.assertTrue(reconstruct(output, start, name) == NEW)
            self.assertTrue(changed == construction(name, NEW))
            allowed = {start+4*p+j for hi, lo, _ in LAYOUTS[name] for p in (hi, lo) for j in (2, 3)}
            differences = {i for i, (a, b) in enumerate(zip(data, output)) if a != b}
            self.assertTrue(differences <= allowed)
            self.assertEqual(len(output), len(data))
            self.assertEqual(subject.ppc_license_matches(output, NEW, OLD), [])
            # Every other inspected target, including PPC loader, stays unsupported.
        for arch in ('arm', 'arm64', 'mipsbe', 'mmips', 'smips', 'ppc'):
            for name in ('keyman', 'mode', 'loader'):
                if arch == 'ppc' and name != 'loader':
                    continue
                data = (Path(root) / arch / name).read_bytes()
                self.assertEqual(subject.ppc_license_matches(data, OLD, NEW), [])


if __name__ == '__main__':
    unittest.main()
