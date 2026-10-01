"""Offline packaging tests: no root, package manager, or external network."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock


def load_renderer():
    spec = importlib.util.spec_from_file_location('panel_renderer', RENDERER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / 'deploy' / 'render_panel_config.py'
INSTALLER = ROOT / 'deploy' / 'install-panel.sh'
SCRATCH = Path.home() / '.hermes' / 'cache' / 'scratch'
if not SCRATCH.is_dir():
    SCRATCH = Path(tempfile.gettempdir())
# Format-only bcrypt fixture, never an installer default or working login.
BCRYPT = '$2a$14$' + 'A' * 53
FIXED_FILES = ['scripts/license_server.py', 'scripts/license_util.py',
               'license.py', 'mikro.py', 'sha256.py', 'web/license/index.html',
               'web/license/app.css', 'web/license/app.js', 'requirements-license.txt']
PACKAGE_FILES = ['toyecc/__init__.py', 'toyecc/Tools.py',
                 'toyecc/nested/__init__.py', 'toyecc/nested/one.py']


def run_renderer(*args):
    return subprocess.run([sys.executable, str(RENDERER), *map(str, args)],
                          text=True, capture_output=True, timeout=10)


def run_installer(*args):
    return subprocess.run(['bash', str(INSTALLER), *map(str, args)],
                          text=True, capture_output=True, timeout=10)


class DeploymentTests(unittest.TestCase):
    def test_domain_is_canonical_and_cannot_inject_configuration(self):
        good = run_renderer('validate-domain', 'Panel.Example.COM')
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertEqual(good.stdout.strip(), 'panel.example.com')
        for domain in ('https://panel.example.com', 'panel.example.com/path',
                       '*.example.com', '127.0.0.1', '[::1]', 'localhost',
                       'panel.local', 'panel.internal', 'x.localhost',
                       'x.test', 'x.invalid', 'foo.onion', 'foo.123',
                       'panel.example.com:443', 'panel.example.com.',
                       '-x.example.com', 'x_.example.com', 'a..example.com',
                       'x.com\n{ admin off }', 'x.com;id', 'x.com $(id)',
                       '{$DOMAIN}', 'büro.example.com', 'a' * 64 + '.com'):
            with self.subTest(domain=domain):
                result = run_renderer('validate-domain', domain)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')

    def render(self, directory, *, version='2.8.4', user='admin', hash_value=BCRYPT):
        hash_file = directory / 'hash'
        hash_file.write_text(hash_value, encoding='ascii')
        hash_file.chmod(0o600)
        return run_renderer('render', '--domain', 'Panel.Example.COM',
                            '--admin-user', user, '--password-hash-file', hash_file,
                            '--caddy-version', version, '--output-dir', directory / 'out')

    def test_renderer_protects_every_path_and_supports_distro_caddy(self):
        for version, directive in [('2.6.2', 'basicauth'), ('v2.8.4', 'basic_auth'),
                                   ('2.10.2 h1:abc', 'basic_auth')]:
            with self.subTest(version=version), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                result = self.render(directory, version=version)
                self.assertEqual(result.returncode, 0, result.stderr)
                conf = (directory / 'out' / 'Caddyfile').read_text()
                self.assertIn('https://panel.example.com {', conf)
                self.assertIn(f'{directive} {{\n            admin {BCRYPT}', conf)
                self.assertNotIn('handle_path', conf)
                self.assertNotIn('file_server', conf)
                self.assertLess(conf.index(directive + ' {'), conf.index('reverse_proxy'))
                for expected in ('max_size 4KB', 'read_header 5s', 'read_body 10s',
                                 'write 30s', 'idle 30s', 'max_header_size 16KB',
                                 'response_header_timeout 10s',
                                 'reverse_proxy 127.0.0.1:12760',
                                 'header_up Host panel.example.com',
                                 'header_up -Authorization', 'header_up -Forwarded',
                                 'output discard', 'admin off'):
                    self.assertIn(expected, conf)
                self.assertNotIn('trusted_proxies', conf)
                unit = (directory / 'out' / 'ali-patch-code.service').read_text()
                for expected in ('User=ali-patch-code', 'Group=ali-patch-code',
                                 '--bind 127.0.0.1 --port 12760',
                                 '--allowed-origin https://panel.example.com',
                                 '--health-endpoint',
                                 '--private-key-file /etc/ali-patch-code/license.key',
                                 'ProtectSystem=strict', 'ProtectHome=true',
                                 'NoNewPrivileges=true', 'UMask=0077',
                                 'CapabilityBoundingSet=', 'RestrictSUIDSGID=true',
                                 'IPAddressDeny=any', 'IPAddressAllow=localhost',
                                 'ReadOnlyPaths=/opt/ali-patch-code /etc/ali-patch-code',
                                 'StandardOutput=null', 'StandardError=null'):
                    self.assertIn(expected, unit)
                self.assertNotIn('EnvironmentFile', unit)
                self.assertEqual((directory / 'out' / 'Caddyfile').stat().st_mode & 0o777, 0o600)
                again = self.render(directory, version=version)
                self.assertNotEqual(again.returncode, 0, 'must refuse overwrite')

    def test_render_rejects_credentials_or_unsupported_version_without_leaking(self):
        cases = [('admin\nrespond hacked', BCRYPT, '2.8.4'),
                 ('@admin', BCRYPT, '2.8.4'),
                 ('admin', 'NOT-A-PASSWORD-HASH-SECRET', '2.8.4'),
                 ('admin', BCRYPT + '\nrespond hacked', '2.8.4'),
                 ('admin', BCRYPT, '2.4.5'), ('admin', BCRYPT, 'devel')]
        for user, value, version in cases:
            with self.subTest(user=user, version=version), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                result = self.render(Path(d), user=user, hash_value=value, version=version)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(value, result.stdout + result.stderr)
                self.assertFalse((Path(d) / 'out').exists())

    def make_source(self, directory):
        for relative in FIXED_FILES + PACKAGE_FILES:
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# fixture\n', encoding='utf-8')

    def test_source_allowlist_copies_only_permitted_files_recursively(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            source = directory / 'source'
            self.make_source(source)
            for relative in ['.env', 'README.md', '.ali_license_private_key',
                             '.github/workflows/patch7.yml', 'toyecc/cache.bin',
                             'web/license/secret.txt', 'web/license/README.md']:
                path = source / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('DO-NOT-COPY\n')
            destination = directory / 'app'
            result = run_renderer('copy-app', '--source', source, '--destination', destination)
            self.assertEqual(result.returncode, 0, result.stderr)
            copied = sorted(str(p.relative_to(destination))
                            for p in destination.rglob('*') if p.is_file())
            self.assertEqual(copied, sorted(FIXED_FILES + PACKAGE_FILES))
            for path in destination.rglob('*'):
                self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644)
            self.assertNotEqual(run_renderer('copy-app', '--source', source,
                                             '--destination', destination).returncode, 0)

    def test_copy_refuses_missing_files_and_symlinks_before_writing(self):
        for kind in ['missing', 'file-link', 'dir-link']:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                source = directory / 'source'
                self.make_source(source)
                if kind == 'missing':
                    (source / 'mikro.py').unlink()
                elif kind == 'file-link':
                    (source / 'mikro.py').unlink()
                    (source / 'mikro.py').symlink_to(source / 'license.py')
                else:
                    (source / 'toyecc' / 'escape').symlink_to(directory, target_is_directory=True)
                result = run_renderer('copy-app', '--source', source,
                                      '--destination', directory / 'out')
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((directory / 'out').exists())

    def test_source_check_refuses_unshipped_local_import_before_copying(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            source = directory / 'source'
            self.make_source(source)
            (source / 'mikro.py').write_text('from unshipped import Helper\n')
            (source / 'unshipped.py').write_text('class Helper: pass\n')
            result = run_renderer('copy-app', '--source', source,
                                  '--destination', directory / 'out')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unshipped.py', result.stderr)
            self.assertFalse((directory / 'out').exists())

    def test_source_check_refuses_omitted_package_module_before_any_copy(self):
        import contextlib
        import io
        module = load_renderer()
        imports = ('from scripts import license_util',
                   'from scripts.license_util import Helper',
                   'import scripts.license_util')
        for statement in imports:
            with self.subTest(statement=statement), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                source = directory / 'source'
                self.make_source(source)
                (source / 'scripts/license_server.py').write_text(statement + '\n')
                shipped = tuple(f for f in module.APP_FILES if f != 'scripts/license_util.py')
                with patch.object(module, 'APP_FILES', shipped):
                    errors = io.StringIO()
                    with contextlib.redirect_stderr(errors), self.assertRaises(SystemExit) as exit_info:
                        module.main(['check-source', '--source', str(source)])
                    self.assertEqual(exit_info.exception.code, 2)
                    self.assertIn('scripts/license_util.py', errors.getvalue())
                    with self.assertRaisesRegex(ValueError, 'scripts/license_util.py'):
                        module.copy_app(source, directory / 'out')
                    self.assertFalse((directory / 'out').exists())
        text = INSTALLER.read_text()
        self.assertLess(text.index('check-source --source'), text.index('apt-get update'))

    def test_source_check_accepts_nested_package_imports(self):
        # A proper nested package that IS allowlisted must be accepted.
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            source = directory / 'source'
            self.make_source(source)
            (source / 'scripts' / 'license_server.py').write_text(
                'from scripts import license_util\nimport toyecc.nested.one\n'
                'from toyecc.nested import one as sibling\nlicense_util.load()\n',
                encoding='utf-8')
            result = run_renderer('check-source', '--source', source)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_key_validation_accepts_hex_without_printing_and_rejects_unsafe_files(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            path = Path(d) / 'key'
            path.write_text('aa' * 32 + '\n', encoding='ascii')
            path.chmod(0o600)
            result = run_renderer('validate-key', path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '')
            for text in ('zz' * 32, '00' * 32, 'aa' * 31, 'aa' * 33, 'plaintext',
                         'aa' * 32 + '\n' + 'bb' * 32):
                path.write_text(text, encoding='ascii')
                result = run_renderer('validate-key', path)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(text, result.stdout + result.stderr)
            path.write_text('aa' * 32)
            path.chmod(0o644)
            self.assertNotEqual(run_renderer('validate-key', path).returncode, 0)
            path.chmod(0o600)
            link = Path(d) / 'link'
            link.symlink_to(path)
            self.assertNotEqual(run_renderer('validate-key', link).returncode, 0)

    def test_installer_syntax_and_fail_closed_cli(self):
        self.assertTrue(INSTALLER.is_file())
        result = subprocess.run(['bash', '-n', str(INSTALLER)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(run_installer('--help').returncode, 0)
        for arguments in [('--password', 'NOT-A-PASSWORD'), ('--domain',),
                          ('--unknown',), ('--render-only',),
                          ('--render-only', '--domain', 'x.com;id')]:
            result = run_installer(*arguments)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('NOT-A-PASSWORD', result.stdout + result.stderr)

    def test_installer_render_only_has_no_root_or_network_requirement(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            hash_file = directory / 'hash'
            hash_file.write_text(BCRYPT)
            arguments = ['--render-only', '--domain', 'panel.example.com',
                         '--admin-user', 'admin', '--password-hash-file', hash_file,
                         '--caddy-version', '2.6.2', '--output-dir', directory / 'out']
            result = run_installer(*arguments)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('basicauth', (directory / 'out' / 'Caddyfile').read_text())
            self.assertNotEqual(run_installer(*arguments).returncode, 0)

    def test_installer_ignores_poisoned_caller_path_before_external_commands(self):
        for mode in ('--help', '--render-only', '--check-config'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                fake = directory / 'bin'
                fake.mkdir()
                for name in ('dirname', 'python3', 'uname'):
                    program = fake / name
                    # Harmless probes only; no privileged installer path is used.
                    program.write_text('#!/bin/sh\n'
                        'printf "%s\\n" "' + name + '" >> "$POISON_MARKER"\n' +
                        ('exec /usr/bin/dirname "$@"\n' if name == 'dirname' else 'exit 87\n'))
                    program.chmod(0o755)
                marker = directory / 'poison-used'
                env = dict(os.environ, PATH=str(fake) + ':/usr/sbin:/usr/bin:/sbin:/bin',
                           POISON_MARKER=str(marker))
                args = [mode]
                if mode == '--render-only':
                    hash_file = directory / 'hash'
                    hash_file.write_text(BCRYPT)
                    args += ['--domain', 'panel.example.com', '--admin-user', 'admin',
                             '--password-hash-file', str(hash_file),
                             '--output-dir', str(directory / 'out')]
                elif mode == '--check-config':
                    # Fail before DNS even on a supported Linux test host.
                    args += ['--domain', 'panel.example.com', '--admin-user', 'admin',
                             '--private-key-file', str(directory / 'absent-key')]
                result = subprocess.run(['/bin/bash', str(INSTALLER), *args], env=env,
                                        capture_output=True, text=True, timeout=10)
                self.assertFalse(marker.exists(), 'caller PATH executable ran: ' +
                                 (marker.read_text() if marker.exists() else ''))
                if mode == '--check-config':
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                if mode == '--render-only':
                    self.assertTrue((directory / 'out' / 'Caddyfile').is_file())

    def test_installer_secret_handling_and_rollback_contract(self):
        text = INSTALLER.read_text()
        for required in ('set +x', 'set -Eeuo pipefail', '/dev/tty',
                         'read -rs', 'caddy hash-password', 'unset PASSWORD',
                         'caddy validate', 'systemctl daemon-reload',
                         'getent passwd', 'useradd', 'apt-get install',
                         'ss -H -ltn', 'policy-rc.d', 'BACKUP', 'trap',
                         'validate-key', 'check-source', 'dns-check',
                         'check-backend', 'check-public', 'copy-app',
                         '--check-config', '--render-only'):
            self.assertIn(required, text)
        for forbidden in ('| bash', 'git pull', '--plaintext', 'set -x',
                          'ufw allow', 'iptables ', 'netplan apply'):
            self.assertNotIn(forbidden, text)
        self.assertLess(text.index('refuse_existing\n'), text.index('apt-get install'))
        self.assertLess(text.index('check_ports\n'), text.index('apt-get install'))
        self.assertLess(text.index('caddy validate'), text.index('systemctl enable --now ali-patch-code'))

    def test_malformed_hash_never_echoes_non_ascii_secret_on_failure(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            secret = 'CONFIDENTIAL-' + '\N{LATIN SMALL LETTER E WITH ACUTE}'
            path = directory / 'hash'
            path.write_text(secret, encoding='utf-8')
            result = run_renderer('render', '--domain', 'panel.example.com',
                                  '--admin-user', 'admin', '--password-hash-file', path,
                                  '--output-dir', directory / 'out')
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('UnicodeDecodeError', result.stderr)
            self.assertNotIn(secret, result.stdout + result.stderr)
            self.assertFalse((directory / 'out').exists())

    def test_dns_preflight_rejects_missing_private_or_mixed_addresses(self):
        module = load_renderer()
        self.assertTrue(hasattr(module, 'check_dns'))
        with patch.object(module.socket, 'getaddrinfo', return_value=[
                (2, 1, 6, '', ('8.8.8.8', 443))]):
            self.assertEqual(module.check_dns('panel.example.com'), ['8.8.8.8'])
        for addresses in [[], ['127.0.0.1'], ['10.0.0.1'], ['::1'],
                          ['8.8.8.8', '192.168.1.1']]:
            with patch.object(module.socket, 'getaddrinfo', return_value=[
                    (2, 1, 6, '', (ip, 443)) for ip in addresses]):
                with self.assertRaises(ValueError):
                    module.check_dns('panel.example.com')

    def test_health_probes_enforce_domain_host_tls_and_auth_all_paths(self):
        module = load_renderer()
        self.assertTrue(hasattr(module, 'check_backend'))
        self.assertTrue(hasattr(module, 'check_public'))
        backend = Mock()
        response = backend.getresponse.return_value
        response.status = 200
        response.read.return_value = b'{"status":"ok"}'
        with patch.object(module.http.client, 'HTTPConnection', return_value=backend):
            module.check_backend('panel.example.com')
            backend.request.assert_called_with('GET', '/api/health',
                                                headers={'Host': 'panel.example.com'})
            response.read.return_value = b'{"status":"down"}'
            with self.assertRaises(ValueError):
                module.check_backend('panel.example.com')
        public = Mock()
        reply = public.getresponse.return_value
        reply.status = 401
        reply.getheader.return_value = 'Basic realm="restricted"'
        with patch.object(module.http.client, 'HTTPSConnection', return_value=public) as factory:
            module.check_public('panel.example.com')
            context = factory.call_args.kwargs['context']
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, module.ssl.CERT_REQUIRED)
            paths = [call.args[1] for call in public.request.call_args_list]
            self.assertEqual(set(paths), {'/', '/app.js', '/app.css', '/api/session',
                                         '/api/health', '/api/generate', '/not-found'})
            reply.status = 200
            with self.assertRaises(ValueError):
                module.check_public('panel.example.com')

    def test_shell_collision_refusal_does_not_modify_existing_file(self):
        self.assertTrue(INSTALLER.is_file())
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            path = Path(d) / 'existing'
            path.write_text('keep-me')
            result = subprocess.run(['bash', '-c',
                'source "$1"; refuse_paths "$2"', 'test', str(INSTALLER), str(path)],
                capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('pembaruan', result.stderr)
            self.assertEqual(path.read_text(), 'keep-me')

    def exercise_hash_prompt(self, directory, *, shell_options=(),
                             password=b'fixture-not-a-real-login', locale=None):
        import pty
        import select
        import termios
        import time
        fake = directory / 'bin'
        fake.mkdir()
        # Verify stdin/argv/environment; never record password bytes.
        program = fake / 'caddy'
        program.write_text('#!' + sys.executable + '\n'
            'import os,sys\n'
            'from pathlib import Path\n'
            'Path(__file__).resolve().parents[1].joinpath("caddy-called").write_text("called")\n'
            'assert sys.argv[1:] == ["hash-password", "--algorithm", "bcrypt"]\n'
            'assert not {"PASSWORD", "PASSWORD_CONFIRM"}.intersection(os.environ)\n'
            'value=sys.stdin.buffer.read()\n'
            'assert len(value) >= 17 and value.endswith(b"\\n")\n'
            'assert all(value[:-1] not in os.fsencode(item) for item in os.environ.values())\n'
            'print(' + repr(BCRYPT) + ')\n')
        program.chmod(0o755)
        pid, fd = pty.fork()
        if pid == 0:
            if locale:
                os.environ['LC_ALL'] = locale
            os.execv('/bin/bash', ['bash', *shell_options, '-c',
                'source "$1"; PATH="$3:$PATH"; umask 077; hash_admin_password "$2"; '
                '[[ ! ${PASSWORD+x} && ! ${PASSWORD_CONFIRM+x} ]]',
                'test', str(INSTALLER), str(directory / 'hash'), str(fake)])
        output = b''
        sent = 0
        status = None
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if select.select([fd], [], [], 0.05)[0]:
                    try:
                        chunk = os.read(fd, 8192)
                    except OSError:
                        chunk = b''
                    output += chunk
                    prompt = b'Password admin' if sent == 0 else b'Ulangi password'
                    if sent < 2 and prompt in output:
                        # Immediate paste: echo must already be off.
                        os.write(fd, password + b'\n')
                        sent += 1
                ended, status = os.waitpid(pid, os.WNOHANG)
                if ended:
                    break
                status = None
            else:
                self.fail('masked prompt did not complete within 10 seconds')
            echo_restored = bool(termios.tcgetattr(fd)[3] & termios.ECHO)
        finally:
            if status is None:
                os.kill(pid, 9)
                os.waitpid(pid, 0)
            os.close(fd)
        self.assertEqual(sent, 2)
        self.assertTrue(password not in output, 'synthetic password leaked to terminal')
        self.assertTrue(echo_restored, 'terminal echo was not restored')
        assert status is not None
        return os.waitstatus_to_exitcode(status)

    def test_hash_prompt_masks_password_and_uses_only_caddy_stdin(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            self.assertEqual(self.exercise_hash_prompt(directory), 0)
            self.assertEqual((directory / 'hash').read_text().strip(), BCRYPT)
            self.assertEqual((directory / 'hash').stat().st_mode & 0o777, 0o600)

    def test_hash_prompt_never_exports_password_with_caller_allexport(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            self.assertEqual(self.exercise_hash_prompt(directory, shell_options=('-a',)), 0,
                             'hash subprocess inherited password variables under bash -a')
            self.assertEqual((directory / 'hash').read_text().strip(), BCRYPT)

    def test_hash_prompt_enforces_bcrypt_byte_boundaries_in_utf8_locale(self):
        locales = subprocess.check_output(['/usr/bin/locale', '-a'],
                                          text=True, timeout=10).splitlines()
        utf8_locale = next((name for name in locales
                            if name.lower().replace('-', '').endswith('.utf8')), None)
        self.assertIsNotNone(utf8_locale, 'a UTF-8 locale is required for this regression')
        cases = [
            ('multibyte-73', ('é' * 36 + 'a').encode('utf-8'), False),
            ('multibyte-72', ('é' * 36).encode('utf-8'), True),
            ('multibyte-16', ('é' * 8).encode('utf-8'), True),
            ('multibyte-15', ('é' * 7 + 'a').encode('utf-8'), False),
            ('ascii-73', b'a' * 73, False), ('ascii-72', b'a' * 72, True),
            ('ascii-16', b'a' * 16, True), ('ascii-15', b'a' * 15, False),
        ]
        for label, password, accepted in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                code = self.exercise_hash_prompt(directory, password=password, locale=utf8_locale)
                self.assertEqual(code == 0, accepted, 'incorrect byte-length decision')
                self.assertEqual((directory / 'caddy-called').exists(), accepted,
                                 'rejection must occur before the hash subprocess')
                self.assertEqual((directory / 'hash').exists(), accepted)
                if accepted:
                    self.assertEqual((directory / 'hash').read_text().strip(), BCRYPT)

    def test_port_checks_fail_closed_before_package_install(self):
        self.assertTrue(INSTALLER.is_file())
        for kind in ('tcp', 'udp', 'error', 'free'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                program = Path(d) / 'ss'
                program.write_text('#!/bin/sh\n' + (
                    'exit 7\n' if kind == 'error' else
                    'case "$*" in *ltn*) printf "LISTEN conflict\\n";; esac\n' if kind == 'tcp' else
                    'case "$*" in *lun*) printf "UDP conflict\\n";; esac\n' if kind == 'udp' else
                    'exit 0\n'))
                program.chmod(0o755)
                result = subprocess.run(['/bin/bash', '-c',
                                         'source "$1"; PATH="$2:$PATH"; check_ports',
                                         'test', str(INSTALLER), d],
                                        capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode == 0, kind == 'free', result.stderr)

    def test_rollback_restores_caddy_and_preserves_failed_key_in_private_backup(self):
        # No live system paths or systemctl: replace shell commands, not the OS.
        self.assertTrue(INSTALLER.is_file())
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            stage = directory / 'stage'
            stage.mkdir()
            code = '''source "$1"
BACKUP=$2 STAGE=$3 TRANSACTION=1 CADDY_CHANGED=1 CADDY_INSTALLED=1
UNIT_CREATED=1 DROPIN_CREATED=1 APP_CREATED=0 KEYDIR_CREATED=0 POLICY_CREATED=0
systemctl() { local IFS=' '; printf '%s\\n' "systemctl $*" >> "$BACKUP/operations"; }
mv() { local IFS=' '; printf '%s\\n' "mv $*" >> "$BACKUP/operations"; }
cp() { local IFS=' '; printf '%s\\n' "cp $*" >> "$BACKUP/operations"; }
trap cleanup EXIT
exit 9
'''
            result = subprocess.run(['bash', '-c', code, 'test', str(INSTALLER),
                                     d, str(stage)], capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 9)
            operations = (directory / 'operations').read_text()
            self.assertIn('disable --now ali-patch-code', operations)
            self.assertIn('disable --now caddy', operations)
            self.assertIn('cp -a ' + d + '/caddy.before /etc/caddy', operations)
            self.assertIn('failed-ali-patch-code.service', operations)
            self.assertIn('daemon-reload', operations)
            self.assertFalse(stage.exists())

    def test_existing_other_service_units_are_refused(self):
        # A sourced, read-only preflight with predictable system inspection.
        # No native systemctl or package manager is executed on the test host.
        code = '''source "$1"
refuse_paths() { :; }
command() { return 1; }
getent() { return 1; }
dpkg-query() { return 1; }
systemctl() { [[ $# == 2 && $2 == caddy ]]; }
refuse_existing
'''
        result = subprocess.run(['bash', '-c', code, 'test', str(INSTALLER)],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('service', result.stderr)

    def test_existing_caddy_group_alone_is_refused_but_fresh_host_is_accepted(self):
        # Only the isolated caddy group exists; all other collisions are absent.
        code = '''source "$1"
GROUP_HIT=$2
refuse_paths() { :; }
command() { return 1; }
systemctl() { return 1; }
dpkg-query() { return 1; }
getent() { [[ $GROUP_HIT == 1 && $1 == group && $2 == caddy ]]; }
refuse_existing
'''
        for group_hit in ('1', '0'):
            with self.subTest(caddy_group=group_hit):
                result = subprocess.run(['/bin/bash', '-c', code, 'test',
                                         str(INSTALLER), group_hit],
                                        capture_output=True, text=True, timeout=10)
                if group_hit == '1':
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn('group Caddy', result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)

    def test_validation_cannot_start_caddy_before_backend_is_healthy(self):
        text = INSTALLER.read_text()
        self.assertLess(text.index('check-backend "$DOMAIN"'),
                        text.index('systemctl enable --now caddy'))
        self.assertIn('systemctl is-active --quiet caddy', text)
        self.assertIn('LimitCORE=0', RENDERER.read_text())

    def test_key_and_password_cannot_enter_core_dumps(self):
        text = INSTALLER.read_text()
        self.assertIn('ulimit -c 0', text)
        self.assertIn('LimitCORE=0', text)
        self.assertIn('LimitCORE=0', RENDERER.read_text())

    def test_service_can_read_venv_created_under_private_umask(self):
        text = INSTALLER.read_text()
        self.assertIn('chmod -R a+rX,go-w /opt/ali-patch-code', text)

    @unittest.skipUnless(os.environ.get('CADDY_TEST_BINARY'), 'optional real Caddy binary not selected')
    def test_real_caddy_validates_and_adapts_auth_before_proxy(self):
        import json
        binary = os.environ['CADDY_TEST_BINARY']
        version = subprocess.check_output([binary, 'version'], text=True).strip()
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            self.assertEqual(self.render(directory, version=version).returncode, 0)
            env = dict(os.environ, HOME=d, XDG_CONFIG_HOME=str(directory / 'config'),
                       XDG_DATA_HOME=str(directory / 'data'))
            config = str(directory / 'out' / 'Caddyfile')
            validated = subprocess.run([binary, 'validate', '--config', config,
                                        '--adapter', 'caddyfile'], env=env,
                                       capture_output=True, text=True, timeout=20)
            self.assertEqual(validated.returncode, 0, validated.stderr.replace(BCRYPT, '[HASH]'))
            adapted = subprocess.run([binary, 'adapt', '--config', config,
                                      '--adapter', 'caddyfile'], env=env,
                                     capture_output=True, text=True, timeout=20)
            self.assertEqual(adapted.returncode, 0)
            document = json.loads(adapted.stdout)
            handlers = []
            def walk(value):
                if isinstance(value, dict):
                    if 'handler' in value:
                        handlers.append(value['handler'])
                    if value.get('handler') == 'authentication':
                        self.assertNotIn('match', value)
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)
            walk(document)
            self.assertLess(handlers.index('authentication'), handlers.index('reverse_proxy'))
            self.assertIn('request_body', handlers)

    @unittest.skipUnless(os.environ.get('CADDY_TEST_BINARY'), 'optional real Caddy binary not selected')
    def test_real_caddy_auth_gates_all_routes_and_strips_upstream_credentials(self):
        import base64
        import http.client
        import http.server
        import socket
        import threading
        import time
        binary = os.environ['CADDY_TEST_BINARY']
        version = subprocess.check_output([binary, 'version'], text=True).strip()
        seen = []
        class Backend(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append(dict(self.headers))
                self.send_response(200)
                self.send_header('Content-Length', '2')
                self.end_headers()
                self.wfile.write(b'ok')
            do_POST = do_GET
            def log_message(self, format, *args):
                pass
        backend = http.server.HTTPServer(('127.0.0.1', 0), Backend)
        worker = threading.Thread(target=backend.serve_forever, daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
                directory = Path(d)
                hashed = subprocess.check_output([binary, 'hash-password', '--algorithm', 'bcrypt'],
                    input=b'fixture-not-a-real-login\n').decode().strip()
                self.assertEqual(self.render(directory, version=version, hash_value=hashed).returncode, 0)
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0))
                    port = sock.getsockname()[1]
                config = directory / 'out' / 'Caddyfile'
                # Local HTTP transport only: same auth/route/proxy, no ACME or public listener.
                value = config.read_text().replace('https://panel.example.com {',
                    f'http://panel.example.com:{port} {{\n    bind 127.0.0.1')
                value = value.replace('127.0.0.1:12760', f'127.0.0.1:{backend.server_port}')
                config.write_text(value)
                env = dict(os.environ, HOME=d, XDG_CONFIG_HOME=d + '/config', XDG_DATA_HOME=d + '/data')
                process = subprocess.Popen([binary, 'run', '--config', str(config), '--adapter', 'caddyfile'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
                def request(path, *, method='GET', auth=False, host='panel.example.com'):
                    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
                    headers = {'Host': host}
                    if auth:
                        headers['Authorization'] = 'Basic ' + base64.b64encode(
                            b'admin:fixture-not-a-real-login').decode()
                        headers['Forwarded'] = 'for=attacker;proto=https'
                    try:
                        conn.request(method, path, headers=headers)
                        response = conn.getresponse()
                        response.read()
                        return response.status
                    finally:
                        conn.close()
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            self.assertEqual(request('/'), 401)
                            break
                        except ConnectionError:
                            if time.monotonic() >= deadline:
                                self.fail('local Caddy did not start')
                            time.sleep(0.05)
                    for path in ('/', '/app.js', '/app.css', '/api/session', '/api/health', '/not-found'):
                        self.assertEqual(request(path), 401, path)
                    self.assertEqual(request('/api/generate', method='POST'), 401)
                    self.assertEqual(seen, [])
                    self.assertEqual(request('/', auth=True), 200)
                    self.assertEqual(seen[-1]['Host'], 'panel.example.com')
                    self.assertNotIn('Authorization', seen[-1])
                    self.assertNotIn('Forwarded', seen[-1])
                    self.assertEqual(request('/', auth=True, host='panel.example.com:444'), 421)
                finally:
                    process.terminate()
                    process.wait(timeout=10)
        finally:
            backend.shutdown()
            backend.server_close()
            worker.join(timeout=3)

    def test_readme_documents_lifecycle_and_does_not_claim_live_linux_verification(self):
        path = ROOT / 'deploy' / 'README.md'
        self.assertTrue(path.is_file())
        text = path.read_text()
        for required in ('DNS A/AAAA', '80', '443', 'Basic Auth', 'install-panel.sh',
                         'render_panel_config.py', 'rotasi', 'uninstall', 'pembaruan',
                         'Ubuntu 24.04', 'Ubuntu 22.04', 'Debian 12', 'belum',
                         'systemctl', '401', '--check-config', '--render-only'):
            self.assertIn(required, text)
        self.assertNotIn('CUSTOM_LICENSE_PRIVATE_KEY="', text)


class RealCheckoutIntegrationTests(unittest.TestCase):
    """The real checkout must survive the deploy allowlist end to end."""

    def test_real_checkout_passes_check_source(self):
        result = run_renderer('check-source', '--source', ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_copied_app_boots_and_answers_domain_health_probe(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as d:
            directory = Path(d)
            app = directory / 'app'
            copied = run_renderer('copy-app', '--source', ROOT, '--destination', app)
            self.assertEqual(copied.returncode, 0, copied.stderr)
            env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
            key_hex = subprocess.run(
                [sys.executable, '-c',
                 'import license; print(license.generate_kcdsa_keypair()[0].hex())'],
                cwd=app, capture_output=True, text=True, timeout=30, env=env)
            self.assertEqual(key_hex.returncode, 0, key_hex.stderr)
            self.assertRegex(key_hex.stdout, r'^[0-9a-f]{64}$')
            key_file = directory / 'key.hex'
            key_file.write_text(key_hex.stdout)
            import socket
            import time
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                port = sock.getsockname()[1]
            server = subprocess.Popen(
                [sys.executable, '-u', '-B', str(app / 'scripts' / 'license_server.py'),
                 '--private-key-file', str(key_file), '--port', str(port),
                 '--health-endpoint', '--allowed-origin', 'https://panel.example.com'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=app, env=env)
            try:
                deadline = time.monotonic() + 15
                while True:
                    self.assertIsNone(server.poll(), 'copied server exited before healthy')
                    try:
                        load_renderer().check_backend('panel.example.com', port)
                        break
                    except (ConnectionError, OSError, ValueError):
                        self.assertLess(time.monotonic(), deadline, 'copied server failed health probe')
                        time.sleep(0.05)
            finally:
                server.terminate()
                server.wait(timeout=10)
                server.stdout.close()
                server.stderr.close()


if __name__ == "__main__":
    unittest.main()
