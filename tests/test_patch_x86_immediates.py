"""Synthetic ELF instructions only: no firmware or configured key material."""
import contextlib
import io
import itertools
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest import mock

import patch as patcher

OLD = bytes(range(32))
NEW = bytes(range(32, 64))


def instructions(key, base=-152):
    result = bytearray()
    for index in range(8):
        displacement = base + index * 4
        if -128 <= displacement <= 127:
            result.extend(b'\xc7\x45' + struct.pack('<b', displacement))
        else:
            result.extend(b'\xc7\x85' + struct.pack('<i', displacement))
        result.extend(key[index * 4:index * 4 + 4])
    return bytes(result)


def elf32(code, *, machine=3, flags=6, ranges=None):
    """Small i386 ELF; ranges are executable (file offset, size) pairs."""
    code_offset = 64
    section_offset = (code_offset + len(code) + 3) & ~3
    if ranges is None:
        ranges = [(code_offset, len(code))]
    ident = b'\x7fELF\x01\x01\x01' + bytes(9)
    header = struct.pack('<16sHHIIIIIHHHHHH', ident, 2, machine, 1,
                         0x8048040, 0, section_offset, 0, 52, 0, 0, 40,
                         1 + len(ranges), 0)
    text = b''.join(struct.pack('<10I', 0, 1, flags, 0x8048000 + start,
                                start, size, 0, 0, 4, 0)
                    for start, size in ranges)
    return (header.ljust(code_offset, b'\0') + code).ljust(section_offset, b'\0') + bytes(40) + text


class X86ImmediateReplacementTests(unittest.TestCase):
    def replace(self, data, mapping=None):
        stats = {}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = patcher._replace_keys(data, mapping or {OLD: NEW}, 'synthetic', stats)
        return result, stats, output.getvalue()

    def assertSplitRejected(self, code, ranges):
        data = elf32(code, ranges=ranges)
        result, stats, log = self.replace(data)
        self.assertTrue(result == data, 'ambiguous split-immediate bytes were rewritten')
        self.assertEqual(stats, {})
        self.assertEqual(log, '')

    def assertSplitReplaced(self, code, ranges, expected_code, count=1):
        result, stats, log = self.replace(elf32(code, ranges=ranges))
        self.assertTrue(result == elf32(expected_code, ranges=ranges),
                        'valid split-immediate control was not replaced correctly')
        self.assertEqual(stats, {OLD: count})
        self.assertEqual(log, f'synthetic: mapping 1, replacements={count}\n')

    def test_overlapping_executable_sections_reject_incompatible_boundaries(self):
        for name, prefix in (('operand-size', b'\x66'),
                             ('mov-immediate', b'\xb8'),
                             ('undecodable', b'\x0f\x04')):
            code = prefix + instructions(OLD)
            outer = (64, len(code))
            inner = (64 + len(prefix), len(instructions(OLD)))
            for order, ranges in (('outer-first', [outer, inner]),
                                  ('inner-first', [inner, outer])):
                with self.subTest(prefix=name, order=order):
                    self.assertSplitReplaced(code, [inner], prefix + instructions(NEW))
                    self.assertSplitRejected(code, [outer])
                    self.assertSplitRejected(code, ranges)

    def test_partial_overlap_containment_and_same_start_are_rejected(self):
        code = b'\x66' + instructions(OLD) + b'\x90\x90'
        expected = b'\x66' + instructions(NEW) + b'\x90\x90'
        inner = (65, len(instructions(OLD)))
        for name, other in (
            ('partial-overlap', (64, len(instructions(OLD)))),
            ('strict-containment', (64, len(code))),
            ('same-start-different-end', (65, len(code) - 1)),
        ):
            for ranges in ([other, inner], [inner, other]):
                with self.subTest(shape=name, ranges=ranges):
                    self.assertSplitReplaced(code, [inner], expected)
                    self.assertSplitRejected(code, ranges)

    def test_exact_duplicate_ranges_are_matched_once(self):
        first_code, second_code = instructions(OLD), instructions(OLD, -80)
        first = (64, len(first_code))
        self.assertSplitReplaced(first_code, [first, first], instructions(NEW))
        self.assertSplitReplaced(first_code, [first, first, first], instructions(NEW))
        code = first_code + b'\x90' + second_code
        second = (64 + len(first_code) + 1, len(second_code))
        for ranges in ([first, second, first], [second, first, first]):
            with self.subTest(ranges=ranges):
                self.assertSplitReplaced(code, ranges,
                                         instructions(NEW) + b'\x90' + instructions(NEW, -80),
                                         count=2)

    def test_disjoint_and_adjacent_sections_each_replace_one_whole_key(self):
        first_code, second_code = instructions(OLD), instructions(OLD, -80)
        for gap in (b'', b'\x90\x90\x90'):
            code = first_code + gap + second_code
            first = (64, len(first_code))
            second = (64 + len(first_code) + len(gap), len(second_code))
            for ranges in ([first, second], [second, first]):
                with self.subTest(gap=len(gap), ranges=ranges):
                    self.assertSplitReplaced(code, ranges,
                                             instructions(NEW) + gap + instructions(NEW, -80),
                                             count=2)

    def test_zero_sized_ranges_do_not_claim_executable_bytes(self):
        code = b'\x90\x90\x90' + instructions(OLD) + b'\x90\x90\x90'
        expected = b'\x90\x90\x90' + instructions(NEW) + b'\x90\x90\x90'
        full = (67, len(instructions(OLD)))
        end = full[0] + full[1]
        for start in (64, 67, 68, end, end + 1):
            empty = (start, 0)
            for ranges in ([full, empty], [empty, full]):
                with self.subTest(ranges=ranges):
                    self.assertSplitReplaced(code, ranges, expected)
                    self.assertSplitRejected(code, [empty])

    def test_empty_middle_range_cannot_hide_nonadjacent_overlap(self):
        code = b'\x0f\x04' + instructions(OLD) + b'\x90'
        expected = b'\x0f\x04' + instructions(NEW) + b'\x90'
        outer, empty, inner = (64, len(code)), (65, 0), (66, len(instructions(OLD)))
        # In sorted order, an empty range separates the overlapping endpoints.
        # Ignoring only adjacent pairs that involve empties would miss it.
        for ranges in itertools.permutations([outer, empty, inner]):
            with self.subTest(ranges=ranges):
                self.assertSplitReplaced(code, [empty, inner], expected)
                self.assertSplitRejected(code, ranges)

    def test_ambiguity_rejects_all_instruction_sites_before_decoding(self):
        first_code, second_code = instructions(OLD), instructions(OLD, -80)
        code = first_code + b'\x90\x66' + second_code
        expected = instructions(NEW) + b'\x90\x66' + instructions(NEW, -80)
        first = (64, len(first_code))
        outer = (64 + len(first_code) + 1, 1 + len(second_code))
        inner = (outer[0] + 1, len(second_code))
        for ranges in itertools.permutations([first, outer, inner]):
            with self.subTest(ranges=ranges):
                self.assertSplitReplaced(code, [first, inner], expected, count=2)
                self.assertSplitRejected(code, ranges)

    def test_full_key_in_consecutive_stack_movs_is_replaced_once(self):
        code = b'\x90\x90' + instructions(OLD) + b'\xc3'
        original = elf32(code)
        result, stats, log = self.replace(original)
        expected = elf32(b'\x90\x90' + instructions(NEW) + b'\xc3')
        self.assertTrue(result == expected, 'Full split-immediate key was not replaced')
        self.assertEqual(stats, {OLD: 1})
        self.assertEqual(len(result), len(original))
        self.assertIn('mapping 1, replacements=1', log)
        self.assertNotIn(OLD.hex(), log.lower())
        self.assertNotIn(NEW.hex(), log.lower())

    def test_disp8_disp32_and_mixed_encodings_keep_opcodes_and_destinations(self):
        for base in (-152, -80, 144):
            with self.subTest(base=base):
                result, stats, _ = self.replace(elf32(instructions(OLD, base)))
                self.assertTrue(result == elf32(instructions(NEW, base)))
                self.assertEqual(stats, {OLD: 1})

    def test_instruction_boundaries_and_operand_sizes_reject_false_positives(self):
        # Each prefix/immediate/displacement used to expose the same raw C7
        # sequence, without eight actual consecutive MOV dword [ebp+disp], imm32.
        for name, preceding in (
            ('operand-size', b'\x66'), ('address-size', b'\x67'),
            ('segment', b'\x64'), ('lock', b'\xf0'), ('repeat', b'\xf3'),
            ('mov-immediate', b'\xb8'), ('push-immediate', b'\x68'),
            ('memory-displacement', b'\x8b\x85'),
            ('undecodable', b'\x0f\x04'),
        ):
            with self.subTest(name=name):
                data = elf32(preceding + instructions(OLD))
                result, stats, log = self.replace(data)
                self.assertTrue(result == data, 'non-instruction bytes were rewritten')
                self.assertEqual(stats, {})
                self.assertEqual(log, '')

    def test_unavailable_decoder_never_falls_back_to_raw_scanning(self):
        data = elf32(instructions(OLD))
        with mock.patch.dict('sys.modules', {'capstone': None}):
            result, stats, log = self.replace(data)
        self.assertTrue(result == data)
        self.assertEqual(stats, {})
        self.assertEqual(log, '')

    def test_literal_and_two_split_sites_count_as_three_whole_keys(self):
        code = instructions(OLD) + b'\x90' + instructions(OLD, -80) + OLD
        expected = instructions(NEW) + b'\x90' + instructions(NEW, -80) + NEW
        result, stats, _ = self.replace(elf32(code))
        self.assertTrue(result == elf32(expected))
        self.assertEqual(stats, {OLD: 3})

    def test_wrong_arch_nonexecutable_or_nonelf_sequence_is_not_a_match(self):
        fixtures = [instructions(OLD), elf32(instructions(OLD), machine=40),
                    elf32(instructions(OLD), flags=2)]
        be = bytearray(elf32(instructions(OLD)))
        be[5] = 2
        fixtures.append(bytes(be))
        for data in fixtures:
            with self.subTest(index=fixtures.index(data)):
                result, stats, _ = self.replace(data)
                self.assertTrue(result == data)
                self.assertEqual(stats, {})

    def test_incomplete_nonadjacent_or_wrong_destination_sequences_are_not_matches(self):
        code = instructions(OLD)
        wrong_dst = bytearray(code)
        struct.pack_into('<i', wrong_dst, 12, -120)
        wrong_word = bytearray(code)
        wrong_word[6] ^= 1
        fixtures = [elf32(code[:-1]), elf32(code[:10] + b'\x90' + code[10:]),
                    elf32(bytes(wrong_dst)), elf32(bytes(wrong_word))]
        for data in fixtures:
            with self.subTest(index=fixtures.index(data)):
                result, stats, _ = self.replace(data)
                self.assertTrue(result == data)
                self.assertEqual(stats, {})

    def test_truncated_invalid_section_table_is_not_a_match(self):
        data = elf32(instructions(OLD))
        fixtures = [data[:30], data[:-1]]
        offset = bytearray(data)
        struct.pack_into('<I', offset, 32, len(data) + 4)
        fixtures.append(bytes(offset))
        for original in fixtures:
            result, stats, _ = self.replace(original)
            self.assertTrue(result == original)
            self.assertEqual(stats, {})

    def test_elf_metadata_cannot_alias_executable_bytes(self):
        code = instructions(OLD)
        # Reviewer reproducer: the sequence occupies section headers 1 and 2;
        # section header 3 advertises those metadata bytes as executable.
        alias = bytearray(elf32(b''))
        alias.extend(bytes(224 - len(alias)))
        struct.pack_into('<H', alias, 48, 4)
        alias[104:104 + len(code)] = code
        struct.pack_into('<10I', alias, 184, 0, 1, 6, 0, 104, len(code), 0, 0, 4, 0)
        fixtures = [('section-table-alias', bytes(alias))]

        # Also reject a code range wholly or partially intersecting a program
        # header table, without interpreting its contents as instructions.
        for start in (52, 64, 132):
            alias = bytearray(elf32(code))
            struct.pack_into('<I', alias, 28, start)
            struct.pack_into('<HH', alias, 42, 32, 1)
            fixtures.append((f'program-table-alias-{start}', bytes(alias)))
        alias = bytearray(elf32(code))
        section_offset = struct.unpack_from('<I', alias, 32)[0]
        struct.pack_into('<II', alias, section_offset + 40 + 16, 48, len(code) + 16)
        fixtures.append(('elf-header-alias', bytes(alias)))

        for name, data in fixtures:
            with self.subTest(name=name):
                result, stats, log = self.replace(data)
                self.assertTrue(result == data, 'ELF metadata alias was rewritten')
                self.assertEqual(stats, {})
                self.assertEqual(log, '')

    def test_unsupported_elf_headers_and_unbounded_tables_are_not_matches(self):
        original = elf32(instructions(OLD))
        section_offset = struct.unpack_from('<I', original, 32)[0]
        for name, changes in (
            ('version', [(20, '<I', 0)]),
            ('header-size', [(40, '<H', 0)]),
            ('oversized-header', [(40, '<H', 64)]),
            ('unsupported-type', [(16, '<H', 4)]),
            ('section-without-offset', [(32, '<I', 0)]),
            ('section-without-count', [(48, '<H', 0)]),
            ('program-table-outside-file', [(28, '<I', len(original)), (42, '<HH', 32, 1)]),
            ('program-entry-size', [(28, '<I', 52), (42, '<HH', 0, 1)]),
            ('program-table-over-header', [(28, '<I', 40), (42, '<HH', 32, 1)]),
            ('program-without-offset', [(42, '<HH', 32, 1)]),
            ('program-without-count', [(28, '<I', 52)]),
            ('overlapping-tables', [(28, '<I', section_offset), (42, '<HH', 32, 1)]),
            ('string-table-index', [(50, '<H', 2)]),
        ):
            with self.subTest(name=name):
                data = bytearray(original)
                for offset, fmt, *values in changes:
                    struct.pack_into(fmt, data, offset, *values)
                data = bytes(data)
                result, stats, log = self.replace(data)
                self.assertTrue(result == data, 'invalid ELF header was accepted')
                self.assertEqual(stats, {})
                self.assertEqual(log, '')

    def test_integration_fixture_imports_work_in_module_and_discovery_modes(self):
        environment = {name: os.environ[name] for name in ('PATH', 'HOME', 'TMPDIR')
                       if name in os.environ}
        for arguments in (
            ['tests.test_patch_coverage_integration'],
            ['discover', '-s', 'tests', '-p', 'test_patch_coverage_integration.py'],
        ):
            with self.subTest(arguments=arguments):
                completed = subprocess.run(
                    [sys.executable, '-B', '-m', 'unittest', *arguments, '-v'],
                    cwd=Path(__file__).resolve().parents[1], env=environment,
                    capture_output=True, text=True, timeout=120)
                self.assertEqual(completed.returncode, 0,
                                 completed.stdout + completed.stderr)

    def test_generated_split_key_is_not_searched_for_a_later_mapping(self):
        third = bytes(range(64, 96))
        mapping = {OLD: NEW, NEW: third}
        result, stats, _ = self.replace(elf32(instructions(OLD)), mapping)
        self.assertTrue(result == elf32(instructions(NEW)))
        self.assertEqual(stats, {OLD: 1})

    def test_overlapping_literal_and_instruction_matches_reject_before_stats(self):
        data = elf32(instructions(OLD))
        code_pattern = instructions(OLD)[:32]
        stats = {}
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaisesRegex(ValueError, 'overlap'):
                patcher._replace_keys(data, {OLD: NEW, code_pattern: b'Q' * 32},
                                      'synthetic', stats)
        self.assertEqual(stats, {})
        self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
