#!/usr/bin/env python3
"""Verify a CHR image ZIP against release metadata; this is not a boot test."""
import argparse
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import struct
import subprocess
import tempfile
import zipfile

try:
    from scripts.release_assets import IMAGE_FORMATS, expected_sources, branded_filename, VALID_VERSION
except ModuleNotFoundError:  # Direct execution from scripts/.
    from release_assets import IMAGE_FORMATS, expected_sources, branded_filename, VALID_VERSION

QEMU_FORMATS = dict(zip(IMAGE_FORMATS, ('raw', 'qcow2', 'vmdk', 'vpc', 'vhdx', 'vdi')))


MAX_IMAGE_BYTES = 16 * 1024 ** 3


def _validate_header(extension, prefix, suffix, size):
    """Cheap format sanity checks, not a substitute for qemu or a boot test."""
    valid = False
    if extension == 'img':
        valid = size >= 512 and size % 512 == 0 and prefix[510:512] == b'\x55\xaa'
    elif extension == 'qcow2' and len(prefix) >= 72:
        valid = (prefix[:4] == b'QFI\xfb'
                 and struct.unpack_from('>I', prefix, 4)[0] in (2, 3)
                 and 9 <= struct.unpack_from('>I', prefix, 20)[0] <= 21
                 and 0 < struct.unpack_from('>Q', prefix, 24)[0] <= MAX_IMAGE_BYTES)
    elif extension == 'vmdk' and len(prefix) >= 512:
        valid = (prefix[:4] == b'KDMV'
                 and struct.unpack_from('<I', prefix, 4)[0] in (1, 2, 3)
                 and 0 < struct.unpack_from('<Q', prefix, 12)[0] <= MAX_IMAGE_BYTES // 512)
    elif extension == 'vhd':
        footer = bytearray(suffix[-512:])
        if len(footer) == 512 and footer[:8] == b'conectix':
            checksum = struct.unpack_from('>I', footer, 64)[0]
            footer[64:68] = b'\0' * 4
            valid = (size % 512 == 0
                     and struct.unpack_from('>I', footer, 12)[0] == 0x10000
                     and struct.unpack_from('>I', footer, 60)[0] in (2, 3)
                     and 0 < struct.unpack_from('>Q', footer, 48)[0] <= MAX_IMAGE_BYTES
                     and checksum == (~sum(footer) & 0xffffffff))
    elif extension == 'vhdx':
        valid = size >= 192 * 1024 and size % 512 == 0 and prefix[:8] == b'vhdxfile'
    elif extension == 'vdi' and len(prefix) >= 400:
        valid = (struct.unpack_from('<I', prefix, 64)[0] == 0xbeda107f
                 and struct.unpack_from('<I', prefix, 68)[0] == 0x10001
                 and 0 < struct.unpack_from('<Q', prefix, 368)[0] <= MAX_IMAGE_BYTES)
    if not valid:
        raise ValueError(f'image does not have a sane {extension} header')


def validate(archive, manifest_path, checksums_path, *, _image_output=None):
    archive = Path(archive)
    for path in (archive, Path(manifest_path), Path(checksums_path)):
        if path.is_symlink() or not path.is_file():
            raise ValueError('inputs must be regular files, not symlinks')
    manifest = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    manifests = manifest.get('architectures', [manifest])
    entries = [entry for item in manifests for entry in item.get('assets', [])
               if entry.get('filename') == archive.name]
    if len(entries) != 1:
        raise ValueError('archive must occur exactly once in manifest')
    entry = entries[0]
    source = entry.get('source', '')
    if not re.fullmatch(r'chr-[0-9]+\.[0-9]+\.[0-9]+(?:-arm64)?-patched\.(img|qcow2|vmdk|vhd|vhdx|vdi)\.zip', source):
        raise ValueError('manifest entry is not a supported CHR image')
    expected = entry.get('sha256', '')
    if not isinstance(expected, str) or not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('manifest SHA-256 is invalid')
    checksum_entries = []
    for line in Path(checksums_path).read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  (.+)', line)
        if not match:
            raise ValueError('checksum list is malformed')
        if match[2] == archive.name:
            checksum_entries.append(match[1])
    if checksum_entries != [expected]:
        raise ValueError('checksum list does not uniquely match manifest')
    digest = hashlib.sha256()
    with archive.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    if type(entry.get('size')) is not int or entry['size'] <= 0:
        raise ValueError('manifest size must be a positive integer')
    if archive.stat().st_size != entry['size'] or digest.hexdigest() != expected:
        raise ValueError('archive bytes do not match release metadata')
    image_name = source[:-4]
    image_digest = hashlib.sha256()
    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) != 1 or members[0].filename != image_name:
            raise ValueError('ZIP must contain exactly the expected image name')
        member = members[0]
        mode = member.external_attr >> 16
        if (member.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
                or member.flag_bits & 1):
            raise ValueError('ZIP image must be an unencrypted regular file')
        if not 0 < member.file_size <= MAX_IMAGE_BYTES:
            raise ValueError('image size is outside validation limits')
        output = Path(_image_output).open('xb') if _image_output is not None else nullcontext(None)
        with output as extracted, bundle.open(member) as image:
            prefix = image.read(512)
            suffix = prefix
            observed_size = len(prefix)
            image_digest.update(prefix)
            if extracted is not None:
                extracted.write(prefix)
            for chunk in iter(lambda: image.read(1024 * 1024), b''):
                observed_size += len(chunk)
                image_digest.update(chunk)
                suffix = (suffix + chunk)[-512:]
                if extracted is not None:
                    extracted.write(chunk)
        if observed_size != member.file_size:
            raise ValueError('decoded image size does not match ZIP metadata')
        extension = image_name.rsplit('.', 1)[1]
        _validate_header(extension, prefix, suffix, observed_size)
    return {'archive': archive.name, 'archive_sha256': expected,
            'image': image_name, 'image_sha256': image_digest.hexdigest(),
            'image_size': member.file_size, 'zip_crc_verified': True,
            'header_checked': True, 'format': extension,
            'boot_tested': False, 'activation_tested': False,
            'scope': 'build-only byte integrity, ZIP structure and format header'}


def _qemu(binary, args):
    result = subprocess.run([str(binary), *args], capture_output=True, text=True,
                            timeout=600, check=False)
    # Never echo tool stderr/stdout on failure (may contain paths or external data).
    if result.returncode != 0:
        raise ValueError('qemu-img validation failed')
    return result.stdout


def _validate_standalone(info, image, qfmt):
    """Reject external storage before any structural check or guest read.

    Older QEMU versions omit children; when present its only permitted child
    is the local container itself. QCOW2/VMDK format metadata is mandatory.
    No external data files, split extents, parents or unknown container shapes.
    """
    def reject():
        raise ValueError('qemu-img standalone container validation failed')

    def same_file(name):
        # Compare names, not samefile(): symlink/hardlink aliases are not allowed.
        return isinstance(name, str) and Path(name).is_absolute() and Path(name) == image

    if not isinstance(info, dict):
        reject()
    if 'filename' in info and not same_file(info['filename']):
        reject()
    if any(key in info for key in ('backing-filename', 'full-backing-filename',
                                   'data-file', 'backing-filename-format')):
        reject()
    specific = info.get('format-specific')
    if qfmt in ('qcow2', 'vmdk') or 'format-specific' in info:
        if (not isinstance(specific, dict) or specific.get('type') != qfmt
                or not isinstance(specific.get('data'), dict)):
            reject()
        data = specific['data']
        if any(key in data for key in ('data-file', 'data-file-raw', 'backing-filename')):
            reject()
        if qfmt == 'vmdk':
            extents = data.get('extents')
            if (data.get('create-type') != 'monolithicSparse'
                    or data.get('parent-cid') != 0xffffffff
                    or not isinstance(extents, list) or len(extents) != 1
                    or not isinstance(extents[0], dict)
                    or not same_file(extents[0].get('filename'))
                    or extents[0].get('virtual-size') != info.get('virtual-size')):
                reject()
        elif 'extents' in data:
            reject()
    if 'children' in info:
        children = info['children']
        if (not isinstance(children, list) or len(children) != 1
                or not isinstance(children[0], dict) or children[0].get('name') != 'file'):
            reject()
        child = children[0].get('info')
        if (not isinstance(child, dict) or child.get('format') != 'file'
                or not same_file(child.get('filename'))
                or child.get('children', []) != []
                or any(key in child for key in ('backing-filename', 'full-backing-filename', 'data-file'))):
            reject()


def _validate_qemu(binary, images, reports):
    raw = images['img']
    raw_size = raw.stat().st_size
    virtual_sizes = {}
    # Preflight every container before check/compare can read guest sectors.
    # qemu-img info itself may open references; this is not a sandbox for info.
    for fmt in IMAGE_FORMATS:
        image = images[fmt]
        qfmt = QEMU_FORMATS[fmt]
        info = json.loads(_qemu(binary, ['info', '--output=json', '-f', qfmt, str(image)]))
        virtual_size = info.get('virtual-size')
        if (info.get('format') != qfmt or type(virtual_size) is not int
                or not raw_size <= virtual_size <= MAX_IMAGE_BYTES
                or virtual_size % 512 or info.get('encrypted')):
            raise ValueError('qemu-img format, size or encryption validation failed')
        _validate_standalone(info, image, qfmt)
        if fmt in ('img', 'qcow2', 'vmdk', 'vhdx') and virtual_size != raw_size:
            raise ValueError('qemu-img guest size differs from raw image')
        virtual_sizes[fmt] = virtual_size
    for fmt in IMAGE_FORMATS:
        image = images[fmt]
        qfmt = QEMU_FORMATS[fmt]
        virtual_size = virtual_sizes[fmt]
        check_supported = fmt in ('qcow2', 'vmdk', 'vhdx', 'vdi')
        if check_supported:
            check = json.loads(_qemu(binary, ['check', '--output=json', '-f', qfmt, str(image)]))
            if any(check.get(key, 0) != 0 for key in ('check-errors', 'corruptions', 'leaks')):
                raise ValueError('qemu-img structural check reported defects')
        if fmt != 'img':
            # Non-strict comparison permits only zero-filled additional guest
            # sectors (VHD geometry rounding), never differences in raw sectors.
            _qemu(binary, ['compare', '-f', 'raw', '-F', qfmt, str(raw), str(image)])
        reports[fmt]['qemu'] = {
            'format': qfmt, 'virtual_size': virtual_size,
            'structural_check': 'passed' if check_supported else 'unsupported-by-format',
            'guest_sectors_equivalent_to_raw': True,
            'comparison': 'raw-reference' if fmt == 'img' else 'non-strict; extra sectors must be zero',
        }


def validate_all(directory, version, manifest_path, checksums_path, *, qemu_img=None):
    """Validate the exact six CHR x86 assets using the release inventory.

    The directory may also hold other products for profile=all. Only the six
    expected CHR x86 archives are selected; missing/duplicate assets fail closed.
    qemu_img is explicitly opt-in and failures/missing tools are never skipped.
    """
    if not isinstance(version, str) or not VALID_VERSION.fullmatch(version):
        raise ValueError('invalid RouterOS version')
    directory = Path(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('archive directory must not be a symlink')
    sources = expected_sources(version, 'x86', 'chr-x86')
    reports, images = {}, {}
    with tempfile.TemporaryDirectory(prefix='chr-validation-') as temporary:
        for fmt, source in zip(IMAGE_FORMATS, sources):
            archive = directory / branded_filename('x86', source)
            extracted = Path(temporary) / source[:-4] if qemu_img else None
            report = validate(archive, manifest_path, checksums_path, _image_output=extracted)
            if report['image'] != source[:-4]:
                raise ValueError('archive source does not match CHR x86 inventory')
            reports[fmt] = report
            images[fmt] = extracted
        if qemu_img:
            _validate_qemu(qemu_img, images, reports)
    return {'scope': 'build-only all six CHR x86 archives',
            'qemu_validated': bool(qemu_img), 'boot_tested': False,
            'activation_tested': False, 'assets': list(reports.values())}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group(required=True)
    selection.add_argument('--archive', type=Path)
    selection.add_argument('--directory', type=Path, help='validate all six CHR x86 archives')
    parser.add_argument('--version', help='required with --directory')
    parser.add_argument('--qemu-img', help='opt-in qemu-img executable for all-six validation')
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.directory is not None and not args.version:
        parser.error('--directory requires --version')
    if args.archive is not None and (args.version or args.qemu_img):
        parser.error('--version and --qemu-img require --directory')
    try:
        if args.directory is not None:
            report = validate_all(args.directory, args.version, args.manifest,
                                  args.checksums, qemu_img=args.qemu_img)
        else:
            report = validate(args.archive, args.manifest, args.checksums)
    except (OSError, ValueError, TypeError, AttributeError, KeyError,
            zipfile.BadZipFile, RuntimeError, subprocess.SubprocessError):
        print('CHR validation failed; no boot or activation claim can be made.', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
