#!/usr/bin/env python3
"""Strict, offline renderer for the private custom-lab VPS panel."""
import argparse
import ast
import http.client
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import ssl
import stat
import sys

APP_FILES = (
    'scripts/license_server.py', 'scripts/license_util.py', 'license.py',
    'mikro.py', 'sha256.py', 'web/license/index.html', 'web/license/app.css',
    'web/license/app.js', 'requirements-license.txt',
)


def source_files(source):
    root = Path(source).absolute()
    if not root.is_dir() or root.is_symlink():
        raise ValueError('checkout lokal bukan direktori biasa')

    def checked(relative):
        path = root / relative
        parents = []
        for parent in path.parents:
            if parent == root:
                break
            parents.append(parent)
        if (not path.is_file() or path.is_symlink()
                or any(p.is_symlink() for p in parents)):
            raise ValueError(f'berkas wajib hilang/symlink: {relative}')
        return path

    files = [(relative, checked(relative)) for relative in APP_FILES]
    package = root / 'toyecc'
    if not package.is_dir() or package.is_symlink():
        raise ValueError('paket toyecc hilang/symlink')
    checked('toyecc/__init__.py')
    for path in sorted(package.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink dalam toyecc ditolak')
        relative = path.relative_to(root)
        if (path.is_file() and path.suffix == '.py'
                and not any(p.startswith('.') or p == '__pycache__'
                            for p in relative.parts)):
            files.append((str(relative), checked(relative)))
    # Parse only shipped Python, never import/execute checkout code as root.
    # A local dependency excluded by the allowlist is an early hard failure.
    included = {relative for relative, _ in files}
    for relative, path in files:
        if path.suffix != '.py':
            continue
        try:
            tree = ast.parse(path.read_text(encoding='utf-8'))
        except (SyntaxError, UnicodeError):
            raise ValueError(f'syntax Python tidak valid: {relative}') from None
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules = [node.module]
                modules.extend(f'{node.module}.{alias.name}' for alias in node.names
                               if alias.name != '*')
            for module in modules:
                parts = module.split('.')
                # Check each package prefix too; namespace packages (scripts/)
                # need no __init__, and imported attributes need no module file.
                for length in range(1, len(parts) + 1):
                    base = Path(*parts[:length])
                    for candidate in (base.with_suffix('.py'), base / '__init__.py'):
                        dependency = str(candidate)
                        if (root / candidate).is_file() and dependency not in included:
                            raise ValueError(f'allowlist kurang dependency {dependency}; perlu persetujuan penambahan sebelum deployment')
    return files


def copy_app(source, destination):
    files = source_files(source)  # Validate the complete tree before writing.
    out = Path(destination)
    out.mkdir(mode=0o755)
    out.chmod(0o755)
    for relative, source_path in files:
        target = out / relative
        target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
        for parent in target.parents:
            if parent == out:
                break
            parent.chmod(0o755)
        with source_path.open('rb') as src, target.open('xb') as dst:
            shutil.copyfileobj(src, dst)
        target.chmod(0o644)


def validate_key(key_file):
    path = Path(key_file)
    if not path.is_file() or path.is_symlink():
        raise ValueError('berkas kunci harus berkas biasa, bukan symlink')
    info = path.stat()
    if info.st_mode & (stat.S_IRWXG | stat.S_IRWXO) or info.st_size > 128:
        raise ValueError('berkas kunci harus chmod 600/400 dan maksimal 128 byte')
    try:
        value = path.read_text(encoding='ascii').strip()
    except UnicodeError:
        raise ValueError('kunci harus 64 karakter hex ASCII') from None
    if not re.fullmatch(r'[0-9a-fA-F]{64}', value) or int(value, 16) == 0:
        raise ValueError('kunci harus 32 byte hex bukan nol; nilai tidak ditampilkan')
    # Signer startup separately validates the curve scalar; no repo import here.


def validate_user(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{2,31}', value):
        raise ValueError('username harus 3-32 karakter ASCII huruf/angka/_/-')
    return value


def auth_directive(version):
    match = re.match(r'^v?(\d+)\.(\d+)\.(\d+)(?:\s|$)', version)
    if not match or not (2, 6, 0) <= tuple(map(int, match.groups())) < (3, 0, 0):
        raise ValueError('Caddy rilis stabil 2.6+ (major 2) diperlukan')
    return 'basic_auth' if int(match[2]) >= 8 else 'basicauth'


def render(domain, user, hash_file, version, output_dir):
    domain = validate_domain(domain)
    user = validate_user(user)
    directive = auth_directive(version)
    hashed = Path(hash_file).read_text(encoding='ascii').strip()
    if not re.fullmatch(r'\$2[aby]\$(?:1[0-6])\$[./A-Za-z0-9]{53}', hashed):
        raise ValueError('hash bcrypt tidak valid (cost 10-16); plaintext ditolak')
    caddy = f'''# Managed standalone PRIVATE custom-lab panel. No access/request logs.
{{
    admin off
    log {{
        output discard
    }}
    servers {{
        max_header_size 16KB
        timeouts {{
            read_header 5s
            read_body 10s
            write 30s
            idle 30s
        }}
    }}
}}

https://{domain} {{
    route {{
        {directive} {{
            {user} {hashed}
        }}
        @wrong_host expression `{{http.request.hostport}} != "{domain}" && {{http.request.hostport}} != "{domain}:443"`
        respond @wrong_host 421
        request_body {{
            max_size 4KB
        }}
        reverse_proxy 127.0.0.1:12760 {{
            header_up Host {domain}
            header_up -Authorization
            header_up -Forwarded
            header_up -X-Forwarded-*
            transport http {{
                dial_timeout 3s
                response_header_timeout 10s
                read_timeout 15s
                write_timeout 15s
            }}
        }}
    }}
}}
'''
    unit = f'''# PRIVATE custom-lab only; not an official MikroTik license service.
[Unit]
Description=Ali Patch Code private custom-lab panel
After=network.target

[Service]
Type=simple
User=ali-patch-code
Group=ali-patch-code
WorkingDirectory=/opt/ali-patch-code
ExecStart=/opt/ali-patch-code/.venv/bin/python /opt/ali-patch-code/scripts/license_server.py --bind 127.0.0.1 --port 12760 --private-key-file /etc/ali-patch-code/license.key --allowed-origin https://{domain} --health-endpoint
Environment=PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5s
UMask=0077
LimitCORE=0
NoNewPrivileges=true
PrivateTmp=true
PrivateDevices=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
ProtectClock=true
ProtectHostname=true
RestrictSUIDSGID=true
RestrictRealtime=true
LockPersonality=true
CapabilityBoundingSet=
AmbientCapabilities=
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
ReadOnlyPaths=/opt/ali-patch-code /etc/ali-patch-code
StandardOutput=null
StandardError=null

[Install]
WantedBy=multi-user.target
'''
    out = Path(output_dir)
    out.mkdir(mode=0o700)  # Deliberately refuse even an existing empty directory.
    for name, text in [('Caddyfile', caddy), ('ali-patch-code.service', unit)]:
        path = out / name
        with path.open('x', encoding='utf-8') as stream:
            path.chmod(0o600)
            stream.write(text)


def validate_domain(value):
    """Only a literal public ASCII DNS name, never a URL or Caddy token."""
    value = value.lower()
    labels = value.split('.')
    if (len(value) > 253 or len(labels) < 2
            or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', p)
                   for p in labels)
            or not re.fullmatch(r'[a-z]{2,63}', labels[-1])
            or labels[-1] in {'local', 'localhost', 'internal', 'lan', 'home',
                              'test', 'invalid', 'onion', 'example', 'arpa'}):
        raise ValueError('domain harus nama DNS publik ASCII tanpa URL/port/wildcard')
    return value


def check_dns(domain):
    domain = validate_domain(domain)
    addresses = sorted({entry[4][0] for entry in socket.getaddrinfo(
        domain, 443, type=socket.SOCK_STREAM)})
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError('DNS A/AAAA harus seluruhnya alamat publik; cek DNS terlebih dahulu')
    return addresses


def check_backend(domain, port=12760):
    domain = validate_domain(domain)
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    try:
        conn.request('GET', '/api/health', headers={'Host': domain})
        response = conn.getresponse()
        if response.status != 200 or json.loads(response.read(256)) != {'status': 'ok'}:
            raise ValueError('health backend gagal')
    finally:
        conn.close()


def check_public(domain):
    domain = validate_domain(domain)
    # Direct TLS: no proxies from the environment, no -k, no redirects followed.
    context = ssl.create_default_context()
    for path in ('/', '/app.js', '/app.css', '/api/session', '/api/health',
                 '/api/generate', '/not-found'):
        conn = http.client.HTTPSConnection(domain, 443, timeout=5, context=context)
        try:
            conn.request('POST' if path == '/api/generate' else 'GET', path)
            response = conn.getresponse()
            auth = response.getheader('WWW-Authenticate', '')
            if response.status != 401 or not auth.lower().startswith('basic '):
                raise ValueError('TLS/Basic Auth probe harus 401 pada seluruh path')
        finally:
            conn.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    domain_parser = commands.add_parser('validate-domain')
    domain_parser.add_argument('domain')
    render_parser = commands.add_parser('render')
    render_parser.add_argument('--domain', required=True)
    render_parser.add_argument('--admin-user', default='admin')
    render_parser.add_argument('--password-hash-file', required=True)
    render_parser.add_argument('--caddy-version', default='2.8.4')
    render_parser.add_argument('--output-dir', required=True)
    copy_parser = commands.add_parser('copy-app')
    copy_parser.add_argument('--source', required=True)
    copy_parser.add_argument('--destination', required=True)
    key_parser = commands.add_parser('validate-key')
    key_parser.add_argument('key_file')
    check_parser = commands.add_parser('check-source')
    check_parser.add_argument('--source', required=True)
    user_parser = commands.add_parser('validate-user')
    user_parser.add_argument('user')
    version_parser = commands.add_parser('validate-version')
    version_parser.add_argument('version')
    for name in ('dns-check', 'check-backend', 'check-public'):
        commands.add_parser(name).add_argument('domain')
    args = parser.parse_args(argv)
    try:
        if args.command == 'validate-domain':
            print(validate_domain(args.domain))
        elif args.command == 'render':
            render(args.domain, args.admin_user, args.password_hash_file,
                   args.caddy_version, args.output_dir)
        elif args.command == 'copy-app':
            copy_app(args.source, args.destination)
        elif args.command == 'validate-key':
            validate_key(args.key_file)
        elif args.command == 'check-source':
            source_files(args.source)  # Raises listing the missing file name.
        elif args.command == 'validate-user':
            print(validate_user(args.user))
        elif args.command == 'validate-version':
            print(auth_directive(args.version))
        elif args.command == 'dns-check':
            print(' '.join(check_dns(args.domain)))
        elif args.command == 'check-backend':
            check_backend(args.domain)
        elif args.command == 'check-public':
            check_public(args.domain)
    except (ValueError, OSError) as error:
        # Never include secret file contents in errors.
        parser.exit(2, f'Konfigurasi ditolak: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
