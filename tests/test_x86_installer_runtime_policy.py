"""Separate caller-declared installer policy; synthetic fixtures, never vendor keys.

Only test-local pins are substituted for synthetic inputs. Optional cached-source
inspection is read-only, does not sign, and is not a firmware/runtime test.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import patch as patcher
from npk import NovaPackage, NpkPartID, NpkPartItem, NpkNameInfo

if __package__:
    from . import test_chr_runtime_policy as chr_tests
else:
    import test_chr_runtime_policy as chr_tests

OLD, NEW = chr_tests.OLD, chr_tests.NEW
SIGN, SIGN_NEW, KEYS = chr_tests.SIGN, chr_tests.SIGN_NEW, chr_tests.KEYS
elf32, instructions, package = chr_tests.elf32, chr_tests.instructions, chr_tests.package
POLICY = 'x86-installer-7.24.4'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def synthetic_wire(p):
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'synthetic.npk'
        p.save(source)
        return source.read_bytes()


class InstallerScopeTests(unittest.TestCase):
    def setUp(self):
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def validate(self, p, policy=POLICY, role=OLD, source_npk=None):
        patcher._validate_runtime_policy(p, KEYS, policy, role, source_npk=source_npk)

    def test_exact_source_required_but_chr_remains_unpinned(self):
        p = package()
        wire = synthetic_wire(p)
        self.validate(p, chr_tests.POLICY)
        with self.assertRaisesRegex(ValueError, 'original source_npk'):
            self.validate(p)
        with self.assertRaisesRegex(ValueError, 'exact qualified pristine'):
            self.validate(p, source_npk=wire)
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(wire)):
            self.validate(p, source_npk=wire)
            p._parts.pop()  # even legal architecture layouts need their own exact qualification
            with self.assertRaisesRegex(ValueError, 'exact qualified pristine'):
                self.validate(p, source_npk=wire)
        wire = synthetic_wire(p)
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(wire)):
            self.validate(p, source_npk=wire)  # shared tight single-authoritative-arch contract

    def test_wrong_product_version_architecture_and_policy(self):
        for name, version in [('routeros', '7.24.4.final'), ('chr', '7.24.4.final'),
                              ('system', '7.24.3.final'), ('system', '7.24.4.test')]:
            p = package()
            p._parts[0].data = NpkNameInfo(name, version)
            with self.subTest(name=name, version=version), self.assertRaisesRegex(ValueError, 'system 7.24.4'):
                self.validate(p)
        for arch in (b'x86', b'x86_64', b'arm', b'I'):
            p = package()
            p._parts[1].data = arch
            with self.subTest(arch=arch), self.assertRaisesRegex(ValueError, 'i386'):
                self.validate(p)
        for policy in ('', 'x86-installer', 'x86-installer-7.24.3'):
            with self.assertRaisesRegex(ValueError, 'unsupported'):
                self.validate(package(), policy)

    def test_missing_duplicate_parts_and_trailing_marker_contract(self):
        for part_id in (NpkPartID.NAME_INFO, NpkPartID.SIGNATURE,
                        NpkPartID.FILE_CONTAINER, NpkPartID.SQUASHFS):
            for duplicate in (False, True):
                p = package()
                part = next(x for x in p if x.id == part_id)
                if duplicate:
                    p._parts.append(part)
                else:
                    p._parts.remove(part)
                before = list(p._parts)
                with self.subTest(part=part_id, duplicate=duplicate), self.assertRaises(ValueError):
                    self.validate(p)
                self.assertEqual(p._parts, before)
        for mutate in (
            lambda p: p._parts.insert(1, p._parts.pop()),
            lambda p: p._parts.append(NpkPartItem(NpkPartID.ARCHITECTURE, b'I')),
            lambda p: setattr(p._parts[-1], 'data', b'i386'),
            lambda p: p._parts.append(p._parts.pop(1)),
        ):
            p = package()
            mutate(p)
            with self.assertRaisesRegex(ValueError, 'i386'):
                self.validate(p)
        p = package()
        p._packages = [package()]
        with self.assertRaisesRegex(ValueError, 'single-package'):
            self.validate(p)
        for role in (None, b'unknown', bytes(32)):
            with self.assertRaisesRegex(ValueError, 'LICENSE'):
                self.validate(package(), role=role)

    def test_unknown_file_rejected_before_load_sign_save_including_inplace(self):
        with tempfile.TemporaryDirectory() as directory:
            src, dst = Path(directory) / 'input.npk', Path(directory) / 'out.npk'
            src.write_bytes(b'unknown or repatched input')
            dst.write_bytes(b'existing output')
            for output in (dst, None):
                with mock.patch.object(NovaPackage, 'load') as load, \
                        mock.patch.object(NovaPackage, 'sign') as sign, \
                        mock.patch.object(NovaPackage, 'save') as save:
                    with self.assertRaisesRegex(ValueError, 'exact qualified pristine'):
                        patcher.patch_npk_file(KEYS, b'fake', b'fake', src, output,
                                               runtime_policy=POLICY, license_public_key=OLD)
                    load.assert_not_called()
                    sign.assert_not_called()
                    save.assert_not_called()
            self.assertEqual(src.read_bytes(), b'unknown or repatched input')
            self.assertEqual(dst.read_bytes(), b'existing output')

    def test_raw_envelope_not_normalized_to_source_pin(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / 'source.npk'
            p = package()
            p.save(src)
            data = src.read_bytes()
            self.assertEqual(digest(data), patcher._npk_source_sha256(p))
            with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(data)):
                for altered in (b'BAD!' + data[4:], data[:4] + bytes(4) + data[8:], data + b'junk'):
                    src.write_bytes(altered)
                    with self.assertRaisesRegex(ValueError, 'exact qualified pristine'), \
                            mock.patch.object(NovaPackage, 'sign') as sign, \
                            mock.patch.object(NovaPackage, 'save') as save:
                        patcher.patch_npk_file(KEYS, b'fake', b'fake', src,
                                               runtime_policy=POLICY, license_public_key=OLD)
                    sign.assert_not_called()
                    save.assert_not_called()

    def test_direct_api_rejects_normalized_truncated_wire_before_processing(self):
        wire = synthetic_wire(package())
        self.assertEqual(wire[-7:], struct.pack('<HI', NpkPartID.ARCHITECTURE.value, 1) + b'I')
        malformed = wire[:-5] + struct.pack('<I', 2) + wire[-1:]
        parsed = NovaPackage(malformed[8:])
        # Reproduce the defect: parsing discards the overstated payload length.
        self.assertNotEqual(digest(malformed), digest(wire))
        self.assertEqual(patcher._npk_source_sha256(parsed), digest(wire))
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(wire)):
            for source in (None, malformed, bytearray(wire), digest(wire)):
                with self.subTest(source_type=type(source).__name__), \
                        mock.patch.object(patcher.NpkFileContainer, 'unserialize_from') as container, \
                        mock.patch.object(patcher, 'patch_kernel') as kernel, \
                        mock.patch.object(patcher, '_run_tools') as tools, \
                        mock.patch.object(NovaPackage, 'sign') as sign, \
                        mock.patch.object(NovaPackage, 'save') as save:
                    with self.assertRaises(ValueError):
                        patcher.patch_npk_package(parsed, KEYS, POLICY, OLD, source_npk=source)
                    for downstream in (container, kernel, tools, sign, save):
                        downstream.assert_not_called()
        # Even a test-local pin cannot authorize truncated part boundaries.
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(malformed)), \
                mock.patch.object(patcher.NpkFileContainer, 'unserialize_from') as container:
            with self.assertRaisesRegex(ValueError, 'truncated original source NPK part payload'):
                patcher.patch_npk_package(parsed, KEYS, POLICY, OLD, source_npk=malformed)
            container.assert_not_called()

    def test_direct_api_accepts_original_wire_but_rejects_changed_package(self):
        wire = synthetic_wire(package())
        parsed = NovaPackage(wire[8:])
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(wire)), \
                mock.patch.object(patcher.NpkFileContainer, 'unserialize_from',
                                  side_effect=RuntimeError('validated processing boundary')) as container:
            with self.assertRaisesRegex(RuntimeError, 'validated processing boundary'):
                patcher.patch_npk_package(parsed, KEYS, POLICY, OLD, source_npk=wire)
            container.assert_called_once()
            container.reset_mock()
            parsed[NpkPartID.SQUASHFS].data += b'changed'
            with self.assertRaisesRegex(ValueError, 'exact qualified pristine'):
                patcher.patch_npk_package(parsed, KEYS, POLICY, OLD, source_npk=wire)
            container.assert_not_called()

    def test_cli_passes_distinct_policy_and_explicit_role(self):
        with mock.patch.object(chr_tests, 'POLICY', POLICY):
            chr_tests.PolicyTests.test_cli_passes_license_role_explicitly(self)

    def test_cli_help_and_non_npk_scope(self):
        script = str(Path(patcher.__file__))
        result = subprocess.run([sys.executable, '-B', script, 'npk', '--help'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)
        for text in (POLICY, chr_tests.POLICY, 'caller-declared', 'pinned pristine', 'autodetection'):
            self.assertIn(text, result.stdout)
        for command, inputs in [('kernel', ['input']), ('netinstall', ['input']),
                                ('block', ['dev', 'file'])]:
            result = subprocess.run([sys.executable, '-B', script, command, *inputs,
                                     '--runtime-policy', POLICY], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn('unrecognized arguments', result.stderr)

    def test_component_pins_checked_before_tree_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'nova/bin').mkdir(parents=True)
            data = elf32(instructions(OLD)) + SIGN
            for name in ('loader', 'keyman', 'mode'):
                (root / 'nova/bin' / name).write_bytes(data)
            pins = {name: digest(data) for name in patcher._X86_INSTALLER_COMPONENT_SHA256}
            for target in pins:
                with self.subTest(target=target), mock.patch.object(
                        patcher, '_X86_INSTALLER_COMPONENT_SHA256', {**pins, target: '0' * 64}):
                    stats = {}
                    with self.assertRaisesRegex(ValueError, 'pristine component'):
                        patcher.patch_squashfs(root, KEYS, stats, POLICY, OLD)
                    self.assertEqual(stats, {})
                    for name in pins:
                        self.assertEqual((root / name).read_bytes(), data)
            # No selector still generically changes the loader; no implicit policy.
            patcher.patch_squashfs(root, KEYS)
            self.assertEqual((root / 'nova/bin/loader').read_bytes(),
                             elf32(instructions(NEW)) + SIGN_NEW)

    def test_pin_constants_match_evidence_not_rejected_vendor_named_iso(self):
        evidence = json.loads((Path(patcher.__file__).parent / 'docs/evidence/'
            'x86-installer-runtime-investigation-20261005T181703Z-9c41b8a2.json').read_text())
        self.assertEqual(patcher._X86_INSTALLER_SOURCE_SHA256, evidence['construction']['source_sha256'])
        for name, value in patcher._X86_INSTALLER_COMPONENT_SHA256.items():
            self.assertEqual(value, evidence['component_hashes_remeasured']['vendor_chr_system'][name]['sha256'])
            self.assertNotEqual(value, evidence['component_hashes_remeasured']['vendor_iso_system'][name]['sha256'])


@unittest.skipUnless(os.name == 'posix' and shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'POSIX SquashFS tools unavailable')
class InstallerRealPolicyTests(chr_tests.RealPolicyTests):
    """Run the unchanged CHR metadata/anchor/coverage regression contract for x86 too."""
    def setUp(self):
        super().setUp()
        switch = mock.patch.object(chr_tests, 'POLICY', POLICY)
        switch.start()
        self.addCleanup(switch.stop)

    def source(self, **kwargs):
        src = super().source(**kwargs)
        pins = {name: digest((self.root / 'tree' / name).read_bytes())
                for name in patcher._X86_INSTALLER_COMPONENT_SHA256}
        for key, value in [('_X86_INSTALLER_COMPONENT_SHA256', pins),
                           ('_X86_INSTALLER_SOURCE_SHA256', digest(src.read_bytes()))]:
            replacement = mock.patch.object(patcher, key, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        return src

    def reject(self, src, message):
        with mock.patch.object(NovaPackage, 'save') as save:
            super().reject(src, message)
            save.assert_not_called()

    def test_kernel_and_squashfs_real_mapping_stats_are_separate(self):
        src = self.source()
        p = NovaPackage.load(src)
        fc = chr_tests.NpkFileContainer([chr_tests.NpkFileContainer.NpkFileItem(
            0, 0, bytes(6), 0, 0, 0, 0, 0, 0, 0, b'boot/kernel', SIGN + SIGN)])
        p[NpkPartID.FILE_CONTAINER].data = fc.serialize()
        p.save(src)
        with mock.patch.object(patcher, '_X86_INSTALLER_SOURCE_SHA256', digest(src.read_bytes())), \
                mock.patch.object(patcher, 'patch_kernel', side_effect=lambda data, keys, stats:
                                  patcher._replace_keys(data, keys, 'synthetic kernel', stats)):
            dst, report = self.apply(src)
        self.assertEqual(report['replacements'], [
            {'mapping_index': 1, 'kernel': 2, 'squashfs': 3, 'total': 5},
            {'mapping_index': 2, 'kernel': 0, 'squashfs': 2, 'total': 2}])
        result = chr_tests.NpkFileContainer.unserialize_from(
            NovaPackage.load(dst)[NpkPartID.FILE_CONTAINER].data)
        self.assertEqual(next(iter(result)).data, SIGN_NEW + SIGN_NEW)

    def test_report_label_and_repatch_rejection(self):
        src = self.source()
        dst, report = self.apply(src)
        self.assertEqual(report['runtime_policy'], POLICY)
        self.assertEqual(report['source_qualification']['npk_sha256'], digest(src.read_bytes()))
        self.assertIn('caller-declared', report['source_qualification']['context'])
        self.assertFalse(report['preserved_anchors'][0]['counted_as_coverage'])
        before = dst.read_bytes()
        with mock.patch.object(NovaPackage, 'sign') as sign, mock.patch.object(NovaPackage, 'save') as save:
            with self.assertRaisesRegex(ValueError, 'exact qualified pristine'):
                patcher.patch_npk_file(KEYS, b'fake', b'fake', dst,
                                       runtime_policy=POLICY, license_public_key=OLD)
            sign.assert_not_called()
            save.assert_not_called()
        self.assertEqual(dst.read_bytes(), before)

    def test_preserved_envelope_overlap_blocks_save(self):
        src = self.source()
        with mock.patch.dict(KEYS, {b'\xc7\x85': b'\xc6\x85'}):
            self.reject(src, 'overlap')

    def test_missing_decoder_blocks_save(self):
        src = self.source()
        with mock.patch.dict(sys.modules, {'capstone': None}):
            self.reject(src, 'exactly one')

    def test_other_mappings_and_literal_license_in_loader_remain_active(self):
        src = self.source(loader=elf32(instructions(OLD) + b'\x90' + instructions(SIGN)) + OLD + SIGN)
        dst, report = self.apply(src)
        self.assertEqual([x['total'] for x in report['replacements']], [4, 3])
        image = self.root / 'extra.sfs'
        image.write_bytes(NovaPackage.load(dst)[NpkPartID.SQUASHFS].data)
        out = self.root / 'extra'
        patcher._run_tools(['unsquashfs', '-d', str(out), str(image)], self.root, preserve_modes=True)
        self.assertEqual((out / 'nova/bin/loader').read_bytes(),
            elf32(instructions(OLD) + b'\x90' + instructions(SIGN_NEW)) + NEW + SIGN_NEW)


class OptionalCachedSourceTests(unittest.TestCase):
    def test_cached_qualified_source_read_only_no_keys(self):
        source = Path(os.environ.get('MIKPATCH_X86_INSTALLER_SOURCE_NPK',
            '/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/vendor.npk'))
        if not source.is_file():
            self.skipTest('qualified cached source unavailable; no vendor fixture committed')
        if os.name != 'posix' or not shutil.which('unsquashfs'):
            self.skipTest('POSIX unsquashfs unavailable')
        before = digest(source.read_bytes())
        self.assertEqual(before, patcher._X86_INSTALLER_SOURCE_SHA256)
        p = NovaPackage.load(source)
        self.assertEqual(patcher._npk_source_sha256(p), before)
        wire = source.read_bytes()
        patcher._validate_runtime_policy(p, KEYS, POLICY, OLD, source_npk=wire)
        # Read-only reproduction against the actual cached source, with no keys.
        self.assertEqual(wire[-7:], struct.pack('<HI', NpkPartID.ARCHITECTURE.value, 1) + b'I')
        malformed = wire[:-5] + struct.pack('<I', 2) + wire[-1:]
        parsed = NovaPackage(malformed[8:])
        self.assertEqual(patcher._npk_source_sha256(parsed), before)
        with mock.patch.object(patcher.NpkFileContainer, 'unserialize_from') as container:
            for original in (None, malformed):
                with self.assertRaises(ValueError):
                    patcher.patch_npk_package(parsed, KEYS, POLICY, OLD, source_npk=original)
            container.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / 'source.sfs'
            image.write_bytes(patcher._part(p, NpkPartID.SQUASHFS).data)
            patcher._squashfs_time(image.read_bytes())
            patcher._squashfs_metadata(image, root)
            tree = root / 'tree'
            patcher._run_tools(['unsquashfs', '-d', str(tree), str(image)], root, preserve_modes=True)
            for name, expected in patcher._X86_INSTALLER_COMPONENT_SHA256.items():
                self.assertEqual(digest((tree / name).read_bytes()), expected)
            self.assertEqual(sum(x.is_file() and not x.is_symlink() for x in tree.rglob('*')), 582)
        self.assertEqual(digest(source.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
