"""Exact CHR terminal logo resource patch; never a note or a license patch.

7.24.4 login loads ASCII art from a file, not from an inline ELF string.
The pinned ELF consumer and its read-only path anchor are checked before edits.
"""
import hashlib
import os
from pathlib import Path
import stat
import struct

POLICY = 'chr-x86-7.24.4-ali-media-patch'
TARGET = 'nova/lib/console/logo.txt'
CONSUMER = 'nova/bin/login'
CONSUMER_SHA256 = '4d43156092a5aa52f6e3f14a68fba818405fe1f1db13132721919784eb72c626'
PATH_ANCHOR = b'/nova/lib/console/logo.txt\0'
ORIGINAL = (
    b'\n'
    b'  MMM      MMM       KKK                          TTTTTTTTTTT      KKK\n'
    b'  MMMM    MMMM       KKK                          TTTTTTTTTTT      KKK\n'
    b'  MMM MMMM MMM  III  KKK  KKK  RRRRRR     OOOOOO      TTT     III  KKK  KKK\n'
    b'  MMM  MM  MMM  III  KKKKK     RRR  RRR  OOO  OOO     TTT     III  KKKKK\n'
    b'  MMM      MMM  III  KKK KKK   RRRRRR    OOO  OOO     TTT     III  KKK KKK\n'
    b'  MMM      MMM  III  KKK  KKK  RRR  RRR   OOOOOO      TTT     III  KKK  KKK\n'
    b'\n'
    b'  MikroTik routerOS V2.4 (c) 1999-2001       http://mikrotik.com/\n'
)


def _replacement():
    # The pinned login consumer prints rows 0..7. Keep all six MikroTik art
    # rows intact and use the following blank row for the plain caption.
    # This is a text resource, not ELF: growing it by 17 bytes is intentional.
    rows = ORIGINAL.split(b'\n')
    rows[7] = b'  Ali Media Patch'
    return b'\n'.join(rows)


REPLACEMENT = _replacement()


def _consumer_anchor(data):
    """Validate ELF32/i386 ET_EXEC and unique read-only, non-executable PT_LOAD."""
    if (not isinstance(data, bytes) or len(data) < 52
            or data[:7] != b'\x7fELF\x01\x01\x01'):
        raise ValueError('terminal banner requires ELF32 little-endian consumer')
    h = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    _, kind, machine, version, _, phoff, _, _, ehsize, phsize, count, *_ = h
    if (kind != 2 or machine != 3 or version != 1 or ehsize != 52
            or phsize != 32 or not 0 < count < 0xffff or phoff < ehsize
            or phoff + phsize * count > len(data)):
        raise ValueError('unsupported terminal banner ELF schema')
    if data.count(PATH_ANCHOR) != 1:
        raise ValueError('missing or ambiguous terminal logo path anchor')
    start = data.index(PATH_ANCHOR)
    end = start + len(PATH_ANCHOR)
    matches = []
    for i in range(count):
        ptype, offset, _, _, size, memsize, flags, _ = struct.unpack_from(
            '<8I', data, phoff + i * phsize)
        if ptype != 1:
            continue
        if offset + size > len(data) or size > memsize:
            raise ValueError('invalid terminal consumer load segment')
        if offset < end and start < offset + size:
            matches.append((offset, size, flags))
    if (len(matches) != 1 or matches[0][2] != 4
            or not matches[0][0] <= start < end <= sum(matches[0][:2])
            or start < phoff + phsize * count):
        raise ValueError('logo path must be wholly inside one read-only ELF load segment')
    if hashlib.sha256(data).hexdigest() != CONSUMER_SHA256:
        raise ValueError('unsupported terminal consumer fingerprint')
    return start


def patch_terminal_banner(data, consumer, *, policy, target=TARGET):
    """Return (bytes, logo-only report); strict idempotency, no key statistics."""
    if policy != POLICY or target != TARGET:
        raise ValueError('unsupported terminal banner policy or target')
    anchor_offset = _consumer_anchor(consumer)
    if not isinstance(data, bytes) or data not in (ORIGINAL, REPLACEMENT):
        raise ValueError('missing, ambiguous or unsupported exact terminal logo schema')
    changed = data == ORIGINAL
    return REPLACEMENT, {
        'policy': policy, 'target': target, 'status': 'patched' if changed else 'already-patched',
        'replacements': int(changed), 'resource_offset': 0, 'size': len(data),
        'output_size': len(REPLACEMENT), 'size_delta': len(REPLACEMENT) - len(data),
        'consumer': CONSUMER, 'consumer_anchor_offset': anchor_offset,
        'counted_as_license_coverage': False,
        'before_sha256': hashlib.sha256(data).hexdigest(),
        'after_sha256': hashlib.sha256(REPLACEMENT).hexdigest(),
    }


def _regular(root, relative):
    root = Path(root)
    file = root / relative
    parent = root
    for part in (None, *file.relative_to(root).parts[:-1]):
        # Check every ancestor, not just the immediate file parent.
        if part is not None:
            parent = parent / part
        if parent.is_symlink() or not parent.is_dir():
            raise ValueError('terminal banner requires real directory ancestors')
    st = file.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
        raise ValueError('terminal banner requires regular unlinked file: ' + relative)
    return file


def plan_terminal_banner(root, policy):
    """Read and validate both files before any tree mutation."""
    if policy != POLICY:
        raise ValueError('unsupported terminal banner policy')
    try:
        file = _regular(root, TARGET)
        consumer = _regular(root, CONSUMER)
    except OSError as exc:
        raise ValueError('missing terminal banner target or consumer') from exc
    original = file.read_bytes()
    replacement, report = patch_terminal_banner(original, consumer.read_bytes(), policy=policy)
    return file, original, replacement, report


def write_terminal_banner(plan):
    file, original, replacement, report = plan
    if file.read_bytes() != original:
        raise ValueError('terminal banner target changed since preflight')
    if original != replacement:
        st = file.stat()
        file.write_bytes(replacement)
        os.chmod(file, stat.S_IMODE(st.st_mode))
        os.utime(file, ns=(st.st_atime_ns, st.st_mtime_ns))
    return report
