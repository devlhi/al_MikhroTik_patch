"""Tests for opt-in terminal ASCII logo resource modification.

Validates exact logo byte transformation, ELF consumer anchor checks,
idempotency, separation from LICENSE coverage, and tree safety.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import patch
import terminal_banner
from unittest import mock
import contextlib
import io
import runpy
import shutil
from npk import NovaPackage, NpkPartItem, NpkPartID, NpkFileContainer, NpkNameInfo


def _make_dummy_consumer(path_anchor=terminal_banner.PATH_ANCHOR, flags=4,
                         magic=b'\x7fELF\x01\x01\x01\x00', machine=3,
                         corrupt_hash=False):
    """Build a minimal valid ELF32/i386 binary with path_anchor in a PT_LOAD segment."""
    # ELF header: 52 bytes
    # Program headers at 52: 1 PT_LOAD segment (32 bytes)
    # Total header size: 84 bytes
    # Align segment file offset to 0x1000 (4096)
    ehsize = 52
    phsize = 32
    phoff = ehsize
    phcount = 1

    seg_offset = 0x1000
    rodata = b'PROLOGUE\0' + path_anchor + b'\0EPILOGUE\0'
    seg_filesz = len(rodata)
    seg_memsz = len(rodata)
    seg_vaddr = 0x8048000 + seg_offset

    # Pack ELF header
    # e_ident: 16 bytes
    # e_type: 2 (ET_EXEC), e_machine: machine, e_version: 1, e_entry: 0x8048000
    # e_phoff: phoff, e_shoff: 0, e_flags: 0, e_ehsize: ehsize, e_phentsize: phsize,
    # e_phnum: phcount, e_shentsize: 40, e_shnum: 0, e_shstrndx: 0
    e_ident = magic.ljust(16, b'\0')
    elf_hdr = struct.pack('<16sHHIIIIIHHHHHH',
                          e_ident, 2, machine, 1, 0x8048000,
                          phoff, 0, 0, ehsize, phsize, phcount, 40, 0, 0)

    # Program header:
    # p_type: 1 (PT_LOAD), p_offset: seg_offset, p_vaddr: seg_vaddr, p_paddr: seg_vaddr,
    # p_filesz: seg_filesz, p_memsz: seg_memsz, p_flags: flags, p_align: 4096
    prog_hdr = struct.pack('<8I', 1, seg_offset, seg_vaddr, seg_vaddr,
                           seg_filesz, seg_memsz, flags, 4096)

    header_block = elf_hdr + prog_hdr
    padding = b'\0' * (seg_offset - len(header_block))
    data = header_block + padding + rodata
    return data


class TerminalBannerUnitTests(unittest.TestCase):
    def test_resource_grows_only_by_exact_caption_length(self):
        self.assertEqual(len(terminal_banner.ORIGINAL), 510)
        self.assertEqual(len(terminal_banner.REPLACEMENT), 527)
        # Offset 443 is the original blank row's newline, not an ELF offset.
        self.assertEqual(terminal_banner.REPLACEMENT,
                         terminal_banner.ORIGINAL[:443] + b'  Ali Media Patch'
                         + terminal_banner.ORIGINAL[443:])

    def test_caption_directly_below_unchanged_original_art_and_footer(self):
        original_rows = terminal_banner.ORIGINAL.split(b'\n')
        rows = terminal_banner.REPLACEMENT.split(b'\n')
        self.assertEqual(len(rows), len(original_rows))
        self.assertEqual(rows[:7], original_rows[:7])  # All six original art rows
        self.assertEqual(rows[0], b'')
        self.assertEqual(rows[7], b'  Ali Media Patch')  # Last row consumer reads
        self.assertEqual(rows[8:], original_rows[8:])  # Footer and final newline
        self.assertEqual(terminal_banner.REPLACEMENT.count(b'Ali Media Patch'), 1)

    def test_consumer_anchor_finds_exact_offset(self):
        dummy = _make_dummy_consumer()
        # Mock the pinned hash for synthetic test
        original_hash = terminal_banner.CONSUMER_SHA256
        dummy_hash = hashlib.sha256(dummy).hexdigest()
        try:
            terminal_banner.CONSUMER_SHA256 = dummy_hash
            offset = terminal_banner._consumer_anchor(dummy)
            self.assertEqual(offset, 0x1000 + len(b'PROLOGUE\0'))
            self.assertEqual(dummy[offset:offset+len(terminal_banner.PATH_ANCHOR)],
                             terminal_banner.PATH_ANCHOR)
        finally:
            terminal_banner.CONSUMER_SHA256 = original_hash

    def test_consumer_anchor_rejects_non_elf(self):
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(b'NOT AN ELF BINARY')
        self.assertIn('ELF32', str(cm.exception))

    def test_consumer_anchor_rejects_wrong_machine(self):
        dummy = _make_dummy_consumer(machine=62)  # x86_64 machine code
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(dummy)
        self.assertIn('ELF schema', str(cm.exception))

    def test_consumer_anchor_rejects_missing_path_anchor(self):
        dummy = _make_dummy_consumer(path_anchor=b'/different/path.txt\0')
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(dummy)
        self.assertIn('missing or ambiguous', str(cm.exception))

    def test_consumer_anchor_rejects_writable_segment(self):
        dummy = _make_dummy_consumer(flags=6)  # PF_R | PF_W
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(dummy)
        self.assertIn('read-only ELF load segment', str(cm.exception))

    def test_consumer_anchor_rejects_executable_segment(self):
        dummy = _make_dummy_consumer(flags=5)  # PF_R | PF_X
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(dummy)
        self.assertIn('read-only ELF load segment', str(cm.exception))

    def test_consumer_anchor_rejects_hash_mismatch(self):
        dummy = _make_dummy_consumer()
        with self.assertRaises(ValueError) as cm:
            terminal_banner._consumer_anchor(dummy)
        self.assertIn('unsupported terminal consumer fingerprint', str(cm.exception))

    def test_patch_terminal_banner_transforms_original(self):
        dummy = _make_dummy_consumer()
        original_hash = terminal_banner.CONSUMER_SHA256
        terminal_banner.CONSUMER_SHA256 = hashlib.sha256(dummy).hexdigest()
        try:
            res, rep = terminal_banner.patch_terminal_banner(
                terminal_banner.ORIGINAL, dummy, policy=terminal_banner.POLICY)
            self.assertEqual(res, terminal_banner.REPLACEMENT)
            self.assertEqual(rep['status'], 'patched')
            self.assertEqual(rep['replacements'], 1)
            self.assertFalse(rep['counted_as_license_coverage'])
            self.assertEqual(rep['size'], 510)
            self.assertEqual(rep['output_size'], 527)
            self.assertEqual(rep['size_delta'], 17)
        finally:
            terminal_banner.CONSUMER_SHA256 = original_hash

    def test_patch_terminal_banner_is_idempotent(self):
        dummy = _make_dummy_consumer()
        original_hash = terminal_banner.CONSUMER_SHA256
        terminal_banner.CONSUMER_SHA256 = hashlib.sha256(dummy).hexdigest()
        try:
            res, rep = terminal_banner.patch_terminal_banner(
                terminal_banner.REPLACEMENT, dummy, policy=terminal_banner.POLICY)
            self.assertEqual(res, terminal_banner.REPLACEMENT)
            self.assertEqual(rep['status'], 'already-patched')
            self.assertEqual(rep['replacements'], 0)
            self.assertEqual(rep['size'], 527)
            self.assertEqual(rep['output_size'], 527)
            self.assertEqual(rep['size_delta'], 0)
        finally:
            terminal_banner.CONSUMER_SHA256 = original_hash

    def test_patch_terminal_banner_rejects_corrupted_logo(self):
        dummy = _make_dummy_consumer()
        original_hash = terminal_banner.CONSUMER_SHA256
        terminal_banner.CONSUMER_SHA256 = hashlib.sha256(dummy).hexdigest()
        try:
            corrupted = terminal_banner.ORIGINAL.replace(b'MMM', b'XXX', 1)
            with self.assertRaises(ValueError) as cm:
                terminal_banner.patch_terminal_banner(corrupted, dummy,
                                                      policy=terminal_banner.POLICY)
            self.assertIn('exact terminal logo schema', str(cm.exception))
        finally:
            terminal_banner.CONSUMER_SHA256 = original_hash

    def test_plan_and_write_terminal_banner_on_disk(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logo_path = root / terminal_banner.TARGET
            login_path = root / terminal_banner.CONSUMER
            logo_path.parent.mkdir(parents=True, exist_ok=True)
            login_path.parent.mkdir(parents=True, exist_ok=True)

            dummy = _make_dummy_consumer()
            original_hash = terminal_banner.CONSUMER_SHA256
            terminal_banner.CONSUMER_SHA256 = hashlib.sha256(dummy).hexdigest()
            try:
                logo_path.write_bytes(terminal_banner.ORIGINAL)
                login_path.write_bytes(dummy)

                plan = terminal_banner.plan_terminal_banner(root, terminal_banner.POLICY)
                rep = terminal_banner.write_terminal_banner(plan)
                self.assertEqual(rep['status'], 'patched')
                self.assertEqual(logo_path.read_bytes(), terminal_banner.REPLACEMENT)

                # Check idempotency on re-run
                plan2 = terminal_banner.plan_terminal_banner(root, terminal_banner.POLICY)
                rep2 = terminal_banner.write_terminal_banner(plan2)
                self.assertEqual(rep2['status'], 'already-patched')
                self.assertEqual(rep2['replacements'], 0)
            finally:
                terminal_banner.CONSUMER_SHA256 = original_hash

    def test_plan_rejects_symlink_components(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logo_target = root / terminal_banner.TARGET
            logo_target.parent.mkdir(parents=True, exist_ok=True)
            logo_target.write_bytes(terminal_banner.ORIGINAL)

            # Create a symlink file
            symlink_logo = root / 'nova/lib/console/sym_logo.txt'
            try:
                symlink_logo.symlink_to(logo_target)
            except OSError:
                self.skipTest("Symlinks not supported in this environment")

            with self.assertRaises(ValueError) as cm:
                terminal_banner._regular(root, 'nova/lib/console/sym_logo.txt')
            self.assertIn('regular unlinked file', str(cm.exception))


class TerminalBannerCliTests(unittest.TestCase):
    def test_cli_terminal_banner_creates_isolated_copy_without_keys(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            logo_path = root / terminal_banner.TARGET
            login_path = root / terminal_banner.CONSUMER
            logo_path.parent.mkdir(parents=True, exist_ok=True)
            login_path.parent.mkdir(parents=True, exist_ok=True)

            dummy = _make_dummy_consumer()
            original_hash = terminal_banner.CONSUMER_SHA256
            terminal_banner.CONSUMER_SHA256 = hashlib.sha256(dummy).hexdigest()
            out_file = root / 'out_logo.txt'
            try:
                logo_path.write_bytes(terminal_banner.ORIGINAL)
                login_path.write_bytes(dummy)

                # Invoke patch.py terminal-banner via CLI without any MIKRO_LICENSE env vars
                cmd = [sys.executable, str(ROOT / 'patch.py'), 'terminal-banner',
                       str(root), '--policy', terminal_banner.POLICY,
                       '-O', str(out_file)]
                stdout = io.StringIO()
                with mock.patch.object(sys, 'argv', cmd[1:]), \
                        mock.patch.dict(os.environ, {}, clear=True), \
                        contextlib.redirect_stdout(stdout), self.assertRaises(SystemExit) as exit_info:
                    runpy.run_path(str(ROOT / 'patch.py'), run_name='__main__')
                self.assertEqual(exit_info.exception.code, 0)
                self.assertTrue(out_file.exists())
                self.assertEqual(logo_path.read_bytes(), terminal_banner.ORIGINAL)
                self.assertEqual(out_file.read_bytes(), terminal_banner.REPLACEMENT)
                with mock.patch.object(sys, 'argv', cmd[1:]), \
                        mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(FileExistsError):
                    runpy.run_path(str(ROOT / 'patch.py'), run_name='__main__')
                data = json.loads(stdout.getvalue())
                self.assertEqual(data['status'], 'patched')
                self.assertEqual(data['replacements'], 1)
                self.assertFalse(data['counted_as_license_coverage'])
            finally:
                terminal_banner.CONSUMER_SHA256 = original_hash


class RealBinaryOfflineInspectionTests(unittest.TestCase):
    def test_real_vendor_extracted_files_match_constants_if_present(self):
        # Look for the actual files in known audit cache or temp scratch
        candidate_paths = [
            Path("/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/vendor-root"),
            Path("/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/production-root"),
        ]
        found_root = None
        for p in candidate_paths:
            if p.exists() and (p / terminal_banner.TARGET).exists():
                found_root = p
                break

        if not found_root:
            self.skipTest("Real vendor extracted tree not accessible directly from this runner")

        real_logo = (found_root / terminal_banner.TARGET).read_bytes()
        real_login = (found_root / terminal_banner.CONSUMER).read_bytes()

        self.assertEqual(hashlib.sha256(real_logo).hexdigest(),
                         hashlib.sha256(terminal_banner.ORIGINAL).hexdigest())
        self.assertEqual(hashlib.sha256(real_login).hexdigest(),
                         terminal_banner.CONSUMER_SHA256)

        # Verify anchor resolves in real binary
        anchor_off = terminal_banner._consumer_anchor(real_login)
        self.assertEqual(anchor_off, 154472)

        # Test full planning on real tree read-only
        plan = terminal_banner.plan_terminal_banner(found_root, terminal_banner.POLICY)
        file, original, replacement, report = plan
        self.assertEqual(original, terminal_banner.ORIGINAL)
        self.assertEqual(replacement, terminal_banner.REPLACEMENT)
        self.assertEqual(report['consumer_anchor_offset'], 154472)
        self.assertFalse(report['counted_as_license_coverage'])


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


class StrictBannerTests(unittest.TestCase):
    def setUp(self):
        self.consumer = _make_dummy_consumer()
        pin = mock.patch.object(terminal_banner, 'CONSUMER_SHA256',
                                hashlib.sha256(self.consumer).hexdigest())
        pin.start()
        self.addCleanup(pin.stop)
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        self.root = Path(td.name) / 'root'
        for relative, data in ((terminal_banner.TARGET, terminal_banner.ORIGINAL),
                               (terminal_banner.CONSUMER, self.consumer)):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.logo = self.root / terminal_banner.TARGET

    def test_only_caption_row_changes_newlines_shift_only_after_insertion(self):
        a, b = terminal_banner.ORIGINAL, terminal_banner.REPLACEMENT
        positions = [i for i, x in enumerate(a) if x == 10]
        self.assertEqual([i for i, x in enumerate(b) if x == 10],
                         [i if i < 443 else i + 17 for i in positions])
        for token in (b'\r', b'\0', b'%'):
            self.assertEqual(a.count(token), 0)
            self.assertEqual(b.count(token), 0)
        self.assertTrue(all(32 <= x < 127 or x == 10 for x in b))
        widths = [len(row) for row in a.splitlines()]
        widths[7] = 17
        self.assertEqual([len(row) for row in b.splitlines()], widths)

    def test_reject_missing_duplicate_partial_unknown_target_and_policy(self):
        for data in (b'', terminal_banner.ORIGINAL * 2,
                     terminal_banner.ORIGINAL[:-1], terminal_banner.ORIGINAL + b'\0',
                     b'prefix' + terminal_banner.ORIGINAL,
                     terminal_banner.REPLACEMENT.replace(b'  Ali Media Patch', b'Ali Media Patch'),
                     terminal_banner.REPLACEMENT.replace(b'MMM', b'AAA', 1),
                     terminal_banner.REPLACEMENT.replace(b'1999-2001', b'1999-2002')):
            with self.subTest(size=len(data)), self.assertRaises(ValueError):
                terminal_banner.patch_terminal_banner(data, self.consumer,
                                                      policy=terminal_banner.POLICY)
        for kwargs in ({'policy': ''}, {'policy': 'unsupported'},
                       {'policy': terminal_banner.POLICY, 'target': 'nova/bin/login'}):
            with self.assertRaises(ValueError):
                terminal_banner.patch_terminal_banner(terminal_banner.ORIGINAL,
                                                      self.consumer, **kwargs)

    def test_reject_duplicate_anchor_and_segment_overlap_truncation(self):
        duplicate = _make_dummy_consumer(path_anchor=terminal_banner.PATH_ANCHOR * 2)
        overlap = bytearray(self.consumer)
        struct.pack_into('<H', overlap, 44, 2)
        overlap[84:116] = overlap[52:84]
        truncated = bytearray(self.consumer)
        struct.pack_into('<I', truncated, 52 + 16, 100000)
        for data in (duplicate, bytes(overlap), bytes(truncated), self.consumer[:70]):
            with self.assertRaises(ValueError):
                terminal_banner._consumer_anchor(data)

    def test_hardlink_missing_ancestor_symlink_and_changed_plan_rejected(self):
        alias = self.root / 'alias'
        os.link(self.logo, alias)
        with self.assertRaises(ValueError):
            terminal_banner.plan_terminal_banner(self.root, terminal_banner.POLICY)
        alias.unlink()
        plan = terminal_banner.plan_terminal_banner(self.root, terminal_banner.POLICY)
        self.logo.write_bytes(b'changed')
        with self.assertRaises(ValueError):
            terminal_banner.write_terminal_banner(plan)
        self.logo.unlink()
        with self.assertRaises(ValueError):
            terminal_banner.plan_terminal_banner(self.root, terminal_banner.POLICY)
        self.logo.write_bytes(terminal_banner.ORIGINAL)
        link = self.root.parent / 'linked-root'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest('directory symlink unavailable')
        with self.assertRaises(ValueError):
            terminal_banner.plan_terminal_banner(link, terminal_banner.POLICY)

    def test_default_unchanged_and_logo_stats_not_mapping_stats(self):
        stats = {}
        self.assertIsNone(patch.patch_squashfs(self.root, {}, stats))
        self.assertEqual(self.logo.read_bytes(), terminal_banner.ORIGINAL)
        before = self.logo.stat()
        result = patch.patch_squashfs(self.root, {}, stats,
                                      terminal_banner=terminal_banner.POLICY)
        self.assertEqual(stats, {})
        self.assertEqual(result['replacements'], 1)
        self.assertEqual(self.logo.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertEqual(self.logo.stat().st_mode, before.st_mode)
        self.assertEqual((self.root / terminal_banner.CONSUMER).read_bytes(), self.consumer)

    def test_npk_scope_rejects_wrong_name_version_arch_duplicate_and_multi(self):
        patch._validate_terminal_banner_package(package(), terminal_banner.POLICY)
        cases = []
        for name, version in (('other', '7.24.4.final'), ('system', '7.24.3.final')):
            p = package()
            p._parts[0].data = NpkNameInfo(name, version)
            cases.append(p)
        p = package()
        p._parts[1].data = b'arm64'
        cases.append(p)
        for part_id in (NpkPartID.NAME_INFO, NpkPartID.FILE_CONTAINER,
                        NpkPartID.SQUASHFS, NpkPartID.SIGNATURE):
            for duplicate in (False, True):
                p = package()
                part = next(x for x in p if x.id == part_id)
                p._parts.append(part) if duplicate else p._parts.remove(part)
                cases.append(p)
        p = package()
        p._packages = [package()]
        cases.append(p)
        for p in cases:
            with mock.patch.object(NovaPackage, 'load', return_value=p), \
                    mock.patch.object(NovaPackage, 'sign') as sign, \
                    mock.patch.object(NovaPackage, 'save') as save:
                with self.assertRaises(ValueError):
                    patch.patch_npk_file({b'old': b'new'}, b'fake', b'fake', 'unused',
                                         terminal_banner=terminal_banner.POLICY)
                sign.assert_not_called()
                save.assert_not_called()

    @unittest.skipUnless(os.name == 'posix' and shutil.which('mksquashfs')
                         and shutil.which('unsquashfs'), 'POSIX SquashFS tools required')
    def test_real_squashfs_npk_roundtrip_and_coverage_failure_no_output(self):
        work = self.root.parent
        (self.root / 'coverage').write_bytes(b'old-pattern')
        source = work / 'source.sfs'
        subprocess.run(['mksquashfs', str(self.root), str(source), '-noappend',
                        '-all-root', '-no-xattrs', '-comp', 'xz', '-b', '256k',
                        '-mkfs-time', '1700000000', '-processors', '1'],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        p = package(source.read_bytes())
        original_sfs = p[NpkPartID.SQUASHFS].data
        output = work / 'out.npk'
        output.write_bytes(b'keep-existing-output')
        with mock.patch.object(NovaPackage, 'load', return_value=p), \
                mock.patch.object(NovaPackage, 'sign') as sign, \
                mock.patch.object(NovaPackage, 'save') as save:
            with self.assertRaisesRegex(ValueError, 'signing blocked'):
                patch.patch_npk_file({b'absent-pattern': b'target-pattern'},
                                     b'fake', b'fake', 'unused', str(output),
                                     terminal_banner=terminal_banner.POLICY)
            sign.assert_not_called()
            save.assert_not_called()
        self.assertEqual(p[NpkPartID.SQUASHFS].data, original_sfs)
        self.assertEqual(output.read_bytes(), b'keep-existing-output')
        report = patch.patch_npk_package(p, {b'old-pattern': b'new-pattern'},
                                         terminal_banner=terminal_banner.POLICY)
        self.assertEqual(report['replacements'][0]['total'], 1)
        self.assertEqual(report['terminal_banner']['replacements'], 1)
        repacked = work / 'out.sfs'
        repacked.write_bytes(p[NpkPartID.SQUASHFS].data)
        extracted = work / 'verified'
        subprocess.run(['unsquashfs', '-d', str(extracted), str(repacked)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, umask=0)
        self.assertEqual((extracted / terminal_banner.TARGET).read_bytes(),
                         terminal_banner.REPLACEMENT)
        self.assertEqual((extracted / terminal_banner.CONSUMER).read_bytes(), self.consumer)
        self.assertEqual((extracted / 'coverage').read_bytes(), b'new-pattern')
        self.assertEqual(report['terminal_banner']['output_size'], 527)
        self.assertEqual(report['terminal_banner']['size_delta'], 17)

        # Repacked metadata may differ ONLY by the exact caption size delta.
        metadata = patch._squashfs_metadata
        for target in ('coverage', terminal_banner.TARGET):
            def tampered_metadata(image, work_dir, target=target):
                inventory = metadata(image, work_dir)
                if Path(image).name == 'repacked.sfs':
                    entry = 'squashfs-root/' + target
                    mode, uid, gid, size, mtime = inventory[entry]
                    inventory[entry] = (mode, uid, gid, str(int(size) + 1), mtime)
                return inventory

            with self.subTest(tampered_size=target):
                candidate = package(source.read_bytes())
                with mock.patch.object(patch, '_squashfs_metadata', side_effect=tampered_metadata), \
                        mock.patch.object(NovaPackage, 'load', return_value=candidate), \
                        mock.patch.object(NovaPackage, 'sign') as sign, \
                        mock.patch.object(NovaPackage, 'save') as save:
                    with self.assertRaisesRegex(ValueError, 'metadata mismatch; signing blocked'):
                        patch.patch_npk_file({b'old-pattern': b'new-pattern'},
                                             b'fake', b'fake', 'unused', str(output),
                                             terminal_banner=terminal_banner.POLICY)
                    sign.assert_not_called()
                    save.assert_not_called()
                self.assertEqual(candidate[NpkPartID.SQUASHFS].data, original_sfs)
                self.assertEqual(output.read_bytes(), b'keep-existing-output')


if __name__ == '__main__':
    unittest.main()
