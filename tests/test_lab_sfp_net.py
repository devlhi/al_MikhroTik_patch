"""Lab SFP-DOM net patch: pinned hunks, fail-closed pins, metadata parity.

Synthetic fixtures use test-local pins only. The optional cached-source test
applies the real pinned hunks to the real pristine vendor net read-only; no
keys, signing, or firmware execution.
"""
import contextlib
import hashlib
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import patch as patcher
from npk import NovaPackage, NpkPartID

if __package__:
    from . import test_chr_runtime_policy as chr_tests
    from . import test_x86_installer_runtime_policy as installer_tests
else:
    import test_chr_runtime_policy as chr_tests
    import test_x86_installer_runtime_policy as installer_tests

POLICY = 'x86-installer-7.24.4'
OLD, NEW, KEYS = chr_tests.OLD, chr_tests.NEW, chr_tests.KEYS
elf32, instructions, package = chr_tests.elf32, chr_tests.instructions, chr_tests.package


def digest(data):
    return hashlib.sha256(data).hexdigest()


SYNTHETIC_NET = bytearray(patcher._LAB_SFP_NET_SIZE)
SYNTHETIC_HUNKS = (
    (0x11, bytes.fromhex('deadbeef') * 1, bytes.fromhex('cafebabe')),
    (0x1200, b'\x90\x74', b'\x90\xeb'),
    (0x130000, bytes(8), bytes.fromhex('0102030405060708')),
)
for _off, _old, _new in SYNTHETIC_HUNKS:
    SYNTHETIC_NET[_off:_off + len(_old)] = _old
SYNTHETIC_NET = bytes(SYNTHETIC_NET)
SYNTHETIC_PATCHED = bytes(
    patcher._apply_lab_sfp_net_patch(
        bytearray(SYNTHETIC_NET),
        [(off, old.hex(), new.hex()) for off, old, new in SYNTHETIC_HUNKS]))
assert SYNTHETIC_PATCHED != SYNTHETIC_NET and len(SYNTHETIC_PATCHED) == len(SYNTHETIC_NET)


class LabSfpPatchTests(unittest.TestCase):
    def test_hunks_are_ordered_nonoverlapping_and_length_preserving(self):
        previous_end = -1
        for offset, old_hex, new_hex in patcher._LAB_SFP_NET_PATCH_7244:
            old, new = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
            self.assertEqual(len(old), len(new))
            self.assertGreater(offset, previous_end)
            self.assertLess(offset + len(old), patcher._LAB_SFP_NET_SIZE)
            previous_end = offset + len(old)

    def test_context_mismatch_fails_closed_without_offset_guessing(self):
        data = bytearray(SYNTHETIC_NET)
        data[0x11] ^= 0xFF
        with self.assertRaisesRegex(ValueError, 'context mismatch'):
            patcher._apply_lab_sfp_net_patch(
                data, [(off, old.hex(), new.hex()) for off, old, new in SYNTHETIC_HUNKS])

    def test_version_gates(self):
        self.assertTrue(patcher.lab_sfp_net_supported('7.24.4'))
        self.assertFalse(patcher.lab_sfp_net_supported('7.24.5'))
        self.assertFalse(patcher.lab_sfp_net_supported('7.23.1'))
        self.assertFalse(patcher.lab_sfp_net_supported('7.99.9'))
        self.assertEqual(patcher.x86_installer_qualification('7.24.4'),
                         ('x86-installer-7.24.4',
                          patcher._X86_INSTALLER_SOURCE_SHA256, '7.24.4.final'))
        with self.assertRaisesRegex(ValueError, 'unsupported x86 installer'):
            patcher.x86_installer_qualification('7.24.2')
        self.assertEqual(patcher.chr_runtime_policy_for('7.24.4'), 'chr-x86-7.24.4')
        self.assertEqual(patcher.chr_runtime_policy_for('7.24.5'), 'chr-x86-7.24.5')
        with self.assertRaisesRegex(ValueError, 'unsupported CHR'):
            patcher.chr_runtime_policy_for('7.24.2')

    def test_unqualified_policy_is_rejected_before_any_work(self):
        for bad_policy in (None, 'chr-x86-7.24.4', 'x86-installer-7.24.5'):
            with self.subTest(policy=bad_policy):
                with self.assertRaisesRegex(ValueError, 'qualified pinned x86-installer'):
                    patcher.patch_npk_file(KEYS, b'fake', b'fake', 'unused.npk',
                                           runtime_policy=bad_policy, license_public_key=OLD,
                                           lab_sfp_net=True)


@unittest.skipUnless(os.name == 'posix' and shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'POSIX SquashFS tools unavailable')
class LabSfpRealPolicyTests(unittest.TestCase):
    """Full synthetic pipeline round trip with the lab net swap enabled."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='lab-sfp-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def source(self, *, net=None):
        tree = self.root / 'tree'
        (tree / 'nova/bin').mkdir(parents=True)
        for name in ('loader', 'keyman', 'mode'):
            f = tree / 'nova/bin' / name
            f.write_bytes(elf32(instructions(OLD)) + chr_tests.SIGN)
            f.chmod(0o755)
        net_file = tree / 'nova/bin/net'
        net_file.write_bytes(SYNTHETIC_NET if net is None else net)
        net_file.chmod(0o755)
        (tree / 'unrelated').write_bytes(b'unchanged')
        for path in [tree] + list(tree.rglob('*')):
            os.utime(path, (1700000123, 1700000123), follow_symlinks=False)
        image = self.root / 'source.sfs'
        subprocess.run(['mksquashfs', str(tree), str(image), '-noappend', '-quiet',
                        '-processors', '1', '-mkfs-time', '1700000000', '-all-root'],
                       check=True, capture_output=True)
        p = package(image.read_bytes())
        src = self.root / 'source.npk'
        p.save(src)

        pins = {name: digest((tree / name).read_bytes())
                for name in patcher._X86_INSTALLER_COMPONENT_SHA256}
        synthetic_hunks = [(off, old.hex(), new.hex())
                           for off, old, new in SYNTHETIC_HUNKS]
        for key, value in [
                ('_X86_INSTALLER_COMPONENT_SHA256', pins),
                ('_X86_INSTALLER_SOURCE_SHA256', digest(src.read_bytes())),
                ('_LAB_SFP_NET_SIZE', len(SYNTHETIC_NET)),
                ('_LAB_SFP_NET_SOURCE_SHA256_7244', digest(SYNTHETIC_NET)),
                ('_LAB_SFP_NET_PATCHED_SHA256_7244', digest(SYNTHETIC_PATCHED)),
                ('_LAB_SFP_NET_PATCH_7244', synthetic_hunks)]:
            replacement = mock.patch.object(patcher, key, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        return src

    def apply(self, src, *, lab=True):
        dst = self.root / 'output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            result = patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                            runtime_policy=POLICY, license_public_key=OLD,
                                            lab_sfp_net=lab)
            sign.assert_called_once()
        return dst, result[0]

    def test_net_swap_survives_roundtrip_and_metadata_parity(self):
        src = self.source()
        before = src.read_bytes()
        dst, report = self.apply(src)
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(report['status'], 'coverage-passed')
        self.assertEqual(report['lab_sfp_net']['source_sha256'], digest(SYNTHETIC_NET))
        self.assertEqual(report['lab_sfp_net']['patched_sha256'], digest(SYNTHETIC_PATCHED))
        self.assertEqual(report['lab_sfp_net']['size'], len(SYNTHETIC_NET))
        image = self.root / 'out.sfs'
        image.write_bytes(NovaPackage.load(dst)[NpkPartID.SQUASHFS].data)
        out = self.root / 'out'
        patcher._run_tools(['unsquashfs', '-d', str(out), str(image)], self.root,
                           preserve_modes=True)
        net = (out / 'nova/bin/net').read_bytes()
        self.assertEqual(net, SYNTHETIC_PATCHED)
        stat = (out / 'nova/bin/net').stat()
        self.assertEqual(int(stat.st_mtime), 1700000123)
        self.assertEqual(stat.st_size, len(SYNTHETIC_NET))

    def test_wrong_net_source_is_rejected_without_save(self):
        src = self.source(net=b'not-the-pinned-net' * 3)
        dst = self.root / 'output.npk'
        dst.write_bytes(b'keep existing')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, 'pinned pristine nova/bin/net'):
                patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                       runtime_policy=POLICY, license_public_key=OLD,
                                       lab_sfp_net=True)
            sign.assert_not_called()
        self.assertEqual(dst.read_bytes(), b'keep existing')

    def test_disabled_flag_leaves_net_untouched(self):
        src = self.source()
        dst, report = self.apply(src, lab=False)
        self.assertNotIn('lab_sfp_net', report)
        image = self.root / 'out.sfs'
        image.write_bytes(NovaPackage.load(dst)[NpkPartID.SQUASHFS].data)
        out = self.root / 'out'
        patcher._run_tools(['unsquashfs', '-d', str(out), str(image)], self.root,
                           preserve_modes=True)
        self.assertEqual((out / 'nova/bin/net').read_bytes(), SYNTHETIC_NET)


class OptionalCachedSourceLabSfpTests(unittest.TestCase):
    """Read-only: apply the REAL pinned hunks to the REAL pristine vendor net."""

    def test_real_vendor_net_maps_to_released_lab_net_digest(self):
        source = Path(os.environ.get(
            'MIKPATCH_X86_INSTALLER_SOURCE_NPK',
            '/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/vendor.npk'))
        if not source.is_file():
            self.skipTest('qualified cached source unavailable; no vendor fixture committed')
        if os.name != 'posix' or not shutil.which('unsquashfs'):
            self.skipTest('POSIX unsquashfs unavailable')
        p = NovaPackage.load(source)
        image = self.root_dir() / 'source.sfs'
        image.write_bytes(patcher._part(p, NpkPartID.SQUASHFS).data)
        out = patcher._run_tools(
            ['unsquashfs', '-f', '-d', str(self.root_dir() / 'tree'), str(image),
             'nova/bin/net'], self.root_dir())
        net = (self.root_dir() / 'tree' / 'nova/bin/net').read_bytes()
        self.assertEqual(len(net), patcher._LAB_SFP_NET_SIZE)
        self.assertEqual(digest(net), patcher._LAB_SFP_NET_SOURCE_SHA256_7244)
        patched = bytes(patcher._apply_lab_sfp_net_patch(bytearray(net),
                                                        patcher._LAB_SFP_NET_PATCH_7244))
        self.assertEqual(digest(patched), patcher._LAB_SFP_NET_PATCHED_SHA256_7244)

    @classmethod
    def root_dir(cls):
        if not hasattr(cls, '_root'):
            cls._root = tempfile.TemporaryDirectory(prefix='lab-sfp-cache-')
            import atexit
            atexit.register(cls._root.cleanup)
        return Path(cls._root.name)


if __name__ == '__main__':
    unittest.main()
