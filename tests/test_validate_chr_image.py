import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import struct
import unittest
import zipfile

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
        self.image = b'KDMV' + b'\0' * 1024
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


if __name__ == '__main__':
    unittest.main()
