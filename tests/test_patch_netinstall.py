"""Synthetic NetInstall failure tests; no firmware, configured keys or signing."""
import contextlib
import io
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import patch


KEYS = {b'synthetic-old': b'synthetic-new'}
SENTINEL = b'existing output must survive'


def bootloaders():
    return [(b'MZ' if i % 2 == 0 else b'\x7fELF') + bytes([65 + i]) * (14 if i % 2 == 0 else 12)
            for i in range(10)]


def linux_fixture(blobs):
    """Only the little-endian ELF section/table fields NetInstall reads."""
    data = bytearray(2048)
    data[:7] = b'\x7fELF\x01\x01\x01'
    struct.pack_into('<I', data, 0x20, 64)
    struct.pack_into('<HHH', data, 0x2e, 40, 3, 2)
    struct.pack_into('<10I', data, 104, 1, 1, 6, 0x10000, 512, 1536, 0, 0, 4, 0)
    struct.pack_into('<10I', data, 144, 7, 3, 0, 0, 192, 17, 0, 0, 1, 0)
    data[192:209] = b'\0.text\0.shstrtab\0\0'
    locations = []
    ids = (131, 138, 129, 130, 135, 137, 139, 140, 136, 143)
    for i, (identifier, blob) in enumerate(zip(ids, blobs)):
        name_offset, blob_offset = 512 + 16 * i, 768 + 64 * i
        name = ('boot' + str(i)).encode() + b'\0'
        data[name_offset:name_offset + len(name)] = name
        data[blob_offset:blob_offset + len(blob)] = blob
        struct.pack_into('<IIII', data, 256 + i * 16, identifier,
                         0x10000 + name_offset - 512,
                         0x10000 + blob_offset - 512, len(blob))
        locations.append((blob_offset, len(blob)))
    return bytes(data), locations


def pe_fixture(blobs):
    pe = mock.MagicMock()
    pe.__enter__.return_value = pe
    resources, payloads = [], {}
    for i, blob in enumerate(blobs):
        rva = 256 + 64 * i
        payload = struct.pack('<I', len(blob)) + blob + b'\0' * 8
        payloads[rva] = payload
        leaf = SimpleNamespace(data=SimpleNamespace(struct=SimpleNamespace(
            OffsetToData=rva, Size=len(payload))))
        resources.append(SimpleNamespace(id=(129, 130, 131, 135, 136, 137, 138, 139, 143)[i],
                                         directory=SimpleNamespace(entries=[leaf])))
    pe.DIRECTORY_ENTRY_RESOURCE.entries = [SimpleNamespace(
        id=10, directory=SimpleNamespace(entries=resources))]
    pe.get_data.side_effect = lambda rva, size: payloads[rva][:size]
    module = SimpleNamespace(PE=mock.Mock(return_value=pe), RESOURCE_TYPE={'RT_RCDATA': 10})
    return module, pe, payloads


class NetInstallSafetyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='netinstall-safety-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.quiet = contextlib.redirect_stdout(io.StringIO())
        self.quiet.__enter__()
        self.addCleanup(self.quiet.__exit__, None, None, None)

    def run_failure(self, branch, failure, inner_format='elf'):
        # One bootloader succeeds before the failing one. In-memory partial
        # edits are allowed; neither input nor any output may be written.
        for destination_kind in ('existing', 'new', 'in-place'):
            with self.subTest(branch=branch, failure=failure, inner=inner_format,
                              destination=destination_kind):
                blobs = bootloaders()
                blobs[1] = (b'MZ' + b'Z' * 14 if inner_format == 'pe' else blobs[1])
                if failure == 'unknown':
                    blobs[1] = b'????' + b'Z' * 12
                module, pe, payloads = pe_fixture(blobs[:2])
                original = b'MZsynthetic outer container' if branch == 'pe' else linux_fixture(blobs)[0]
                source = self.root / 'input.bin'
                source.write_bytes(original)
                destination = self.root / 'output.bin'
                if destination.exists():
                    destination.unlink()
                if destination_kind == 'existing':
                    destination.write_bytes(SENTINEL)
                elif destination_kind == 'in-place':
                    destination = None

                def transform(data, mapping):
                    self.assertEqual(mapping, KEYS)
                    if data == blobs[1]:
                        if failure == 'error':
                            raise RuntimeError('synthetic patch failure')
                        if failure == 'oversized':
                            return data + b'!'
                    return data[:-1] + b'!'

                writes = []
                real_open = open

                def tracked_open(path, mode='r', *args, **kwargs):
                    if any(flag in mode for flag in 'wax+'):
                        writes.append((path, mode))
                    return real_open(path, mode, *args, **kwargs)

                expected = 'exceeds' if failure == 'oversized' else 'patch failed'
                with mock.patch.dict('sys.modules', {'pefile': module}), \
                        mock.patch.object(patch, 'patch_pe', side_effect=transform) as patch_pe, \
                        mock.patch.object(patch, 'patch_elf', side_effect=transform) as patch_elf, \
                        mock.patch('builtins.open', side_effect=tracked_open):
                    with self.assertRaisesRegex(ValueError, expected) as caught:
                        patch.patch_netinstall(KEYS, source, destination)
                if failure == 'error':
                    self.assertIsInstance(caught.exception.__cause__, RuntimeError)
                self.assertEqual(patch_pe.call_count + patch_elf.call_count,
                                 1 if failure == 'unknown' else 2)
                self.assertEqual(writes, [])
                pe.write.assert_not_called()
                if branch == 'pe':
                    pe.set_bytes_at_rva.assert_called_once()
                self.assertEqual(source.read_bytes(), original)
                if destination_kind == 'existing':
                    self.assertEqual(destination.read_bytes(), SENTINEL)
                elif destination_kind == 'new':
                    self.assertFalse(destination.exists())

    def test_pe_inner_patch_errors_abort_without_writes(self):
        for inner in ('pe', 'elf'):
            self.run_failure('pe', 'error', inner)

    def test_linux_inner_patch_errors_abort_without_writes(self):
        for inner in ('pe', 'elf'):
            self.run_failure('linux', 'error', inner)

    def test_pe_unknown_bootloader_aborts_without_writes(self):
        self.run_failure('pe', 'unknown')

    def test_linux_unknown_bootloader_aborts_without_writes(self):
        self.run_failure('linux', 'unknown')

    def test_pe_oversized_patch_aborts_without_writes(self):
        for inner in ('pe', 'elf'):
            self.run_failure('pe', 'oversized', inner)

    def test_linux_oversized_patch_aborts_without_writes(self):
        for inner in ('pe', 'elf'):
            self.run_failure('linux', 'oversized', inner)

    def test_unknown_outer_format_rejected_without_writes(self):
        for original in (b'', b'unknown synthetic container'):
            for kind in ('existing', 'new', 'in-place'):
                with self.subTest(size=len(original), destination=kind):
                    source = self.root / 'input.bin'
                    source.write_bytes(original)
                    destination = self.root / (kind + '.bin')
                    if kind == 'existing':
                        destination.write_bytes(SENTINEL)
                    elif kind == 'in-place':
                        destination = None
                    with self.assertRaisesRegex(ValueError, 'unknown NetInstall format'):
                        patch.patch_netinstall(KEYS, source, destination)
                    self.assertEqual(source.read_bytes(), original)
                    if kind == 'existing':
                        self.assertEqual(destination.read_bytes(), SENTINEL)
                    elif kind == 'new':
                        self.assertFalse(destination.exists())

    def test_pe_rejects_declared_blob_larger_than_resource(self):
        blobs = bootloaders()[:2]
        module, pe, payloads = pe_fixture(blobs)
        payload = payloads[320]
        payloads[320] = struct.pack('<I', len(payload)) + payload[4:]
        source = self.root / 'input.exe'
        source.write_bytes(b'MZsynthetic container')
        destination = self.root / 'output.exe'
        destination.write_bytes(SENTINEL)
        with mock.patch.dict('sys.modules', {'pefile': module}), \
                mock.patch.object(patch, 'patch_pe', side_effect=lambda data, _: data):
            with self.assertRaisesRegex(ValueError, 'exceeds resource size'):
                patch.patch_netinstall(KEYS, source, destination)
        pe.write.assert_not_called()
        self.assertEqual(source.read_bytes(), b'MZsynthetic container')
        self.assertEqual(destination.read_bytes(), SENTINEL)

    def test_pe_success_pads_shorter_blobs_and_writes_once(self):
        blobs = bootloaders()[:2]
        module, pe, payloads = pe_fixture(blobs)
        source = self.root / 'input.exe'
        source.write_bytes(b'MZsynthetic container')
        destination = self.root / 'output.exe'
        with mock.patch.dict('sys.modules', {'pefile': module}), \
                mock.patch.object(patch, 'patch_pe', return_value=b'patched-pe'), \
                mock.patch.object(patch, 'patch_elf', return_value=b'patched-elf'):
            patch.patch_netinstall(KEYS, source, destination)
        pe.write.assert_called_once_with(destination)
        for call, replacement in zip(pe.set_bytes_at_rva.call_args_list,
                                     (b'patched-pe', b'patched-elf')):
            rva, output = call.args
            expected = struct.pack('<I', 16) + replacement.ljust(16, b'\0') + b'\0' * 8
            self.assertEqual(output, expected)
            self.assertEqual(len(output), len(payloads[rva]))
        self.assertEqual(source.read_bytes(), b'MZsynthetic container')

    def test_linux_success_pads_shorter_blobs_preserving_layout(self):
        blobs = bootloaders()
        original, locations = linux_fixture(blobs)
        source = self.root / 'input.elf'
        source.write_bytes(original)
        destination = self.root / 'output.elf'
        destination.write_bytes(SENTINEL)
        with mock.patch.object(patch, 'patch_pe', return_value=b'patched-pe'), \
                mock.patch.object(patch, 'patch_elf', return_value=b'patched-elf'):
            patch.patch_netinstall(KEYS, source, destination)
        expected = bytearray(original)
        for i, (offset, size) in enumerate(locations):
            replacement = b'patched-pe' if i % 2 == 0 else b'patched-elf'
            expected[offset:offset + size] = replacement.ljust(size, b'\0')
        self.assertEqual(destination.read_bytes(), bytes(expected))
        self.assertEqual(source.read_bytes(), original)


if __name__ == '__main__':
    unittest.main()
