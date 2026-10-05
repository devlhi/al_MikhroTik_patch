#!/usr/bin/env python3
"""Verify a CHR image ZIP against release metadata; this is not a boot test."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import sys
import zipfile


MAX_IMAGE_BYTES = 16 * 1024 ** 3


def validate(archive, manifest_path, checksums_path):
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
        with bundle.open(member) as image:
            prefix = image.read(512)
            observed_size = len(prefix)
            image_digest.update(prefix)
            for chunk in iter(lambda: image.read(1024 * 1024), b''):
                observed_size += len(chunk)
                image_digest.update(chunk)
        if observed_size != member.file_size:
            raise ValueError('decoded image size does not match ZIP metadata')
        extension = image_name.rsplit('.', 1)[1]
        if extension == 'vmdk' and not prefix.startswith(b'KDMV'):
            raise ValueError('image does not have a sparse VMDK header')
        if extension == 'qcow2' and not prefix.startswith(b'QFI\xfb'):
            raise ValueError('image does not have a QCOW2 header')
    return {'archive': archive.name, 'archive_sha256': expected,
            'image': image_name, 'image_sha256': image_digest.hexdigest(),
            'image_size': member.file_size, 'zip_crc_verified': True,
            'boot_tested': False, 'activation_tested': False,
            'scope': 'byte integrity and ZIP structure only'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--checksums', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = validate(args.archive, args.manifest, args.checksums)
    except (OSError, ValueError, TypeError, AttributeError, KeyError,
            zipfile.BadZipFile, RuntimeError):
        print('CHR validation failed; no boot or activation claim can be made.', file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
