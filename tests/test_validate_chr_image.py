import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import struct
import unittest
import zipfile
import os
import subprocess
from unittest import mock


def image_bytes(fmt):
    data = bytearray(192 * 1024)
    if fmt == 'img':
        data[510:512] = b'\x55\xaa'
    elif fmt == 'vmdk':
        data[:4] = b'KDMV'
        struct.pack_into('<I', data, 4, 1)
        struct.pack_into('<Q', data, 12, len(data) // 512)
    elif fmt == 'qcow2':
        data[:4] = b'QFI\xfb'
        struct.pack_into('>I', data, 4, 3)
        struct.pack_into('>I', data, 20, 16)
        struct.pack_into('>Q', data, 24, len(data))
    elif fmt == 'vhdx':
        data[:8] = b'vhdxfile'
    elif fmt == 'vdi':
        struct.pack_into('<II', data, 64, 0xbeda107f, 0x10001)
        struct.pack_into('<Q', data, 368, len(data))
    elif fmt == 'vhd':
        footer = bytearray(512)
        footer[:8] = b'conectix'
        struct.pack_into('>I', footer, 12, 0x10000)
        struct.pack_into('>Q', footer, 48, len(data))
        struct.pack_into('>I', footer, 60, 3)
        struct.pack_into('>I', footer, 64, ~sum(footer) & 0xffffffff)
        data[-512:] = footer
    return bytes(data)

spec = importlib.util.spec_from_file_location(
    'validate_chr_image', Path(__file__).resolve().parents[1] / 'scripts/validate_chr_image.py')
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class ChrImageValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = 'chr-7.24.4-patched.vmdk.zip'
        self.archive = self.root / ('ali-patch-code-x86-' + self.source)
        self.manifest = self.root / 'manifest.json'
        self.checksums = self.root / 'SHA256SUMS'
        self.image = image_bytes('vmdk')
        self.write_zip([(self.source[:-4], self.image)])

    def write_zip(self, members):
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_STORED) as bundle:
            for name, data in members:
                bundle.writestr(name, data)
        self.refresh()

    def refresh(self):
        self.digest = hashlib.sha256(self.archive.read_bytes()).hexdigest()
        self.entry = {'filename': self.archive.name, 'source': self.source,
                      'size': self.archive.stat().st_size, 'sha256': self.digest}
        self.manifest.write_text(json.dumps({'architecture': 'x86', 'assets': [self.entry]}))
        self.checksums.write_text(self.digest + '  ' + self.archive.name + '\n')

    def validate(self):
        return validator.validate(self.archive, self.manifest, self.checksums)

    def test_valid_archive_is_integrity_only_not_runtime(self):
        report = self.validate()
        self.assertEqual(report['image_sha256'], hashlib.sha256(self.image).hexdigest())
        self.assertTrue(report['zip_crc_verified'])
        self.assertFalse(report['boot_tested'])
        self.assertFalse(report['activation_tested'])

    def test_merged_manifest_supported(self):
        self.manifest.write_text(json.dumps({'architectures': [{'assets': [self.entry]}]}))
        self.assertEqual(self.validate()['archive_sha256'], self.digest)

    def test_changed_archive_rejected(self):
        with self.archive.open('ab') as handle:
            handle.write(b'altered')
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_duplicate_and_mismatched_checksums_rejected(self):
        for text in ('', self.checksums.read_text() * 2,
                     '0' * 64 + '  ' + self.archive.name + '\n'):
            with self.subTest(text=text[:4]):
                self.checksums.write_text(text)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_extra_traversal_or_wrong_member_rejected(self):
        for members in ([('../image.vmdk', self.image)],
                        [(self.source[:-4], self.image), ('extra', b'x')],
                        [('wrong.vmdk', self.image)]):
            with self.subTest(names=[name for name, _ in members]):
                self.write_zip(members)
                with self.assertRaises(ValueError):
                    self.validate()

    def test_empty_or_invalid_vmdk_rejected(self):
        for data in (b'', b'not-vmdk'):
            with self.subTest(data=data):
                self.write_zip([(self.source[:-4], data)])
                with self.assertRaises(ValueError):
                    self.validate()

    def test_duplicate_manifest_entry_rejected(self):
        self.manifest.write_text(json.dumps({'assets': [self.entry, self.entry]}))
        with self.assertRaises(ValueError):
            self.validate()

    def test_symlink_member_rejected(self):
        entry = zipfile.ZipInfo(self.source[:-4])
        entry.create_system = 3
        entry.external_attr = 0o120777 << 16
        self.write_zip([(entry, self.image)])
        with self.assertRaises(ValueError):
            self.validate()

    def test_nonregular_unix_member_rejected(self):
        for mode in (0o010644, 0o020644, 0o060644):
            with self.subTest(mode=mode):
                entry = zipfile.ZipInfo(self.source[:-4])
                entry.create_system = 3
                entry.external_attr = mode << 16
                self.write_zip([(entry, self.image)])
                with self.assertRaises(ValueError):
                    self.validate()

    def test_declared_uncompressed_size_must_match_observed_bytes(self):
        with zipfile.ZipFile(self.archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(self.source[:-4], self.image)
        data = bytearray(self.archive.read_bytes())
        central = data.index(b'PK\x01\x02')
        struct.pack_into('<I', data, 22, len(self.image) + 100)
        struct.pack_into('<I', data, central + 24, len(self.image) + 100)
        self.archive.write_bytes(data)
        self.refresh()
        with self.assertRaisesRegex(ValueError, 'decoded image size'):
            self.validate()

    def test_crc_error_even_when_outer_metadata_matches(self):
        data = bytearray(self.archive.read_bytes())
        offset = data.index(self.image)
        data[offset + 8] ^= 1
        self.archive.write_bytes(data)
        self.refresh()
        with self.assertRaises(zipfile.BadZipFile):
            self.validate()


class AllChrImagesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'manifest.json'
        self.checksums = self.root / 'SHA256SUMS'
        self.entries = []
        for fmt, source in zip(validator.IMAGE_FORMATS,
                               validator.expected_sources('7.24.4', 'x86', 'chr-x86')):
            archive = self.root / validator.branded_filename('x86', source)
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr(source[:-4], image_bytes(fmt))
            self.entries.append({'source': source, 'filename': archive.name,
                                 'size': archive.stat().st_size,
                                 'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()})
        self.refresh()

    def refresh(self):
        self.manifest.write_text(json.dumps({'assets': self.entries}))
        self.checksums.write_text(''.join(e['sha256'] + '  ' + e['filename'] + '\n'
                                       for e in self.entries))

    def validate(self, **kwargs):
        return validator.validate_all(self.root, '7.24.4', self.manifest, self.checksums, **kwargs)

    def test_all_six_inventory_headers_hashes_and_crc_without_qemu(self):
        with mock.patch.object(validator.subprocess, 'run') as run:
            report = self.validate()
        run.assert_not_called()
        self.assertFalse(report['qemu_validated'])
        self.assertFalse(report['boot_tested'])
        self.assertFalse(report['activation_tested'])
        self.assertEqual([e['format'] for e in report['assets']], list(validator.IMAGE_FORMATS))
        for entry in report['assets']:
            self.assertTrue(entry['zip_crc_verified'])
            self.assertTrue(entry['header_checked'])
            self.assertEqual(entry['image_sha256'], hashlib.sha256(image_bytes(entry['format'])).hexdigest())

    def test_each_missing_format_rejected(self):
        for entry in self.entries:
            archive = self.root / entry['filename']
            temporary = archive.with_suffix('.hold')
            archive.rename(temporary)
            try:
                with self.subTest(source=entry['source']), self.assertRaises(ValueError):
                    self.validate()
            finally:
                temporary.rename(archive)

    def test_wrong_inventory_source_rejected(self):
        self.entries[0]['source'] = 'chr-7.24.4-arm64-patched.img.zip'
        self.refresh()
        with self.assertRaises(ValueError):
            self.validate()

    def test_every_format_header_rejects_corruption(self):
        for fmt in validator.IMAGE_FORMATS:
            data = image_bytes(fmt)
            with self.subTest(fmt=fmt):
                validator._validate_header(fmt, data[:512], data[-512:], len(data))
                with self.assertRaises(ValueError):
                    validator._validate_header(fmt, b'\0' * 512, b'\0' * 512, len(data))
                with self.assertRaises(ValueError):
                    validator._validate_header(fmt, data[:4], data[-4:], 4)

    def fake_qemu(self, binary, args):
        if args[0] == 'info':
            fmt = args[args.index('-f') + 1]
            info = {'format': fmt, 'filename': args[-1], 'virtual-size': 192 * 1024}
            if fmt == 'qcow2':
                info['format-specific'] = {'type': fmt, 'data': {}}
            if fmt == 'vmdk':
                info['format-specific'] = {'type': fmt, 'data': {
                    'create-type': 'monolithicSparse', 'parent-cid': 0xffffffff,
                    'extents': [{'filename': args[-1], 'virtual-size': 192 * 1024}]}}
            return json.dumps(info)
        return '{}' if args[0] == 'check' else ''

    def test_opt_in_qemu_info_check_compare_and_cleanup(self):
        with mock.patch.object(validator, '_qemu', side_effect=self.fake_qemu) as run:
            report = self.validate(qemu_img='test-qemu')
        calls = [c.args[1] for c in run.call_args_list]
        self.assertEqual(sum(c[0] == 'info' for c in calls), 6)
        self.assertEqual(sum(c[0] == 'check' for c in calls), 4)
        self.assertEqual(sum(c[0] == 'compare' for c in calls), 5)
        self.assertEqual([c[c.index('-f') + 1] for c in calls if c[0] == 'check'],
                         ['qcow2', 'vmdk', 'vhdx', 'vdi'])
        for call in calls:
            self.assertFalse(Path(call[-1]).exists())
            self.assertNotIn('-r', call)
        self.assertTrue(report['qemu_validated'])
        self.assertFalse(report['boot_tested'])

    def test_opt_in_missing_qemu_and_nonzero_or_timeout_fail_closed(self):
        for failure in (FileNotFoundError(), ValueError('failure'), subprocess.TimeoutExpired('qemu-img', 1)):
            with self.subTest(error=type(failure).__name__):
                with mock.patch.object(validator, '_qemu', side_effect=failure):
                    with self.assertRaises(type(failure)):
                        self.validate(qemu_img='missing')

    def test_qemu_rejects_backing_wrong_size_format_and_defects(self):
        bad_info = [dict(format='raw', **{'virtual-size': 0}),
                    dict(format='wrong', **{'virtual-size': 192 * 1024}),
                    dict(format='raw', **{'virtual-size': 192 * 1024, 'backing-filename': 'external'}),
                    dict(format='qcow2', **{'virtual-size': 192 * 1024,
                                            'format-specific': {'type': 'qcow2', 'data': {'data-file': '/tmp/ext'}}}),
                    dict(format='qcow2', **{'virtual-size': 192 * 1024,
                                            'format-specific': {'type': 'qcow2', 'data': {'data-file-raw': True}}}),
                    dict(format='vmdk', **{'virtual-size': 192 * 1024,
                                           'format-specific': {'type': 'vmdk', 'data': {
                                               'create-type': 'twoGbMaxExtentSparse',
                                               'extents': [{'filename': 'split.vmdk', 'virtual-size': 192 * 1024}]}}}),
                    dict(format='vmdk', **{'virtual-size': 192 * 1024,
                                           'format-specific': {'type': 'vmdk', 'data': {
                                               'create-type': 'monolithicSparse', 'parent-cid': 0,
                                               'extents': [{'filename': 'ext.vmdk', 'virtual-size': 192 * 1024}]}}})]
        for info in bad_info:
            with self.subTest(info=info), mock.patch.object(validator, '_qemu', return_value=json.dumps(info)) as run:
                with self.assertRaises(ValueError):
                    self.validate(qemu_img='test-qemu')
                calls = [c.args[1][0] for c in run.call_args_list]
                self.assertNotIn('check', calls)
                self.assertNotIn('compare', calls)
        for key in ('corruptions', 'leaks', 'check-errors'):
            def damaged(binary, args):
                return json.dumps({key: 1}) if args[0] == 'check' else self.fake_qemu(binary, args)
            with self.subTest(key=key), mock.patch.object(validator, '_qemu', side_effect=damaged):
                with self.assertRaises(ValueError):
                    self.validate(qemu_img='test-qemu')

    def test_external_references_rejected_at_target_before_any_guest_operations(self):
        for fmt in ('qcow2', 'vmdk', 'vhdx', 'vdi', 'vpc'):
            def external(binary, args):
                info = json.loads(self.fake_qemu(binary, args))
                if info['format'] == fmt:
                    if fmt == 'qcow2':
                        info['format-specific']['data']['data-file'] = '/external'
                    elif fmt == 'vmdk':
                        info['format-specific']['data']['extents'][0]['filename'] = '/external'
                    else:
                        info['children'] = [{'name': 'file', 'info': {
                            'format': 'file', 'filename': '/external', 'children': []}}]
                return json.dumps(info)
            with self.subTest(fmt=fmt), mock.patch.object(validator, '_qemu', side_effect=external) as run:
                with self.assertRaisesRegex(ValueError, 'standalone container'):
                    self.validate(qemu_img='test-qemu')
                self.assertTrue(all(c.args[1][0] == 'info' for c in run.call_args_list))
                self.assertEqual(run.call_args_list[-1].args[1][-2], fmt)

    def test_standalone_schema_rejects_external_extents_and_malformed_metadata(self):
        image = self.root / 'image.vmdk'
        for fmt in ('qcow2', 'vmdk'):
            valid = json.loads(self.fake_qemu('test', ['info', '-f', fmt, str(image)]))
            validator._validate_standalone(valid, image, fmt)
            bad = []
            for specific in (None, [], {}, {'type': 'wrong', 'data': {}}, {'type': fmt, 'data': []}):
                bad.append(dict(valid, **{'format-specific': specific}))
            for child in (None, {}, [], [{'name': 'data-file', 'info': {}}],
                          [{'name': 'file', 'info': {'format': 'file', 'filename': str(self.root / 'external')}}]):
                bad.append(dict(valid, children=child))
            for key in ('data-file', 'data-file-raw'):
                edited = json.loads(json.dumps(valid))
                edited['format-specific']['data'][key] = '/external'
                bad.append(edited)
            if fmt == 'vmdk':
                for extent in (None, {}, [], [{'filename': '/external', 'virtual-size': 192 * 1024}],
                               valid['format-specific']['data']['extents'] * 2):
                    edited = json.loads(json.dumps(valid))
                    edited['format-specific']['data']['extents'] = extent
                    bad.append(edited)
            for info in bad:
                with self.subTest(fmt=fmt, info=info), self.assertRaises(ValueError):
                    validator._validate_standalone(info, image, fmt)

    @unittest.skipUnless(os.environ.get('CHR_TEST_QEMU_IMG'), 'opt-in real qemu-img not configured')
    def test_real_qcow2_external_data_rejected_before_check_or_compare(self):
        binary = os.environ['CHR_TEST_QEMU_IMG']
        raw = self.root / 'reference.img'
        raw.write_bytes(image_bytes('img'))
        external = self.root / 'external.raw'
        image = self.root / self.entries[1]['source'][:-4]
        validator._qemu(binary, ['convert', '-f', 'raw', '-O', 'qcow2', '-o',
                                f'data_file={external},data_file_raw=on', str(raw), str(image)])
        self.assertTrue(external.is_file())
        info = json.loads(validator._qemu(binary, ['info', '--output=json', '-f', 'qcow2', str(image)]))
        self.assertEqual(info['format-specific']['data']['data-file'], str(external))
        entry = self.entries[1]
        archive = self.root / entry['filename']
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(image, image.name)
        entry.update(size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.refresh()
        with mock.patch.object(validator, '_qemu', wraps=validator._qemu) as run:
            with self.assertRaisesRegex(ValueError, 'standalone container'):
                self.validate(qemu_img=binary)
        self.assertEqual([c.args[1][0] for c in run.call_args_list], ['info', 'info'])

    def test_subprocess_failure_output_not_exposed(self):
        with mock.patch.object(validator.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, 'sensitive', 'sensitive')):
            with self.assertRaisesRegex(ValueError, '^qemu-img validation failed$'):
                validator._qemu('test-qemu', ['info'])

    @unittest.skipUnless(os.environ.get('CHR_TEST_QEMU_IMG'), 'opt-in real qemu-img not configured')
    def test_real_qemu_six_conversions_and_guest_mismatch(self):
        binary = os.environ['CHR_TEST_QEMU_IMG']
        raw = self.root / 'reference.img'
        raw.write_bytes(image_bytes('img'))
        for entry, fmt in zip(self.entries, validator.IMAGE_FORMATS):
            image = self.root / entry['source'][:-4]
            if fmt == 'img':
                image.write_bytes(raw.read_bytes())
            else:
                validator._qemu(binary, ['convert', '-f', 'raw', '-O', validator.QEMU_FORMATS[fmt], str(raw), str(image)])
            archive = self.root / entry['filename']
            with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.write(image, image.name)
            entry.update(size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.refresh()
        self.assertTrue(self.validate(qemu_img=binary)['qemu_validated'])
        # Change a guest byte while retaining a valid image, ZIP and metadata.
        entry = self.entries[0]
        changed = bytearray(raw.read_bytes())
        changed[4096] = 1
        archive = self.root / entry['filename']
        with zipfile.ZipFile(archive, 'w') as bundle:
            bundle.writestr(entry['source'][:-4], changed)
        entry.update(size=archive.stat().st_size, sha256=hashlib.sha256(archive.read_bytes()).hexdigest())
        self.refresh()
        with self.assertRaises(ValueError):
            self.validate(qemu_img=binary)


if __name__ == '__main__':
    unittest.main()
