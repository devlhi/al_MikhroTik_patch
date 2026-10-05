"""Version-scoped CHR policy; synthetic keys/ELFs/NPK only, signing mocked."""
import contextlib
import io
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import patch as patcher
from npk import NovaPackage, NpkPartID, NpkPartItem, NpkNameInfo, NpkFileContainer

if __package__:
    from .test_patch_x86_immediates import elf32, instructions, OLD, NEW
else:
    from test_patch_x86_immediates import elf32, instructions, OLD, NEW

SIGN, SIGN_NEW = b'S' * 32, b'T' * 32
KEYS = {SIGN: SIGN_NEW, OLD: NEW}  # LICENSE deliberately is not first.
POLICY = 'chr-x86-7.24.4'


def package(squashfs=b'fixture'):
    result = NovaPackage()
    result._parts = [
        NpkPartItem(NpkPartID.NAME_INFO, NpkNameInfo('system', '7.24.4.final')),
        NpkPartItem(NpkPartID.ARCHITECTURE, b'i386'),
        NpkPartItem(NpkPartID.FILE_CONTAINER, NpkFileContainer([]).serialize()),
        NpkPartItem(NpkPartID.SQUASHFS, squashfs),
        NpkPartItem(NpkPartID.SIGNATURE, bytes(132)),
        NpkPartItem(NpkPartID.ARCHITECTURE, b'I'),
    ]
    return result


class PolicyTests(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def test_scope_accepts_exact_and_single_architecture(self):
        p = package()
        before = list(p._parts)
        patcher._validate_runtime_policy(p, KEYS, POLICY, OLD)
        self.assertEqual(p._parts, before)
        p._parts.pop()
        patcher._validate_runtime_policy(p, KEYS, POLICY, OLD)

    def test_scope_rejects_versions_names_and_unknown_policy(self):
        for version, name, policy in [('7.24.3.final', 'system', POLICY),
                                      ('7.24.4.test', 'system', POLICY),
                                      ('7.24.4.final', 'routeros', POLICY),
                                      ('7.24.4.final', 'system', ''),
                                      ('7.24.4.final', 'system', 'other')]:
            with self.subTest(version=version, name=name, policy=policy):
                p = package()
                p._parts[0].data = NpkNameInfo(name, version)
                with self.assertRaises(ValueError):
                    patcher.patch_npk_package(p, KEYS, policy, OLD)

    def test_scope_rejects_missing_duplicates_conflicts_without_creation(self):
        for part_id in (NpkPartID.NAME_INFO, NpkPartID.FILE_CONTAINER,
                        NpkPartID.SQUASHFS, NpkPartID.SIGNATURE):
            for duplicate in (False, True):
                p = package()
                part = next(part for part in p if part.id == part_id)
                if duplicate:
                    p._parts.append(part)
                else:
                    p._parts.remove(part)
                before = list(p._parts)
                with self.subTest(part=part_id, duplicate=duplicate), self.assertRaises(ValueError):
                    patcher.patch_npk_package(p, KEYS, POLICY, OLD)
                self.assertEqual(p._parts, before)
        for values in ([], [b'x86'], [b'I'], [b'i386', b'arm'],
                       [b'i386', b'i386'], [b'i386', b'I', b'I']):
            p = package()
            p._parts = [part for part in p if part.id != NpkPartID.ARCHITECTURE]
            p._parts[1:1] = [NpkPartItem(NpkPartID.ARCHITECTURE, value) for value in values]
            with self.subTest(values=values), self.assertRaises(ValueError):
                patcher.patch_npk_package(p, KEYS, POLICY, OLD)
        p = package()
        p._parts.insert(1, p._parts.pop())  # I before signature, not accepted.
        with self.assertRaises(ValueError):
            patcher.patch_npk_package(p, KEYS, POLICY, OLD)

    def test_explicit_role_and_multipackage_rejected_before_signing(self):
        for role in (None, b'unknown', bytes(32)):
            with self.assertRaisesRegex(ValueError, 'LICENSE'):
                patcher.patch_npk_package(package(), KEYS, POLICY, role)
        p = package()
        p._packages = [package()]
        with mock.patch.object(NovaPackage, 'load', return_value=p), \
                mock.patch.object(NovaPackage, 'sign') as sign, \
                mock.patch.object(NovaPackage, 'save') as save:
            with self.assertRaisesRegex(ValueError, 'single-package'):
                patcher.patch_npk_file(KEYS, b'fake', b'fake', 'unused', runtime_policy=POLICY,
                                       license_public_key=OLD)
            sign.assert_not_called()
            save.assert_not_called()

    def test_preserve_only_instruction_anchor_keep_literals_signing_and_indices(self):
        data = elf32(instructions(OLD) + b'\x90' + instructions(SIGN)) + OLD + SIGN
        stats = {}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = patcher._replace_keys(data, KEYS, 'loader', stats, OLD)
        expected = elf32(instructions(OLD) + b'\x90' + instructions(SIGN_NEW)) + NEW + SIGN_NEW
        self.assertEqual(result, expected)
        self.assertEqual(stats, {SIGN: 2, OLD: 1})
        self.assertIn('mapping 1, replacements=2', output.getvalue())
        self.assertIn('mapping 2, replacements=1', output.getvalue())

    def test_zero_duplicate_or_wrong_machine_anchor_rejected(self):
        for data in (OLD, elf32(instructions(OLD) * 2), elf32(instructions(OLD), machine=62)):
            stats = {}
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                patcher._replace_keys(data, KEYS, 'loader', stats, OLD)
            self.assertEqual(stats, {})

    def test_preserved_envelope_still_participates_in_overlap_preflight(self):
        data = elf32(instructions(OLD))
        maps = {OLD: NEW, b'\xc7\x85': b'\xc6\x85'}
        stats = {}
        with self.assertRaisesRegex(ValueError, 'overlap'):
            patcher._replace_keys(data, maps, 'loader', stats, OLD)
        self.assertEqual(stats, {})

    def test_missing_decoder_blocks_preservation(self):
        with mock.patch.dict(sys.modules, {'capstone': None}):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                patcher._replace_keys(elf32(instructions(OLD)), KEYS, 'loader', {}, OLD)

    def test_generic_replacement_preserves_regular_file_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'fixture'
            path.write_bytes(OLD)
            os.utime(path, (1700000123, 1700000123))
            before = path.stat().st_mtime_ns
            patcher.patch_squashfs(Path(directory), KEYS)
            self.assertEqual(path.read_bytes(), NEW)
            self.assertEqual(path.stat().st_mtime_ns, before)

    def test_generic_still_replaces_loader_anchor(self):
        data = elf32(instructions(OLD))
        stats = {}
        self.assertEqual(patcher._replace_keys(data, KEYS, 'loader', stats), elf32(instructions(NEW)))
        self.assertEqual(stats, {OLD: 1})

    def test_metadata_listing_rejects_nonroot_and_unknown_lines(self):
        good = b'drwxr-xr-x 0/0 42 2020-01-02 03:04:05 squashfs-root\n'
        for data in (good.replace(b'0/0', b'1000/0'), b'unknown\n', b''):
            with mock.patch.object(patcher, '_run_tools', return_value=(data, b'')):
                with self.assertRaises(ValueError):
                    patcher._squashfs_metadata(Path('fixture'), Path('.'))
        with mock.patch.object(patcher, '_run_tools', return_value=(good, b'')):
            self.assertEqual(len(patcher._squashfs_metadata(Path('fixture'), Path('.'))), 1)

    def test_cli_passes_license_role_explicitly(self):
        environment = {'MIKRO_LICENSE_PUBLIC_KEY': OLD.hex(), 'CUSTOM_LICENSE_PUBLIC_KEY': NEW.hex(),
                       'MIKRO_NPK_SIGN_PUBLIC_KEY': SIGN.hex(), 'CUSTOM_NPK_SIGN_PUBLIC_KEY': SIGN_NEW.hex(),
                       'CUSTOM_LICENSE_PRIVATE_KEY': '11' * 32, 'CUSTOM_NPK_SIGN_PRIVATE_KEY': '22' * 32}
        # Trace at function entry avoids loading firmware or running tools/signing.
        class StopCLI(Exception):
            pass
        captured = {}
        def trace(frame, event, arg):
            if event == 'call' and frame.f_code.co_name == 'patch_npk_file':
                captured.update(frame.f_locals)
                raise StopCLI()
            return trace
        previous = sys.gettrace()
        try:
            with mock.patch.dict(os.environ, environment), \
                    mock.patch.object(sys, 'argv', ['patch.py', 'npk', 'synthetic.npk', '--runtime-policy', POLICY]):
                sys.settrace(trace)
                with self.assertRaises(StopCLI):
                    runpy.run_path(str(Path(patcher.__file__)), run_name='__main__')
        finally:
            sys.settrace(previous)
        self.assertEqual(captured['runtime_policy'], POLICY)
        self.assertEqual(captured['license_public_key'], OLD)


@unittest.skipUnless(shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'real SquashFS tools unavailable')
class RealPolicyTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='chr-policy-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def source(self, *, loader=None, keyman=None, mode=None, allroot=True, loader_link=False):
        tree = self.root / 'tree'
        (tree / 'nova/bin').mkdir(parents=True)
        defaults = {'loader': loader, 'keyman': keyman, 'mode': mode}
        for name, value in defaults.items():
            f = tree / 'nova/bin' / name
            f.write_bytes(value if value is not None else elf32(instructions(OLD)) + SIGN)
            f.chmod(0o755)
        (tree / 'unrelated').write_bytes(b'unchanged')
        os.link(tree / 'unrelated', tree / 'hardlink')
        os.symlink('unrelated', tree / 'symlink')
        if loader_link:
            os.link(tree / 'nova/bin/loader', tree / 'alias')
        for path in [tree] + list(tree.rglob('*')):
            os.utime(path, (1700000123, 1700000123), follow_symlinks=False)
        image = self.root / 'source.sfs'
        args = ['mksquashfs', str(tree), str(image), '-noappend', '-quiet', '-processors', '1',
                '-mkfs-time', '1700000000']
        args += ['-all-root'] if allroot else ['-force-uid', '1001', '-force-gid', '1002']
        subprocess.run(args, check=True, capture_output=True)
        p = package(image.read_bytes())
        src = self.root / 'source.npk'
        p.save(src)
        return src

    def apply(self, src):
        dst = self.root / 'output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            result = patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                            runtime_policy=POLICY, license_public_key=OLD)
            sign.assert_called_once()
        return dst, result[0]

    def reject(self, src, message):
        before = src.read_bytes()
        dst = self.root / 'output.npk'
        dst.write_bytes(b'keep existing')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, message):
                patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                       runtime_policy=POLICY, license_public_key=OLD)
            sign.assert_not_called()
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(dst.read_bytes(), b'keep existing')

    def test_real_round_trip_preserves_anchor_metadata_and_exact_counts(self):
        src = self.source()
        before = src.read_bytes()
        dst, report = self.apply(src)
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(report['replacements'], [
            {'mapping_index': 1, 'kernel': 0, 'squashfs': 3, 'total': 3},
            {'mapping_index': 2, 'kernel': 0, 'squashfs': 2, 'total': 2}])
        self.assertEqual(report['preserved_anchors'], [{'path': 'nova/bin/loader', 'role': 'LICENSE',
                                                       'count': 1, 'counted_as_coverage': False}])
        p = NovaPackage.load(dst)
        image = self.root / 'verify.sfs'
        image.write_bytes(p[NpkPartID.SQUASHFS].data)
        self.assertEqual(patcher._squashfs_time(image.read_bytes()), 1700000000)
        out = self.root / 'verify'
        subprocess.run(['unsquashfs', '-d', str(out), str(image)], check=True,
                       capture_output=True, umask=0)
        self.assertEqual((out / 'nova/bin/loader').read_bytes(), elf32(instructions(OLD)) + SIGN_NEW)
        for name in ('keyman', 'mode'):
            self.assertEqual((out / 'nova/bin' / name).read_bytes(), elf32(instructions(NEW)) + SIGN_NEW)
        self.assertEqual(patcher._tree_metadata(out), patcher._tree_metadata(self.root / 'tree'))
        self.assertEqual([part.data for part in p if part.id == NpkPartID.ARCHITECTURE], [b'i386', b'I'])

    def test_real_private_caller_umask_preserves_original_modes(self):
        src = self.source()
        previous = os.umask(0o077)
        try:
            dst, report = self.apply(src)
            observed = os.umask(0o077)
            self.assertEqual(observed, 0o077, 'parent umask must never be widened')
            self.assertEqual(dst.stat().st_mode & 0o777, 0o600)
            self.assertEqual(report['status'], 'coverage-passed')
            original = NovaPackage.load(src)[NpkPartID.SQUASHFS].data
            repacked = NovaPackage.load(dst)[NpkPartID.SQUASHFS].data
            a, b = self.root / 'metadata-source.sfs', self.root / 'metadata-result.sfs'
            a.write_bytes(original)
            b.write_bytes(repacked)
            self.assertEqual(patcher._squashfs_metadata(a, self.root),
                             patcher._squashfs_metadata(b, self.root))
        finally:
            os.umask(previous)

    def test_real_private_caller_umask_unchanged_on_extraction_failure(self):
        src = self.source()
        real_run = patcher._run_tools
        def fail(args, cwd, **kwargs):
            if args[0] == 'unsquashfs' and '-d' in args:
                raise subprocess.CalledProcessError(1, ['unsquashfs'])
            return real_run(args, cwd, **kwargs)
        previous = os.umask(0o077)
        try:
            with mock.patch.object(patcher, '_run_tools', side_effect=fail), \
                    mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
                with self.assertRaises(subprocess.CalledProcessError):
                    patcher.patch_npk_file(KEYS, b'fake', b'fake', src,
                                           runtime_policy=POLICY, license_public_key=OLD)
                sign.assert_not_called()
            self.assertEqual(os.umask(0o077), 0o077)
        finally:
            os.umask(previous)

    def test_real_missing_keyman_license_blocks_even_with_other_coverage(self):
        self.reject(self.source(keyman=SIGN), 'keyman and mode')

    def test_real_missing_mode_license_blocks_even_with_other_coverage(self):
        self.reject(self.source(mode=SIGN), 'keyman and mode')

    def test_real_nonroot_source_rejected(self):
        self.reject(self.source(allroot=False), 'all-root')

    def test_real_loader_hardlink_rejected(self):
        self.reject(self.source(loader_link=True), 'regular unlinked')

    def test_real_loader_duplicate_anchor_rejected(self):
        self.reject(self.source(loader=elf32(instructions(OLD) * 2) + SIGN), 'exactly one')

    def test_real_loader_without_instruction_anchor_rejected(self):
        self.reject(self.source(loader=OLD + SIGN), 'exactly one')

    def test_real_loader_symlink_rejected(self):
        src = self.source()
        real_run = patcher._run_tools
        def symlink(args, cwd, **kwargs):
            result = real_run(args, cwd, **kwargs)
            if args[0] == 'unsquashfs' and '-d' in args:
                tree = Path(args[args.index('-d') + 1])
                target = tree / 'nova/bin/loader'
                target.unlink()
                target.symlink_to('keyman')
            return result
        with mock.patch.object(patcher, '_run_tools', side_effect=symlink):
            self.reject(src, 'regular unlinked')

    def test_real_missing_loader_rejected(self):
        src = self.source()
        real_run = patcher._run_tools
        def missing(args, cwd, **kwargs):
            result = real_run(args, cwd, **kwargs)
            if args[0] == 'unsquashfs' and '-d' in args:
                (Path(args[args.index('-d') + 1]) / 'nova/bin/loader').unlink()
            return result
        with mock.patch.object(patcher, '_run_tools', side_effect=missing):
            self.reject(src, 'regular unlinked')

    def test_real_hardlink_topology_tamper_blocks_signing(self):
        src = self.source()
        real_run = patcher._run_tools
        def tamper(args, cwd, **kwargs):
            if args[0] == 'mksquashfs':
                target = Path(args[1]) / 'hardlink'
                data, st = target.read_bytes(), target.stat()
                target.unlink()
                target.write_bytes(data)
                os.chmod(target, st.st_mode)
                os.utime(target, ns=(st.st_atime_ns, st.st_mtime_ns))
                # Restore directory mtime so the inode topology is the only delta.
                os.utime(target.parent, (1700000123, 1700000123))
            return real_run(args, cwd, **kwargs)
        with mock.patch.object(patcher, '_run_tools', side_effect=tamper):
            self.reject(src, 'inode/link metadata mismatch')

    def test_real_no_signing_coverage_still_rejected(self):
        data = elf32(instructions(OLD))
        self.reject(self.source(loader=data, keyman=data, mode=data), 'no replacement.*1')

    def test_real_metadata_tamper_blocks_signing(self):
        src = self.source()
        real_run = patcher._run_tools
        def tamper(args, cwd, **kwargs):
            if args[0] == 'mksquashfs':
                target = Path(args[1]) / 'unrelated'
                os.utime(target, (1700000999, 1700000999))
            return real_run(args, cwd, **kwargs)
        with mock.patch.object(patcher, '_run_tools', side_effect=tamper):
            self.reject(src, 'metadata mismatch')


if __name__ == '__main__':
    unittest.main()
