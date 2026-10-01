"""Local-only web console for Ali Patch Code custom lab licenses.

Binds to loopback only. The signing key stays server-side (file or environment
variable, never a command-line value, never sent to the browser). Licenses
generated here are CUSTOM LAB LICENSES accepted only by patched "Ali Patch
Code" firmware; they are not licenses for official MikroTik software.

Run:
  python3 scripts/license_server.py \
    --private-key-file /path/to/custom_license_private_key.hex \
    --port 12760
"""
import argparse
import hashlib
import math
import hmac
import http.server
import json
from pathlib import Path
import secrets
from typing import ClassVar
import sys
import threading
import time
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import license_util  # noqa: E402

BRAND = 'Ali Patch Code'
SCOPE = 'custom-lab-only'
LOOPBACK_BINDS = {'127.0.0.1', 'localhost'}
SESSION_TTL_SECONDS = 900
MAX_SESSIONS = 1000
MAX_BODY_BYTES = 4096
STATIC_FILES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/app.css': ('app.css', 'text/css; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
}
SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; img-src 'self'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'self'"),
    'Cache-Control': 'no-store',
}


class _ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def _parse_public_origin(value):
    """Only a canonical HTTPS DNS origin; forwarded headers are never trusted."""
    if (not isinstance(value, str) or not value or len(value) > 300
            or not value.isascii() or any(ord(ch) < 33 or ord(ch) == 127 for ch in value)):
        raise ValueError('allowed-origin harus origin HTTPS domain DNS yang valid')
    try:
        parts = urlsplit(value)
        host, port = parts.hostname, parts.port
    except ValueError:
        raise ValueError('allowed-origin tidak valid') from None
    if (parts.scheme.lower() != 'https' or not host or parts.username is not None
            or parts.password is not None or parts.path or parts.query or parts.fragment
            or '?' in value or '#' in value or parts.netloc.endswith(':')
            or host.endswith('.') or len(host) > 253 or '.' not in host):
        raise ValueError('allowed-origin harus HTTPS domain tanpa path/query/credentials')
    import ipaddress
    import re
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('allowed-origin harus domain DNS, bukan IP')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
           for label in host.split('.')) or not any(ch.isalpha() for ch in host.split('.')[-1]):
        raise ValueError('allowed-origin memiliki domain DNS yang tidak valid')
    if port is not None and not 1 <= port <= 65535:
        raise ValueError('allowed-origin memiliki port yang tidak valid')
    suffix = '' if port in (None, 443) else ':' + str(port)
    origin = 'https://' + host + suffix
    hosts = {host, host + ':443'} if not suffix else {host + suffix}
    return origin, hosts


class _State:
    def __init__(self, private_key_hex, static_dir, cooldown, allowed_origin=None,
                 health_endpoint=False):
        self.allowed_origin = None
        self.allowed_hosts = set()
        if allowed_origin is not None:
            self.allowed_origin, self.allowed_hosts = _parse_public_origin(allowed_origin)
        self.health_endpoint = health_endpoint
        self.private_key = license_util._decode_private_key(private_key_hex)
        self.static_dir = Path(static_dir)
        self.cooldown = cooldown
        self.lock = threading.Lock()
        self.sessions = {}
        self.last_generate = {}

    def public_key(self):
        return _derive_public_key(self.private_key)

    def key_fingerprint(self):
        return hashlib.sha256(self.public_key()).hexdigest()[:16]

    def new_session(self):
        now = time.monotonic()
        with self.lock:
            self.sessions = {t: exp for t, exp in self.sessions.items()
                             if exp > now}
            if len(self.sessions) >= MAX_SESSIONS:
                raise _ApiError(503, 'Server terlalu sibuk, coba lagi nanti')
            token = secrets.token_urlsafe(32)
            self.sessions[token] = now + SESSION_TTL_SECONDS
        return token

    def consume_session(self, token):
        if not isinstance(token, str) or len(token) > 256:
            raise _ApiError(403, 'Sesi tidak valid; muat ulang halaman')
        now = time.monotonic()
        with self.lock:
            expiry = self.sessions.get(token)
            if expiry is None or expiry <= now:
                self.sessions.pop(token, None)
                raise _ApiError(403, 'Sesi kadaluarsa; muat ulang halaman')
            # A token belongs to an open page; allow multiple submissions.
            self.sessions[token] = now + SESSION_TTL_SECONDS

    def enforce_cooldown(self, client):
        now = time.monotonic()
        with self.lock:
            last = self.last_generate.get(client, 0.0)
            if now - last < self.cooldown:
                raise _ApiError(429, 'Terlalu sering; tunggu sebentar')
            self.last_generate[client] = now
            if len(self.last_generate) > 4096:
                self.last_generate = {c: t for c, t in self.last_generate.items()
                                      if now - t < 300}


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _ApiError(400, 'Key JSON duplikat tidak diizinkan')
        result[key] = value
    return result


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'AliPatchCode'
    sys_version = ''
    protocol_version = 'HTTP/1.1'
    state: ClassVar[_State]  # set by create_server

    def setup(self):
        self.request.settimeout(5)
        super().setup()

    def log_message(self, format, *args):
        # No access log: even an unknown URL can contain private user input.
        pass

    def log_request(self, code='-', size='-'):
        pass

    def _check_host_and_origin(self):
        host = (self.headers.get('Host') or '').strip()
        port = self.server.server_address[1]
        allowed_hosts = self.state.allowed_hosts or {f'127.0.0.1:{port}', f'localhost:{port}'}
        if len(self.headers.get_all('Host', [])) != 1 or host.lower() not in allowed_hosts:
            raise _ApiError(403, 'Host tidak diizinkan')
        origins = self.headers.get_all('Origin', [])
        if len(origins) > 1 or (self.command == 'POST' and not origins):
            raise _ApiError(403, 'Origin tidak diizinkan')
        expected_origin = self.state.allowed_origin or ('http://' + host)
        if origins and origins[0] != expected_origin:
            raise _ApiError(403, 'Origin tidak diizinkan')
        fetch_site = self.headers.get('Sec-Fetch-Site')
        if fetch_site is not None and fetch_site not in (
                'same-origin', 'none'):
            raise _ApiError(403, 'Permintaan lintas situs ditolak')

    def _send(self, status, body, content_type='application/json; charset=utf-8',
              extra=None):
        self.close_connection = True
        self.send_response(status)
        self.send_header('Connection', 'close')
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        for key, value in SECURITY_HEADERS.items():
            self.send_header(key, value)
        for key, value in (extra or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def _api_error(self, error):
        try:
            self._send_json(error.status, {'error': error.message})
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if self.state.allowed_origin or (path == '/api/health' and self.state.health_endpoint):
            try:
                self._check_host_and_origin()
            except _ApiError as error:
                self._api_error(error)
                return
        if path == '/api/health' and self.state.health_endpoint:
            self._send_json(200, {'status': 'ok'})
            return
        if path == '/api/session':
            try:
                self._check_host_and_origin()
                token = self.state.new_session()
                self._send_json(200, {
                    'csrf_token': token,
                    'key_fingerprint': self.state.key_fingerprint(),
                    'brand': BRAND,
                    'scope': SCOPE,
                })
            except _ApiError as error:
                self._api_error(error)
            except Exception:
                self._api_error(_ApiError(500, 'Kesalahan internal server'))
            return
        entry = STATIC_FILES.get(path)
        if entry is None:
            self._send_json(404, {'error': 'Halaman tidak ditemukan'})
            return
        name, content_type = entry
        try:
            body = (self.state.static_dir / name).read_bytes()
        except OSError:
            self._send_json(404, {'error': 'Berkas tidak ditemukan'})
            return
        self._send(200, body, content_type=content_type)

    def do_POST(self):
        if urlsplit(self.path).path != '/api/generate':
            self._send_json(404, {'error': 'Endpoint tidak ditemukan'})
            return
        try:
            self._check_host_and_origin()
            self.state.consume_session(self.headers.get('X-CSRF-Token'))
            content_type = self.headers.get('Content-Type', '')
            if content_type.split(';')[0].strip().lower() != 'application/json':
                raise _ApiError(415, 'Content-Type harus application/json')
            if self.headers.get('Transfer-Encoding'):
                raise _ApiError(400, 'Transfer-Encoding tidak didukung')
            try:
                length = int(self.headers.get('Content-Length', ''))
            except ValueError:
                raise _ApiError(400, 'Content-Length tidak valid') from None
            if length <= 0 or length > MAX_BODY_BYTES:
                raise _ApiError(413, 'Body terlalu besar')
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode('utf-8'),
                                     object_pairs_hook=_reject_duplicates)
            except _ApiError:
                raise
            except (UnicodeDecodeError, json.JSONDecodeError, RecursionError):
                raise _ApiError(400, 'Body bukan JSON yang valid') from None
            if (not isinstance(payload, dict)
                    or set(payload) != {'kind', 'identifier'}
                    or payload['kind'] not in ('chr', 'ros')):
                raise _ApiError(400, "Body harus {kind: 'chr'|'ros', identifier: string}")
            identifier = payload['identifier']
            if not isinstance(identifier, str) or not identifier.strip():
                raise _ApiError(400, 'Identifier tidak boleh kosong')
            if len(identifier) > 128:
                raise _ApiError(400, 'Identifier terlalu panjang')

            self.state.enforce_cooldown(self.client_address[0])
            if payload['kind'] == 'chr':
                license_text = license_util.generate_chr(
                    identifier, self.state.private_key.hex())
            else:
                license_text = license_util.generate_ros(
                    identifier, self.state.private_key.hex())
            fields = license_util.parse(
                license_text, self.state.public_key().hex())
            expected_key = 'System ID' if payload['kind'] == 'chr' else 'Software ID'
            if (fields.get('License valid') != 'True'
                    or fields.get('kind') != payload['kind']
                    or fields.get(expected_key) != identifier.strip()):
                raise _ApiError(500, 'Verifikasi internal gagal; lisensi tidak dikirim')
            self._send_json(200, {
                'kind': payload['kind'],
                'identifier': identifier.strip(),
                'license': license_text,
                'verified': True,
                'scope': SCOPE,
            })
        except _ApiError as error:
            self._api_error(error)
        except ValueError as error:
            self._api_error(_ApiError(400, str(error)))
        except Exception:
            self._api_error(_ApiError(500, 'Kesalahan internal server'))

    def do_PUT(self):
        self._send_json(405, {'error': 'Metode tidak didukung'})

    do_DELETE = do_PATCH = do_PUT


class LicenseServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False


def _derive_public_key(private_key):
    from mikro import getcurvebyname, Tools
    from toyecc import ECPrivateKey
    curve = getcurvebyname('Curve25519')
    key = ECPrivateKey(Tools.bytestoint_le(private_key), curve)
    return Tools.inttobytes_le(int(key.pubkey.point.x), 32)


def create_server(private_key_hex, port=0, static_dir=None, cooldown=1.0,
                  bind='127.0.0.1', allowed_origin=None, health_endpoint=False):
    """Build a loopback-bound server; port=0 picks a free ephemeral port."""
    if bind not in LOOPBACK_BINDS:
        raise ValueError('Server hanya boleh diikat ke loopback')
    static_dir = Path(static_dir) if static_dir else REPO_ROOT / 'web' / 'license'
    handler = type('BoundHandler', (_Handler,), {})
    handler.state = _State(private_key_hex, static_dir, cooldown, allowed_origin,
                           health_endpoint)
    # Validate key material up front so bad config fails before listening.
    license_util.generate_ros('4JZ2-H049', private_key_hex)
    return LicenseServer(('127.0.0.1', port), handler)



def _default_private_key_file():
    """Git-ignored 64-hex key file next to the repo (chmod 600), if present."""
    return REPO_ROOT / '.ali_license_private_key'


def _workflow_private_key():
    """Read the lab key pinned in .github/workflows/patch7.yml; never print it.

    The workflow also pins the matching public key. If the two disagree the
    local file was edited and every generated license would be rejected by
    the patched firmware, so refuse to start instead.
    """
    import yaml
    workflow = REPO_ROOT / '.github' / 'workflows' / 'patch7.yml'
    try:
        config = yaml.safe_load(workflow.read_text(encoding='utf-8'))
    except OSError as error:
        raise ValueError('tidak dapat membaca %s (%s)' % (workflow.name, error)) from None
    except yaml.YAMLError:
        # Pesan error PyYAML menyertakan baris sumber berkas; jangan
        # diteruskan karena dapat membocorkan nilai env (termasuk kunci).
        raise ValueError('patch7.yml bukan YAML yang valid') from None
    env = config.get('env') if isinstance(config, dict) else None
    env = env if isinstance(env, dict) else {}
    private_hex = env.get('CUSTOM_LICENSE_PRIVATE_KEY')
    public_hex = env.get('CUSTOM_LICENSE_PUBLIC_KEY')
    if not isinstance(private_hex, str) or not isinstance(public_hex, str):
        raise ValueError('env CUSTOM_LICENSE_PRIVATE_KEY/CUSTOM_LICENSE_PUBLIC_KEY '
                         'tidak ditemukan di patch7.yml')
    private_key = license_util._decode_private_key(private_hex)
    if _derive_public_key(private_key).hex() != public_hex.strip().lower():
        raise ValueError('CUSTOM_LICENSE_PRIVATE_KEY tidak cocok dengan '
                         'CUSTOM_LICENSE_PUBLIC_KEY di patch7.yml')
    return private_key.hex()


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Konsol lisensi lab lokal Ali Patch Code (loopback saja)')
    parser.add_argument('--private-key-file',
                        help='Berkas berisi 64 karakter heks private key lisensi custom')
    parser.add_argument('--port', type=int, default=12760)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--static-dir', default=str(REPO_ROOT / 'web' / 'license'))
    parser.add_argument('--cooldown', type=float, default=1.0)
    parser.add_argument('--allowed-origin', help='Origin HTTPS domain; wajib reverse proxy dengan autentikasi')
    parser.add_argument('--health-endpoint', action='store_true', help='Aktifkan /api/health untuk probe lokal')
    args = parser.parse_args(argv)

    import os
    if args.private_key_file:
        key_file = Path(args.private_key_file)
        if not key_file.is_file():
            parser.error('berkas kunci tidak ditemukan: %s '
                         '(tidak ada fallback ke env/workflow)' % key_file)
        try:
            key_text = key_file.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            parser.error('berkas kunci tidak dapat dibaca sebagai teks UTF-8')
    elif os.environ.get('ALI_LICENSE_PRIVATE_KEY'):
        key_text = os.environ['ALI_LICENSE_PRIVATE_KEY']
    elif _default_private_key_file().is_file():
        key_text = _default_private_key_file().read_text(encoding='utf-8')
    else:
        # Default sesuai pilihan pemilik lab: kunci custom yang sudah dipin
        # di workflow repo, dibaca lokal dan tidak pernah ditampilkan.
        try:
            key_text = _workflow_private_key()
        except ValueError as error:
            parser.error('tidak dapat memuat kunci dari workflow: %s '
                         '(alternatif: --private-key-file PATH, env '
                         'ALI_LICENSE_PRIVATE_KEY, atau berkas '
                         '.ali_license_private_key)' % error)
    if args.bind not in LOOPBACK_BINDS:
        parser.error('--bind hanya boleh 127.0.0.1 atau localhost')
    if not math.isfinite(args.cooldown) or args.cooldown < 0:
        parser.error('--cooldown harus angka >= 0')
    if not 0 <= args.port <= 65535:
        parser.error('--port harus 0-65535')
    try:
        server = create_server(key_text, port=args.port, static_dir=args.static_dir,
                               cooldown=args.cooldown, bind=args.bind,
                               allowed_origin=args.allowed_origin,
                               health_endpoint=args.health_endpoint)
    except ValueError as error:
        parser.error('kunci/konfigurasi tidak valid: %s' % error)
    except OSError:
        parser.error('tidak dapat mengikat %s:%d' % (args.bind, args.port))
    print('Ali Patch Code license console (local lab only)')
    print('  url      : http://%s:%d' % (args.bind, server.server_port))
    print('  fingerprint publik:', server.RequestHandlerClass.state.key_fingerprint())
    print('  scope    : custom lab licenses untuk firmware hasil patch; '
          'bukan lisensi resmi MikroTik')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
