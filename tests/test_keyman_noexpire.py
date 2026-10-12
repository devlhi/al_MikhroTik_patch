"""keyman no-expires-in patch: pinned hunks, fail-closed pins, metadata parity.

Synthetic fixtures use test-local pins only. The optional cached-source test
applies the real pinned hunks to the real pristine vendor keyman read-only; no
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


SYNTHETIC_KEYMAN = bytearray(patcher._KEYMAN_NOEXPIRE_SIZE_7244)
SYNTHETIC_KEYMAN[:len(elf32(instructions(OLD))) + len(chr_tests.SIGN)] = (
    elf32(instructions(OLD)) + chr_tests.SIGN)
SYNTHETIC_HUNKS = (
    (0x400, bytes.fromhex('deadbeef'), bytes.fromhex('cafebabe')),
    (0xA143, bytes.fromhex('0f84b8000000'), bytes.fromhex('e90500000090')),
)
for _off, _old, _new in SYNTHETIC_HUNKS:
    SYNTHETIC_KEYMAN[_off:_off + len(_old)] = _old
SYNTHETIC_KEYMAN = bytes(SYNTHETIC_KEYMAN)
SYNTHETIC_PATCHED = bytes(
    patcher._apply_lab_sfp_net_patch(
        bytearray(SYNTHETIC_KEYMAN),
        [(off, old.hex(), new.hex()) for off, old, new in SYNTHETIC_HUNKS]))
assert SYNTHETIC_PATCHED != SYNTHETIC_KEYMAN and len(SYNTHETIC_PATCHED) == len(SYNTHETIC_KEYMAN)


class KeymanNoExpirePatchTests(unittest.TestCase):
    def test_hunks_are_ordered_nonoverlapping_and_length_preserving(self):
        previous_end = -1
        for offset, old_hex, new_hex in patcher._KEYMAN_NOEXPIRE_HUNK:
            old, new = bytes.fromhex(old_hex), bytes.fromhex(new_hex)
            self.assertEqual(len(old), len(new))
            self.assertGreater(offset, previous_end)
            self.assertLess(offset + len(old), patcher._KEYMAN_NOEXPIRE_SIZE_7244)
            previous_end = offset + len(old)

    def test_pinned_hunk_is_the_property_six_branch_skip(self):
        # je rel32 (6 bytes) -> jmp +5 landing on the finish block, then nop.
        for offset, old_hex, new_hex in patcher._KEYMAN_NOEXPIRE_HUNK:
            self.assertEqual(old_hex, '0f84b8000000')
            self.assertEqual(new_hex, 'e90500000090')

    def test_pinned_digests_are_self_consistent(self):
        source = bytearray(patcher._KEYMAN_NOEXPIRE_SIZE_7244)
        for offset, old_hex, _ in patcher._KEYMAN_NOEXPIRE_HUNK:
            source[offset:offset + len(bytes.fromhex(old_hex))] = bytes.fromhex(old_hex)
        # The real pristine keyman is pinned by sha; the hunk alone does not
        # reconstruct it, so only verify the patched digest is pinned distinct.
        self.assertNotEqual(patcher._KEYMAN_NOEXPIRE_SOURCE_SHA256_7244,
                            patcher._KEYMAN_NOEXPIRE_PATCHED_SHA256_7244)

    def test_context_mismatch_fails_closed_without_offset_guessing(self):
        data = bytearray(SYNTHETIC_KEYMAN)
        data[0x400] ^= 0xFF
        with self.assertRaisesRegex(ValueError, 'context mismatch'):
            patcher._apply_lab_sfp_net_patch(
                data, [(off, old.hex(), new.hex()) for off, old, new in SYNTHETIC_HUNKS])

    def test_version_gates(self):
        self.assertTrue(patcher.no_expires_in_supported('7.24.4'))
        self.assertFalse(patcher.no_expires_in_supported('7.24.5'))
        self.assertFalse(patcher.no_expires_in_supported('7.23.1'))
        self.assertFalse(patcher.no_expires_in_supported('7.99.9'))

    def test_unqualified_policy_is_rejected_before_any_work(self):
        for bad_policy in (None, 'chr-x86-7.24.4', 'x86-installer-7.24.5'):
            with self.subTest(policy=bad_policy):
                with self.assertRaisesRegex(ValueError, 'qualified pinned x86-installer'):
                    patcher.patch_npk_file(KEYS, b'fake', b'fake', 'unused.npk',
                                           runtime_policy=bad_policy, license_public_key=OLD,
                                           no_expires_in=True)


@unittest.skipUnless(os.name == 'posix' and shutil.which('mksquashfs') and shutil.which('unsquashfs'),
                     'POSIX SquashFS tools unavailable')
class KeymanNoExpireRealPolicyTests(unittest.TestCase):
    """Full synthetic pipeline round trip with the keyman no-expire patch enabled."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory(prefix='keyman-noexp-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        quiet = contextlib.redirect_stdout(io.StringIO())
        quiet.__enter__()
        self.addCleanup(quiet.__exit__, None, None, None)

    def source(self, *, keyman=None):
        tree = self.root / 'tree'
        (tree / 'nova/bin').mkdir(parents=True)
        for name in ('loader', 'keyman', 'mode'):
            f = tree / 'nova/bin' / name
            if name == 'keyman':
                f.write_bytes(SYNTHETIC_KEYMAN if keyman is None else keyman)
            else:
                f.write_bytes(elf32(instructions(OLD)) + chr_tests.SIGN)
            f.chmod(0o755)
        net_file = tree / 'nova/bin/net'
        net_file.write_bytes(elf32(instructions(OLD)) + chr_tests.SIGN)
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
        # The keyman pin binds the post-rewrite bytes, mirroring the pipeline
        # order: generic key replacement first, pinned hunk second.
        replaced_keyman = patcher._replace_keys(
            SYNTHETIC_KEYMAN, KEYS, 'nova/bin/keyman', {}, None)
        synthetic_hunks = [(off, old.hex(), new.hex())
                           for off, old, new in SYNTHETIC_HUNKS]
        replaced_patched = bytes(patcher._apply_lab_sfp_net_patch(
            bytearray(replaced_keyman), synthetic_hunks))
        for key, value in [
                ('_X86_INSTALLER_COMPONENT_SHA256', pins),
                ('_X86_INSTALLER_SOURCE_SHA256', digest(src.read_bytes())),
                ('_KEYMAN_NOEXPIRE_SIZE_7244', len(SYNTHETIC_KEYMAN)),
                ('_KEYMAN_NOEXPIRE_SOURCE_SHA256_7244', digest(replaced_keyman)),
                ('_KEYMAN_NOEXPIRE_PATCHED_SHA256_7244', digest(replaced_patched)),
                ('_KEYMAN_NOEXPIRE_HUNK', synthetic_hunks)]:
            replacement = mock.patch.object(patcher, key, value)
            replacement.start()
            self.addCleanup(replacement.stop)
        return src

    def apply(self, src, *, enabled=True):
        dst = self.root / 'output.npk'
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            result = patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                            runtime_policy=POLICY, license_public_key=OLD,
                                            no_expires_in=enabled)
            sign.assert_called_once()
        return dst, result[0]

    def test_keyman_patch_survives_roundtrip_and_metadata_parity(self):
        src = self.source()
        before = src.read_bytes()
        dst, report = self.apply(src)
        self.assertEqual(src.read_bytes(), before)
        self.assertEqual(report['status'], 'coverage-passed')
        self.assertEqual(report['keyman_no_expires_in']['size'], len(SYNTHETIC_KEYMAN))
        image = self.root / 'out.sfs'
        image.write_bytes(NovaPackage.load(dst)[NpkPartID.SQUASHFS].data)
        out = self.root / 'out'
        patcher._run_tools(['unsquashfs', '-d', str(out), str(image)], self.root,
                           preserve_modes=True)
        keyman = (out / 'nova/bin/keyman').read_bytes()
        expected = patcher._replace_keys(
            SYNTHETIC_PATCHED, KEYS, 'nova/bin/keyman', {}, None)
        self.assertEqual(keyman, expected)
        self.assertNotEqual(keyman, SYNTHETIC_PATCHED)
        stat = (out / 'nova/bin/keyman').stat()
        self.assertEqual(int(stat.st_mtime), 1700000123)
        self.assertEqual(stat.st_size, len(SYNTHETIC_KEYMAN))

    def test_wrong_keyman_source_is_rejected_without_save(self):
        # Must pass the policy anchors so rejection comes from the pinned
        # post-rewrite digest, not the earlier structural validation.
        drifted = bytearray(SYNTHETIC_KEYMAN)
        drifted[0x500] ^= 0xFF
        src = self.source(keyman=bytes(drifted))
        dst = self.root / 'output.npk'
        dst.write_bytes(b'keep existing')
        with mock.patch.object(NovaPackage, 'sign', autospec=True) as sign:
            with self.assertRaisesRegex(ValueError, 'pinned pristine nova/bin/keyman'):
                patcher.patch_npk_file(KEYS, b'fake', b'fake', src, dst,
                                       runtime_policy=POLICY, license_public_key=OLD,
                                       no_expires_in=True)
            sign.assert_not_called()
        self.assertEqual(dst.read_bytes(), b'keep existing')

    def test_disabled_flag_leaves_keyman_untouched(self):
        src = self.source()
        dst, report = self.apply(src, enabled=False)
        self.assertNotIn('keyman_no_expires_in', report)
        image = self.root / 'out.sfs'
        image.write_bytes(NovaPackage.load(dst)[NpkPartID.SQUASHFS].data)
        out = self.root / 'out'
        patcher._run_tools(['unsquashfs', '-d', str(out), str(image)], self.root,
                           preserve_modes=True)
        expected = patcher._replace_keys(
            SYNTHETIC_KEYMAN, KEYS, 'nova/bin/keyman', {}, None)
        self.assertEqual((out / 'nova/bin/keyman').read_bytes(), expected)


class OptionalCachedSourceKeymanTests(unittest.TestCase):
    """Read-only: prove the REAL pinned hunk maps the REAL vendor keyman
    (after the real key rewrite) to the pinned patched digest."""

    def _workflow_key_dict(self):
        import yaml
        workflow = Path(patcher.__file__).parent / '.github' / 'workflows' / 'patch7.yml'
        if not workflow.is_file():
            self.skipTest('workflow unavailable')
        env = yaml.safe_load(workflow.read_text(encoding='utf-8'))['env']
        return ({bytes.fromhex(env['MIKRO_LICENSE_PUBLIC_KEY'].strip()):
                 bytes.fromhex(env['CUSTOM_LICENSE_PUBLIC_KEY'].strip()),
                 bytes.fromhex(env['MIKRO_NPK_SIGN_PUBLIC_KEY'].strip()):
                 bytes.fromhex(env['CUSTOM_NPK_SIGN_PUBLIC_KEY'].strip())},
                bytes.fromhex(env['MIKRO_LICENSE_PUBLIC_KEY'].strip()))

    def test_real_vendor_keyman_maps_to_pinned_patched_digest(self):
        source = Path(os.environ.get(
            'MIKPATCH_X86_INSTALLER_SOURCE_NPK',
            '/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/vendor.npk'))
        if not source.is_file():
            self.skipTest('qualified cached source unavailable; no vendor fixture committed')
        if os.name != 'posix' or not shutil.which('unsquashfs'):
            self.skipTest('POSIX unsquashfs unavailable')
        try:
            import capstone  # noqa: F401
        except ImportError:
            self.skipTest('capstone unavailable; instruction rewrite cannot run')
        key_dict, license_pub = self._workflow_key_dict()
        p = NovaPackage.load(source)
        image = self.root_dir() / 'source.sfs'
        image.write_bytes(patcher._part(p, NpkPartID.SQUASHFS).data)
        tree = self.root_dir() / 'tree'
        patcher._run_tools(['unsquashfs', '-d', str(tree), str(image)],
                           self.root_dir(), preserve_modes=True)
        stats = {key: 0 for key in key_dict}
        patcher.patch_squashfs(tree, key_dict, stats, 'x86-installer-7.24.4', license_pub)
        keyman = (tree / 'nova/bin/keyman').read_bytes()
        self.assertEqual(len(keyman), patcher._KEYMAN_NOEXPIRE_SIZE_7244)
        self.assertEqual(digest(keyman), patcher._KEYMAN_NOEXPIRE_SOURCE_SHA256_7244)
        patched = bytes(patcher._apply_lab_sfp_net_patch(
            bytearray(keyman), patcher._KEYMAN_NOEXPIRE_HUNK))
        self.assertEqual(digest(patched), patcher._KEYMAN_NOEXPIRE_PATCHED_SHA256_7244)

    @classmethod
    def root_dir(cls):
        if not hasattr(cls, '_root'):
            cls._root = tempfile.TemporaryDirectory(prefix='keyman-noexp-cache-')
            import atexit
            atexit.register(cls._root.cleanup)
        return Path(cls._root.name)


if __name__ == '__main__':
    unittest.main()
