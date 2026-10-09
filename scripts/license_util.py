"""Safe import wrapper for the repo's vendored license generator.

Generates CUSTOM LAB LICENSES signed by the lab's own keys. They are only
accepted by patched "Ali Patch Code" firmware, never by official MikroTik
software. This module is the only import surface other tools should use.
"""
import re

import license as repo_license

# license.py references MIKRO_LICENSE_HEADER/FOOTER inside lic_gen_* but only
# defines them under __main__; bind them so import users get stable output
# without running the argparse CLI.
repo_license.MIKRO_LICENSE_HEADER = (
    '-----BEGIN MIKROTIK SOFTWARE KEY------------')
repo_license.MIKRO_LICENSE_FOOTER = (
    '-----END MIKROTIK SOFTWARE KEY--------------')

import mikro  # noqa: E402

# RouterOS Software ID: 4 groups of 4 chars from the repo's 35-char table
# joined by a single dash, e.g. "4JZ2-H049".
ROS_SOFTWARE_ID_RE = re.compile(
    r'^[' + re.escape(mikro.SOFTWARE_ID_CHARACTER_TABLE.decode('ascii')) +
    r']{4}-[' + re.escape(mikro.SOFTWARE_ID_CHARACTER_TABLE.decode('ascii')) +
    r']{4}$')
# CHR System ID: exactly 11 chars from the case-sensitive base64 table.
CHR_SYSTEM_ID_RE = re.compile(
    r'^[' + re.escape(mikro.SYSTEM_ID_CHARACTER_TABLE.decode('ascii')) +
    r']{11}$')

MAX_PRIVATE_KEY_CHARS = 4096
MAX_LICENSE_CHARS = 32768

__all__ = [
    'generate_ros', 'generate_chr', 'parse',
    'ROS_SOFTWARE_ID_RE', 'CHR_SYSTEM_ID_RE',
]


def _clean(text):
    if not isinstance(text, str):
        raise ValueError('identifier harus berupa teks')
    return text.strip()


def _decode_private_key(private_key):
    if not isinstance(private_key, str):
        raise ValueError('private key harus berupa string heksadesimal')
    text = private_key.strip().replace(' ', '').replace('\n', '')
    if not text:
        raise ValueError('private key tidak boleh kosong')
    if len(text) > MAX_PRIVATE_KEY_CHARS:
        raise ValueError('private key terlalu panjang')
    try:
        key = bytes.fromhex(text)
    except ValueError:
        raise ValueError('private key harus heksadesimal yang valid') from None
    if len(key) != 32:
        raise ValueError('private key harus 32 byte (64 karakter heks)')
    # Existing lab keys may be non-reduced scalars; the vendor signer reduces
    # modulo the curve order. Reject only the zero residue, which has no inverse.
    if int.from_bytes(key, 'little') % mikro.getcurvebyname('Curve25519').n == 0:
        raise ValueError('private key memiliki scalar yang tidak valid')
    return key


def generate_ros(software_id, private_key, feature_bits=1):
    """Return a custom lab license for a RouterOS Software ID.

    feature_bits (0-15) selects the license feature nibble. The legacy
    default 1 keeps the payload byte-identical to older generator output
    (byte 0x16: level 6 + feature rendered as "extra-channels"); 0 issues a
    key whose RouterOS Features field is expected to stay empty.
    """
    software_id = _clean(software_id)
    if not ROS_SOFTWARE_ID_RE.fullmatch(software_id):
        raise ValueError(
            'Software ID RouterOS harus berformat XXXX-XXXX (huruf besar/'
            'angka dari tabel resmi), contoh 4JZ2-H049')
    if (isinstance(feature_bits, bool) or not isinstance(feature_bits, int)
            or not 0 <= feature_bits <= 15):
        raise ValueError('feature_bits harus bilangan bulat 0-15')
    return repo_license.lic_gen_ros(
        software_id, _decode_private_key(private_key), feature_bits=feature_bits)


def generate_chr(system_id, private_key):
    """Return a custom lab license for a CHR System ID."""
    system_id = _clean(system_id)
    if not CHR_SYSTEM_ID_RE.fullmatch(system_id):
        raise ValueError(
            'System ID CHR harus tepat 11 karakter base64 case-sensitive, '
            'contoh pjLQ21gHzfI')
    if mikro.mikro_systemid_decode(system_id) >= 1 << 64:
        raise ValueError(
            'System ID CHR terlalu besar (melebihi 8 byte) dan tidak dapat '
            'ditandatangani')
    return repo_license.lic_gen_chr(
        system_id, _decode_private_key(private_key))


def _decode_public_key(public_key):
    if not isinstance(public_key, str) or len(public_key) > 128:
        raise ValueError('public key harus berupa 64 karakter heksadesimal')
    try:
        key = bytes.fromhex(public_key.strip())
    except ValueError:
        raise ValueError('public key harus heksadesimal yang valid') from None
    if len(key) != 32:
        raise ValueError('public key harus 32 byte')
    return key


def parse(license_text, public_key):
    """Decode a canonical lab payload and verify its complete signature.

    Vendor lic_parse_* print instead of returning validity and do not identify
    payload type. Inspect the signed layout directly; never infer validity from
    a successful parse or mutate global stdout (the web server is threaded).
    """
    if not isinstance(license_text, str) or not 0 < len(license_text) <= MAX_LICENSE_CHARS:
        raise ValueError('lisensi harus berupa teks dengan panjang terbatas')
    key = _decode_public_key(public_key)
    lines = license_text.strip().splitlines()
    if (len(lines) not in (3, 4)
            or lines[0] != repo_license.MIKRO_LICENSE_HEADER
            or lines[-1] != repo_license.MIKRO_LICENSE_FOOTER):
        raise ValueError('format lisensi tidak valid')
    body = ''.join(lines[1:-1])
    if not re.fullmatch(r'[A-Za-z0-9+/]{86}==', body):
        raise ValueError('isi lisensi tidak valid')
    try:
        raw = mikro.mikro_base64_decode(body)
        if len(raw) != 64 or mikro.mikro_base64_encode(raw, True) != body:
            raise ValueError('panjang atau encoding lisensi tidak valid')
        payload = mikro.mikro_decode(raw[:16])
        valid = mikro.mikro_kcdsa_verify(payload, raw[16:], key)
    except (ValueError, TypeError, ArithmeticError, AssertionError, IndexError):
        raise ValueError('lisensi tidak dapat diverifikasi') from None
    if not valid:
        raise ValueError('signature lisensi tidak cocok dengan public key')

    fields = {'License valid': 'True'}
    if payload[6] == 7 and payload[8:] == b'\0' * 8:
        number = int.from_bytes(payload[:6], 'little')
        if number >= len(mikro.SOFTWARE_ID_CHARACTER_TABLE) ** 8:
            raise ValueError('Software ID dalam lisensi tidak valid')
        # Byte 7 packs feature bits (high nibble) + license level (low
        # nibble); nibble meaning verified statically, display pending lab A3.
        fields.update(kind='ros', **{
            'Software ID': mikro.mikro_softwareid_encode(number),
            'RouterOS Version': '7',
            'License Level': str(payload[7] & 0x0F),
            'Feature Bits': str(payload[7] >> 4),
        })
    elif payload[8:13] == bytes((0, 87, 134, 244, 3)) and payload[13:] == b'\0' * 3:
        fields.update(kind='chr', **{
            'System ID': mikro.mikro_systemid_encode(int.from_bytes(payload[:8], 'little')),
            'Deadline': '244', 'Level': '3',
        })
    else:
        raise ValueError('tipe payload lisensi custom tidak dikenal')
    return fields
