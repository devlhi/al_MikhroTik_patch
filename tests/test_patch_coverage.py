"""Synthetic patch coverage tests; no firmware, real keys, or signing.

Only the external SquashFS commands and crypto-signing boundary are faked.
The NPK container, FILE_CONTAINER, XZ, traversal and patch code are real.
"""
import contextlib
import io
import lzma
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

import patch as patcher
from npk import NovaPackage, NpkPartID, NpkNameInfo, NpkFileContainer

OLD_A, NEW_A = b'A' * 32, b'B' * 32
OLD_B, NEW_B = b'C' * 32, b'D' * 32
KEYS = {OLD_A: NEW_A, OLD_B: NEW_B}


class PackageCoverageTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='patch-coverage-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        previous = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, previous)
        self.squash_content = b'unrelated synthetic file'
        self.commands = []
        self.real_run_tools = patcher._run_tools
        self.tools = mock.patch.object(patcher, '_run_tools', side_effect=self.fake_tools)
        self.tools.start()
        self.addCleanup(self.tools.stop)
        self.signing = mock.patch.object(NovaPackage, 'sign', autospec=True)
        self.sign = self.signing.start()
        self.addCleanup(self.signing.stop)
        self.output = io.StringIO()
        self.quiet = contextlib.redirect_stdout(self.output)
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def fake_tools(self, command, work_dir):
        args = shlex.split(command) if isinstance(command, str) else list(command)
        self.commands.append(args)
        if args[0] == 'unsquashfs':
            target = Path(args[args.index('-d') + 1])
            target.mkdir(parents=True)
            (target / 'synthetic.bin').write_bytes(self.squash_content)
        elif args[0] == 'mksquashfs':
            Path(args[2]).write_bytes(b'synthetic repacked filesystem')
        elif args[0] != 'rm':
            raise AssertionError('unexpected external command')
        return b'', b''

    def source(self, payload=b'no expected key here', name='system'):
        package = NovaPackage()
        package[NpkPartID.NAME_INFO].data = NpkNameInfo(name, '7.23.3.final')
        item = NpkFileContainer.NpkFileItem(
            0, 0, b'\0' * 6, 0, 0, 0, 0, 0, 0, 0,  # type: ignore[arg-type]  # Legacy struct uses 6s.
            b'boot/initrd.rgz', lzma.compress(payload, check=lzma.CHECK_CRC32))
        package[NpkPartID.FILE_CONTAINER].data = NpkFileContainer([item]).serialize()
        package[NpkPartID.SQUASHFS].data = b'synthetic filesystem input'
        path = self.root / 'input.npk'
        package.save(path)
        return path

    def test_zero_matches_blocks_signing_and_preserves_files(self):
        source = self.source()
        before = source.read_bytes()
        destination = self.root / 'output.npk'
        destination.write_bytes(b'existing output must survive')
        with self.assertRaisesRegex(ValueError, 'replacement'):
            patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'existing output must survive')
        self.assertFalse(any(command[0] == 'mksquashfs' for command in self.commands))

    def test_complete_coverage_can_be_split_between_kernel_and_filesystem(self):
        # Neither fragment contains both patterns. Only package-wide coverage
        # should be mandatory; an unrelated file must remain acceptable.
        source = self.source(b'prefix' + OLD_A + OLD_A + b'suffix')
        self.squash_content = b'filesystem' + OLD_B
        destination = self.root / 'output.npk'
        reports = patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_called_once()
        self.assertTrue(destination.is_file())
        self.assertEqual(reports[0]['status'], 'coverage-passed')
        self.assertEqual(reports[0]['replacements'], [
            {'mapping_index': 1, 'kernel': 2, 'squashfs': 0, 'total': 2},
            {'mapping_index': 2, 'kernel': 0, 'squashfs': 1, 'total': 1},
        ])
        result = NovaPackage.load(destination)
        container_bytes = result[NpkPartID.FILE_CONTAINER].data
        self.assertIsInstance(container_bytes, bytes)
        assert isinstance(container_bytes, bytes)
        container = NpkFileContainer.unserialize_from(container_bytes)
        decoded = lzma.decompress(next(iter(container)).data)
        self.assertEqual(decoded, b'prefix' + NEW_A + NEW_A + b'suffix')

    def test_partial_coverage_blocks_signing(self):
        source = self.source(b'prefix' + OLD_B)
        destination = self.root / 'output.npk'
        with self.assertRaisesRegex(ValueError, 'mapping.*1'):
            patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_not_called()
        self.assertFalse(destination.exists())

    def test_non_system_addon_remains_a_sign_only_operation(self):
        source = self.source(name='wireless')
        destination = self.root / 'output.npk'
        reports = patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_called_once()
        self.assertEqual(reports[0]['status'], 'not-system')
        self.assertEqual(self.commands, [])

    def test_report_and_logs_never_disclose_pattern_bytes(self):
        source = self.source(b'prefix' + OLD_A + OLD_B)
        reports = patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
        import json
        text = self.output.getvalue() + json.dumps(reports)
        for pattern in (*KEYS.keys(), *KEYS.values()):
            self.assertNotIn(pattern.hex(), text.lower())
            self.assertNotIn(pattern[:16].hex(), text.lower())
        self.assertIn('mapping 1', self.output.getvalue())
        self.assertIn('mapping 2', self.output.getvalue())

    def test_kernel_only_or_filesystem_only_coverage_is_valid(self):
        for kernel, filesystem in ((OLD_A + OLD_B, b'unrelated'),
                                   (b'unrelated', OLD_A + OLD_B)):
            with self.subTest(location='kernel' if kernel.startswith(OLD_A) else 'filesystem'):
                self.sign.reset_mock()
                source = self.source(kernel)
                self.squash_content = filesystem
                reports = patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
                self.sign.assert_called_once()
                self.assertEqual([row['total'] for row in reports[0]['replacements']], [1, 1])

    def test_invalid_mappings_stop_before_any_tool_or_signature(self):
        invalid = ({}, {b'': b''}, {OLD_A: OLD_A}, {OLD_A: b'short'},
                   {OLD_A: NEW_A, NEW_A: NEW_B}, {'not-bytes': NEW_A})
        for mapping in invalid:
            with self.subTest(mapping_index=invalid.index(mapping)):
                source = self.source(OLD_A + OLD_B)
                before = source.read_bytes()
                with self.assertRaisesRegex(ValueError, 'replacement'):
                    patcher.patch_npk_file(mapping, b'test-only', b'test-only', source)
                self.sign.assert_not_called()
                self.assertEqual(self.commands, [])
                self.assertEqual(source.read_bytes(), before)

    def test_failure_cleans_isolated_workspace_without_touching_cwd_files(self):
        source = self.source()
        sentinel = self.root / 'squashfs-root.sfs'
        sentinel.write_bytes(b'belongs to someone else')
        with self.assertRaises(ValueError):
            patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
        self.assertEqual(sentinel.read_bytes(), b'belongs to someone else')
        self.assertTrue(self.commands)
        workspace = Path(self.commands[0][self.commands[0].index('-d') + 1]).parent
        self.assertNotEqual(workspace, self.root)
        self.assertFalse(workspace.exists())

    def test_repack_failure_never_signs_or_changes_source(self):
        source = self.source(OLD_A + OLD_B)
        before = source.read_bytes()

        def fail_repack(command, work_dir):
            if command[0] == 'mksquashfs':
                raise OSError('synthetic repack failure')
            return self.fake_tools(command, work_dir)

        with mock.patch.object(patcher, '_run_tools', side_effect=fail_repack):
            with self.assertRaisesRegex(OSError, 'synthetic repack failure'):
                patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
        self.sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        workspace = Path(self.commands[0][self.commands[0].index('-d') + 1]).parent
        self.assertFalse(workspace.exists())

    def test_empty_repack_never_signs(self):
        source = self.source(OLD_A + OLD_B)
        before = source.read_bytes()

        def empty_repack(command, work_dir):
            result = self.fake_tools(command, work_dir)
            if command[0] == 'mksquashfs':
                Path(command[2]).write_bytes(b'')
            return result

        with mock.patch.object(patcher, '_run_tools', side_effect=empty_repack):
            with self.assertRaisesRegex(ValueError, 'empty repacked'):
                patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
        self.sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)

    def test_multi_package_failure_blocks_entire_file_signature(self):
        first = NovaPackage.load(self.source(name='wireless'))
        missing = NovaPackage.load(self.source())
        source = self.root / 'input.npk'
        container = NovaPackage()
        container._packages = [first, missing]
        destination = self.root / 'output.npk'
        with mock.patch.object(NovaPackage, 'load', return_value=container):
            with self.assertRaisesRegex(ValueError, 'replacement'):
                patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_not_called()
        self.assertFalse(destination.exists())

    def test_fragment_api_keeps_bytes_result_and_optional_counts(self):
        blob = lzma.compress(OLD_A + OLD_A, check=lzma.CHECK_CRC32)
        stats = {}
        result = patcher.patch_initrd_xz(blob, KEYS, False, stats=stats)
        self.assertIsInstance(result, bytes)
        self.assertEqual(lzma.decompress(result), NEW_A + NEW_A)
        self.assertEqual(stats, {OLD_A: 2})
        unrelated = lzma.compress(b'no matching bytes', check=lzma.CHECK_CRC32)
        self.assertEqual(lzma.decompress(patcher.patch_initrd_xz(unrelated, KEYS, False)),
                         b'no matching bytes')

    def test_filesystem_traversal_does_not_follow_external_symlinks(self):
        external = self.root / 'external.bin'
        external.write_bytes(OLD_A + OLD_B)
        tree = self.root / 'tree'
        tree.mkdir()
        (tree / 'link').symlink_to(external)
        local = tree / 'local.bin'
        local.write_bytes(OLD_A)
        stats = {}
        patcher.patch_squashfs(tree, KEYS, stats)
        self.assertEqual(external.read_bytes(), OLD_A + OLD_B)
        self.assertEqual(local.read_bytes(), NEW_A)
        self.assertEqual(stats, {OLD_A: 1})

    def test_identical_contents_on_distinct_inodes_are_each_counted(self):
        tree = self.root / 'separate files'
        tree.mkdir()
        first = tree / 'one.bin'
        second = tree / 'two.bin'
        first.write_bytes(OLD_A)
        second.write_bytes(OLD_A)
        self.assertNotEqual((first.stat().st_dev, first.stat().st_ino),
                            (second.stat().st_dev, second.stat().st_ino))
        stats = {}
        patcher.patch_squashfs(tree, KEYS, stats)
        self.assertEqual(stats, {OLD_A: 2})
        self.assertEqual(first.read_bytes(), NEW_A)
        self.assertEqual(second.read_bytes(), NEW_A)

    def test_hardlink_aliases_cannot_create_coverage_or_clobber_bytes(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        tree = self.root / 'hardlinks'
        (tree / 'nested').mkdir(parents=True)
        first = tree / 'original.bin'
        alias = tree / 'nested' / 'alias.bin'
        first.write_bytes(OLD_A + b'C')
        os.link(first, alias)
        before_identity = (first.stat().st_dev, first.stat().st_ino)
        self.assertEqual(before_identity, (alias.stat().st_dev, alias.stat().st_ino))
        stats = {}
        patcher.patch_squashfs(tree, mapping, stats)
        self.assertEqual(stats, {OLD_A: 1})
        self.assertEqual(first.read_bytes(), NEW_A + b'C')
        self.assertEqual(alias.read_bytes(), NEW_A + b'C')
        self.assertEqual((first.stat().st_dev, first.stat().st_ino), before_identity)
        self.assertEqual((alias.stat().st_dev, alias.stat().st_ino), before_identity)

    def test_affix_cascade_cannot_create_required_coverage(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        source = self.source(OLD_A + b'C')
        before = source.read_bytes()
        destination = self.root / 'output.npk'
        destination.write_bytes(b'existing output must survive')
        with self.assertRaisesRegex(ValueError, 'replacement.*2'):
            patcher.patch_npk_file(mapping, b'test-only', b'test-only', source, destination)
        self.sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'existing output must survive')

    def test_affix_generated_match_does_not_clobber_a_replacement(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        stats = {}
        result = patcher._replace_keys(OLD_A + b'C', mapping, 'synthetic', stats)
        self.assertEqual(stats, {OLD_A: 1})
        self.assertEqual(result, NEW_A + b'C')

    def test_original_match_replaced_without_touching_an_introduced_match(self):
        second_pattern = b'B' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        stats = {}
        original = OLD_A + b'C::' + second_pattern
        result = patcher._replace_keys(original, mapping, 'synthetic', stats)
        self.assertEqual(result, NEW_A + b'C::' + NEW_B)
        self.assertEqual(stats, {OLD_A: 1, second_pattern: 1})

    def test_overlapping_original_patterns_are_rejected_before_counting(self):
        second_pattern = b'A' * 31 + b'C'
        mapping = {OLD_A: NEW_A, second_pattern: NEW_B}
        stats = {}
        with self.assertRaisesRegex(ValueError, 'overlap'):
            patcher._replace_keys(OLD_A + b'C', mapping, 'synthetic', stats)
        self.assertEqual(stats, {})

    def test_completed_system_package_cannot_cover_a_later_partial_package(self):
        complete = NovaPackage.load(self.source(OLD_A + OLD_B))
        partial = NovaPackage.load(self.source(OLD_B))
        source = self.root / 'input.npk'
        before = source.read_bytes()
        container = NovaPackage()
        container._packages = [complete, partial]
        destination = self.root / 'output.npk'
        destination.write_bytes(b'existing output must survive')
        with mock.patch.object(NovaPackage, 'load', return_value=container):
            with self.assertRaisesRegex(ValueError, 'replacement.*1'):
                patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source, destination)
        self.sign.assert_not_called()
        self.assertEqual(source.read_bytes(), before)
        self.assertEqual(destination.read_bytes(), b'existing output must survive')
        self.assertEqual(sum(command[0] == 'mksquashfs' for command in self.commands), 1)

    def test_repack_command_is_explicitly_non_appending(self):
        source = self.source(OLD_A + OLD_B)
        patcher.patch_npk_file(KEYS, b'test-only', b'test-only', source)
        repacks = [command for command in self.commands if command[0] == 'mksquashfs']
        self.assertEqual(len(repacks), 1)
        self.assertIn('-noappend', repacks[0])

    def test_squashfs_tool_wrapper_passes_literal_argv_without_shell(self):
        command = ['unsquashfs', '-d', 'path with spaces; no-shell', 'input.sfs']
        with mock.patch.object(patcher.subprocess, 'run') as run:
            completed = subprocess.CompletedProcess(command, 0, stdout=b'ok', stderr=b'')
            run.return_value = completed
            # Bypass the setUp adapter so the real wrapper is exercised.
            result = self.real_run_tools(command, self.root)
            self.assertEqual(result, (b'ok', b''))
            run.assert_called_once_with(command, cwd=self.root, check=True,
                                        stdout=patcher.subprocess.PIPE,
                                        stderr=patcher.subprocess.PIPE)


if __name__ == '__main__':
    unittest.main()
