"""Exercise coverage with real SquashFS tools and synthetic NPK bytes.

The signing boundary is mocked: no real keys or firmware are used. All
filesystem packing, extraction, traversal, replacement and NPK I/O are real.
"""
import contextlib
import io
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import patch as patcher
from npk import NovaPackage, NpkPartID, NpkNameInfo, NpkFileContainer

# unittest supports both package-module and discover -s tests entry points.
if __package__:
    from .test_patch_x86_immediates import elf32, instructions, OLD, NEW
else:
    from test_patch_x86_immediates import elf32, instructions, OLD, NEW

OLD_A, NEW_A = b'A' * 32, b'B' * 32
OLD_B, NEW_B = b'C' * 32, b'D' * 32
KEYS = {OLD_A: NEW_A, OLD_B: NEW_B}


@unittest.skipUnless(shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'real SquashFS tools are not installed')
class RealSquashfsCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='coverage real tools ')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def run_tool(self, args):
        return subprocess.run(args, check=True, capture_output=True, timeout=60)

    def source(self, kernel, filesystem, *, hardlink=False):
        tree = self.root / 'fixture tree'
        tree.mkdir()
        (tree / 'synthetic.bin').write_bytes(filesystem)
        if hardlink:
            (tree / 'nested').mkdir()
            os.link(tree / 'synthetic.bin', tree / 'nested' / 'alias.bin')
        (tree / 'unrelated.txt').write_text('not a replacement target')
        image = self.root / 'fixture.sfs'
        self.run_tool(['mksquashfs', str(tree), str(image), '-noappend',
                       '-quiet', '-no-progress', '-all-root', '-comp', 'xz',
                       '-processors', '1'])
        package = NovaPackage()
        package[NpkPartID.NAME_INFO].data = NpkNameInfo('system', '7.23.3.final')
        item = NpkFileContainer.NpkFileItem(
            0, 0, b'\0' * 6, 0, 0, 0, 0, 0, 0, 0,  # type: ignore[arg-type]
            b'boot/initrd.rgz', lzma.compress(kernel, check=lzma.CHECK_CRC32))
        package[NpkPartID.FILE_CONTAINER].data = NpkFileContainer([item]).serialize()
        package[NpkPartID.SQUASHFS].data = image.read_bytes()
        path = self.root / 'synthetic input.npk'
        package.save(path)
        return path

    def extract_npk_filesystem(self, path, label):
        package = NovaPackage.load(path)
        filesystem = package[NpkPartID.SQUASHFS].data
        self.assertIsInstance(filesystem, bytes)
        image = self.root / (label + '.sfs')
        image.write_bytes(filesystem)
        extracted = self.root / (label + ' tree')
        self.run_tool(['unsquashfs', '-d', str(extracted), str(image)])
        return extracted

    def assert_hardlink_pair(self, extracted, expected):
        first = extracted / 'synthetic.bin'
        alias = extracted / 'nested' / 'alias.bin'
        self.assertEqual((first.stat().st_dev, first.stat().st_ino),
                         (alias.stat().st_dev, alias.stat().st_ino))
        self.assertEqual(first.read_bytes(), expected)
        self.assertEqual(alias.read_bytes(), expected)

    def test_real_hardlinks_cannot_create_required_coverage(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        source = self.source(b'unrelated kernel', OLD_A + b'C', hardlink=True)
        self.assert_hardlink_pair(self.extract_npk_filesystem(source, 'pristine'), OLD_A + b'C')
        before = source.read_bytes()
        destination = self.root / 'existing output.npk'
        destination.write_bytes(b'must not be overwritten')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, 'no replacement.*2'):
                patcher.patch_npk_file(mapping, b'test-only', b'test-only', source, destination)
        sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'must not be overwritten')

    def test_real_hardlinks_preserve_genuine_replacements_and_topology(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        original = OLD_A + b'C::' + second_pattern
        source = self.source(b'unrelated kernel', original, hardlink=True)
        self.assert_hardlink_pair(self.extract_npk_filesystem(source, 'pristine'), original)
        destination = self.root / 'hardlink output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            reports = patcher.patch_npk_file(mapping, b'test-only', b'test-only', source, destination)
        sign.assert_called_once()
        self.assertEqual(reports[0]['replacements'], [
            {'mapping_index': 1, 'kernel': 0, 'squashfs': 1, 'total': 1},
            {'mapping_index': 2, 'kernel': 0, 'squashfs': 1, 'total': 1},
        ])
        self.assert_hardlink_pair(self.extract_npk_filesystem(destination, 'verified'),
                                  NEW_A + b'C::' + NEW_B)

    def test_complete_coverage_repack_has_expected_decoded_bytes(self):
        source = self.source(b'kernel' + OLD_A, b'filesystem' + OLD_B)
        destination = self.root / 'synthetic output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            reports = patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        sign.assert_called_once()
        self.assertEqual([row['total'] for row in reports[0]['replacements']], [1, 1])
        result = NovaPackage.load(destination)
        container_data = result[NpkPartID.FILE_CONTAINER].data
        assert isinstance(container_data, bytes)
        container = NpkFileContainer.unserialize_from(container_data)
        self.assertEqual(lzma.decompress(next(iter(container)).data), b'kernel' + NEW_A)
        filesystem_data = result[NpkPartID.SQUASHFS].data
        assert isinstance(filesystem_data, bytes)
        repacked = self.root / 'verified.sfs'
        repacked.write_bytes(filesystem_data)
        extracted = self.root / 'verified tree'
        self.run_tool(['unsquashfs', '-d', str(extracted), str(repacked)])
        self.assertEqual((extracted / 'synthetic.bin').read_bytes(), b'filesystem' + NEW_B)
        self.assertEqual((extracted / 'unrelated.txt').read_text(), 'not a replacement target')

    def test_immediate_coverage_is_counted_once_per_hardlinked_inode(self):
        source = self.source(b'unrelated kernel', elf32(instructions(OLD)) + OLD_B,
                             hardlink=True)
        destination = self.root / 'immediate output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            reports = patcher.patch_npk_file({OLD: NEW, OLD_B: NEW_B},
                                            b'test-only', b'test-only', source, destination)
        sign.assert_called_once()
        self.assertEqual(reports[0]['replacements'], [
            {'mapping_index': 1, 'kernel': 0, 'squashfs': 1, 'total': 1},
            {'mapping_index': 2, 'kernel': 0, 'squashfs': 1, 'total': 1},
        ])
        self.assert_hardlink_pair(self.extract_npk_filesystem(destination, 'split-verified'),
                                  elf32(instructions(NEW)) + NEW_B)

    def test_partial_immediate_cannot_satisfy_required_coverage(self):
        source = self.source(b'unrelated kernel', elf32(instructions(OLD)[:-1]) + OLD_B)
        before = source.read_bytes()
        destination = self.root / 'partial immediate output.npk'
        destination.write_bytes(b'must survive')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, 'no replacement.*1'):
                patcher.patch_npk_file({OLD: NEW, OLD_B: NEW_B},
                                      b'test-only', b'test-only', source, destination)
        sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'must survive')

    def test_partial_coverage_preserves_input_and_existing_output(self):
        source = self.source(b'kernel without target A', b'filesystem' + OLD_B)
        before = source.read_bytes()
        destination = self.root / 'existing output.npk'
        destination.write_bytes(b'must not be overwritten')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, 'no replacement.*1'):
                patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'must not be overwritten')


if __name__ == '__main__':
    unittest.main()
