"""Real loopback HTTP tests with ephemeral lab keys; never firmware."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import license_util


class LicenseServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import license
        cls.private, cls.public = license.generate_kcdsa_keypair()

    def setUp(self):
        from scripts import license_server
        self.module = license_server
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.static = Path(self.temp.name)
        (self.static / 'index.html').write_text('<!doctype html><title>TEST FIXTURE</title>')
        (self.static / 'app.css').write_text('body { color: black; }')
        (self.static / 'app.js').write_text('"use strict";')
        self.server = license_server.create_server(
            self.private.hex(), port=0, static_dir=self.static, cooldown=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_port
        self.host = f'127.0.0.1:{self.port}'
        self.origin = 'http://' + self.host

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method='GET', path='/api/session', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request(method, path, body, headers or {})
            res = conn.getresponse()
            return res.status, dict(res.getheaders()), res.read()
        finally:
            conn.close()

    def session(self):
        status, headers, raw = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(headers.get('Cache-Control'), 'no-store')
        data = json.loads(raw)
        self.assertNotIn(self.private.hex(), raw.decode())
        return data

    def post(self, payload, extra=None):
        headers = {'Content-Type': 'application/json', 'Origin': self.origin,
                   'X-CSRF-Token': self.session()['csrf_token']}
        headers.update(extra or {})
        return self.request('POST', '/api/generate', json.dumps(payload), headers)

    def test_real_chr_generation_matches_requested_identifier_and_key(self):
        session = self.session()
        self.assertEqual(session['scope'], 'custom-lab-only')
        self.assertEqual(session['brand'], 'Ali Patch Code')
        self.assertRegex(session['key_fingerprint'], r'^[0-9a-f]{16}$')
        status, headers, raw = self.post({'kind': 'chr', 'identifier': 'pjLQ21gHzfI'})
        self.assertEqual(status, 200, raw)
        data = json.loads(raw)
        self.assertIs(data['verified'], True)
        self.assertEqual(data['identifier'], 'pjLQ21gHzfI')
        fields = license_util.parse(data['license'], self.public.hex())
        self.assertEqual(fields['System ID'], data['identifier'])
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn(self.private.hex(), raw.decode())

    def test_untrusted_host_cannot_read_session_or_sign(self):
        status, _, _ = self.request(headers={'Host': 'attacker.invalid'})
        self.assertEqual(status, 403)
        status, _, _ = self.post({'kind': 'ros', 'identifier': '4JZ2-H049'}, {
            'Host': 'attacker.invalid', 'Origin': 'http://attacker.invalid'})
        self.assertEqual(status, 403)

    def test_session_is_reusable_for_both_modes_on_one_page(self):
        token = self.session()['csrf_token']
        for kind, identifier in [('ros', '4JZ2-H049'), ('chr', 'pjLQ21gHzfI')]:
            status, _, raw = self.post({'kind': kind, 'identifier': identifier},
                                      {'X-CSRF-Token': token})
            self.assertEqual(status, 200, raw)
            data = json.loads(raw)
            self.assertEqual(data['kind'], kind)
            self.assertIs(data['verified'], True)

    def test_no_untrusted_origin_can_get_a_csrf_token(self):
        for origin in ('http://attacker.invalid', 'null'):
            with self.subTest(origin=origin):
                status, _, raw = self.request(headers={'Origin': origin})
                self.assertEqual(status, 403, raw)
        status, _, _ = self.request(headers={'Sec-Fetch-Site': 'cross-site'})
        self.assertEqual(status, 403)

    def test_invalid_request_never_exposes_key_and_does_not_poison_session(self):
        token = self.session()['csrf_token']
        for payload in (None, [], {}, {'kind': 'wrong', 'identifier': 'x'},
                        {'kind': 'ros', 'identifier': 7},
                        {'kind': 'ros', 'identifier': '4JZ2-H04O'},
                        {'kind': 'chr', 'identifier': '///////////'},
                        {'kind': 'chr', 'identifier': 'pjLQ21gHzfI', 'private_key': 'no'}):
            with self.subTest(payload=payload):
                status, _, raw = self.post(payload, {'X-CSRF-Token': token})
                self.assertEqual(status, 400, raw)
                self.assertNotIn(self.private.hex(), raw.decode())
                self.assertNotIn('Traceback', raw.decode())

    def test_cross_origin_and_missing_csrf_are_forbidden(self):
        for headers in ({'Origin': 'null'}, {'Origin': 'https://' + self.host},
                        {'Origin': 'http://attacker.invalid'},
                        {'X-CSRF-Token': ''}, {'X-CSRF-Token': 'invalid'}):
            with self.subTest(headers=headers):
                status, _, _ = self.post({'kind': 'ros', 'identifier': '4JZ2-H049'}, headers)
                self.assertEqual(status, 403)

    def test_only_allowlisted_static_paths_are_served(self):
        for path in ('/license.py', '/.github/workflows/patch7.yml',
                     '/../../README.md', '/%2e%2e/license.py', '/no-such-path'):
            with self.subTest(path=path):
                status, _, _ = self.request(path=path)
                self.assertEqual(status, 404)
        status, headers, raw = self.request(path='/')
        self.assertEqual(status, 200)
        self.assertIn(b'TEST FIXTURE', raw)
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)

    def test_early_rejections_close_connection_and_disallow_chunking(self):
        status, headers, _ = self.post({'kind': 'ros', 'identifier': '4JZ2-H049'},
                                      {'Content-Type': 'text/plain'})
        self.assertEqual(status, 415)
        self.assertEqual(headers.get('Connection'), 'close')
        status, _, _ = self.post({'kind': 'ros', 'identifier': '4JZ2-H049'},
                                {'Transfer-Encoding': 'chunked'})
        self.assertEqual(status, 400)

    def test_deep_or_duplicate_json_is_rejected(self):
        for body in ('[' * 1500 + '0' + ']' * 1500,
                     '{"kind":"ros","kind":"chr","identifier":"pjLQ21gHzfI"}'):
            with self.subTest(length=len(body)):
                status, _, raw = self.request('POST', '/api/generate', body, {
                    'Content-Type': 'application/json', 'Origin': self.origin,
                    'X-CSRF-Token': self.session()['csrf_token']})
                self.assertEqual(status, 400, raw)

    def test_missing_origin_is_rejected(self):
        status, _, raw = self.request('POST', '/api/generate',
            json.dumps({'kind': 'ros', 'identifier': '4JZ2-H049'}), {
                'Content-Type': 'application/json',
                'X-CSRF-Token': self.session()['csrf_token']})
        self.assertEqual(status, 403, raw)

    def test_oversized_body_wrong_types_and_transfer_headers_are_rejected(self):
        for body, extra, expected in [
            ('x' * 4097, {}, 413),
            ('{"kind": [], "identifier": "x"}', {}, 400),
            ('{"kind": null, "identifier": "x"}', {}, 400),
            ('{malformed', {}, 400),
            ('{"kind": "ros", "identifier": "x"}', {'Transfer-Encoding': 'chunked'}, 400),
        ]:
            with self.subTest(expected=expected, length=len(body)):
                headers = {'Origin': self.origin, 'Content-Type': 'application/json',
                           'X-CSRF-Token': self.session()['csrf_token']}
                headers.update(extra)
                status, _, raw = self.request('POST', '/api/generate', body, headers)
                self.assertEqual(status, expected, raw)
                self.assertNotIn(self.private.hex(), raw.decode())

    def test_cooldown_cannot_be_bypassed_by_new_session(self):
        self.server.RequestHandlerClass.state.cooldown = 60
        payload = {'kind': 'ros', 'identifier': '4JZ2-H049'}
        status, _, raw = self.post(payload)
        self.assertEqual(status, 200, raw)
        status, _, raw = self.post(payload)
        self.assertEqual(status, 429, raw)

    def test_invalid_key_and_non_loopback_bind_fail_before_listening(self):
        with self.assertRaises(ValueError):
            self.module.create_server(self.private.hex(), bind='0.0.0.0')
        for value in (None, '', 'nothex', '00' * 32):
            with self.subTest(value_is_none=value is None):
                with self.assertRaises(ValueError):
                    self.module.create_server(value)

    def test_workflow_key_loading_checks_matching_public_key(self):
        from unittest.mock import patch
        import yaml
        source = self.static / 'patch7.yml'
        config = {'env': {'CUSTOM_LICENSE_PRIVATE_KEY': self.private.hex(),
                          'CUSTOM_LICENSE_PUBLIC_KEY': self.public.hex()}}
        source.write_text(yaml.safe_dump(config))
        with patch.object(self.module, 'REPO_ROOT', self.static):
            (self.static / '.github' / 'workflows').mkdir(parents=True)
            target = self.static / '.github' / 'workflows' / 'patch7.yml'
            target.write_text(source.read_text())
            self.assertEqual(self.module._workflow_private_key(), self.private.hex())
            config['env']['CUSTOM_LICENSE_PUBLIC_KEY'] = '00' * 32
            target.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, 'tidak cocok'):
                self.module._workflow_private_key()

    def test_explicit_missing_key_file_never_falls_back_to_environment(self):
        from unittest.mock import patch
        from contextlib import redirect_stderr
        import io
        message = io.StringIO()
        with patch.dict('os.environ', {'ALI_LICENSE_PRIVATE_KEY': self.private.hex()}):
            with patch.object(self.module, 'create_server',
                              side_effect=AssertionError('Unexpected key fallback')):
                with redirect_stderr(message), self.assertRaises(SystemExit) as result:
                    self.module.main(['--private-key-file', str(self.static / 'missing.hex')])
        # The server must never be started with a different key source.
        self.assertEqual(result.exception.code, 2)
        self.assertNotIn(self.private.hex(), message.getvalue())
        self.assertNotIn('Traceback', message.getvalue())

    def test_malformed_workflow_error_never_includes_source_values(self):
        from unittest.mock import patch
        marker = 'TEST_SECRET_MUST_NOT_APPEAR'
        target = self.static / '.github' / 'workflows' / 'patch7.yml'
        target.parent.mkdir(parents=True)
        target.write_text('env: [' + marker + '}\n')
        with patch.object(self.module, 'REPO_ROOT', self.static):
            with self.assertRaises(ValueError) as error:
                self.module._workflow_private_key()
        self.assertNotIn(marker, str(error.exception))

    def test_local_key_file_is_git_ignored(self):
        import subprocess
        result = subprocess.run(
            ['git', 'check-ignore', '--no-index', '.ali_license_private_key'],
            cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, 'Local key file must not be tracked')

    def test_logs_do_not_include_request_paths_or_identifiers(self):
        from contextlib import redirect_stderr
        import io
        log = io.StringIO()
        with redirect_stderr(log):
            self.request(path='/api/session?private_key=TEST_DO_NOT_LOG')
        self.assertNotIn('TEST_DO_NOT_LOG', log.getvalue())


class ProxyModeTests(unittest.TestCase):
    """Mode origin domain untuk deployment reverse proxy (Caddy/HTTPS)."""

    ORIGIN = 'https://panel.example.com'

    @classmethod
    def setUpClass(cls):
        import license
        cls.private, cls.public = license.generate_kcdsa_keypair()

    def setUp(self):
        from scripts import license_server
        self.module = license_server
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        static = Path(self.temp.name)
        (static / 'index.html').write_text('<!doctype html><title>TEST FIXTURE</title>')
        (static / 'app.css').write_text('body { color: black; }')
        (static / 'app.js').write_text('"use strict";')
        self.server = license_server.create_server(
            self.private.hex(), port=0, static_dir=static, cooldown=0,
            allowed_origin=self.ORIGIN, health_endpoint=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.port = self.server.server_port

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method='GET', path='/api/session', body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=15)
        try:
            conn.request(method, path, body, headers or {})
            res = conn.getresponse()
            return res.status, dict(res.getheaders()), res.read()
        finally:
            conn.close()

    def make_server(self, **kwargs):
        kwargs.setdefault('port', 0)
        kwargs.setdefault('static_dir', Path(self.temp.name))
        kwargs.setdefault('cooldown', 0)
        return self.module.create_server(self.private.hex(), **kwargs)

    def test_rejects_invalid_allowed_origin_values(self):
        for value in (123, [], '', 'ftp://panel.example.com', 'http://panel.example.com',
                      'https://panel.example.com\n', 'https://panel.example.com/a/..',
                      'https://127.0.0.1', 'https://localhost', 'https://',
                      'https://user:pw@panel.example.com',
                      'https://panel.example.com/path', 'https://panel.example.com?q=1',
                      'https://panel.example.com#frag', 'https://[::1]',
                      'https://panel.example.com:port', 'https://panel.example.com:99999',
                      'https://panel.example.com:' + 'x' * 300):
            with self.subTest(value=value):
                server = None
                try:
                    with self.assertRaises(ValueError):
                        server = self.make_server(allowed_origin=value)
                finally:
                    if server is not None:
                        server.server_close()

    def test_allowed_origin_is_canonicalised(self):
        server = self.make_server(allowed_origin='HTTPS://Panel.Example.COM:443')
        try:
            self.assertEqual(server.RequestHandlerClass.state.allowed_origin,
                             'https://panel.example.com')
            self.assertIn('panel.example.com',
                          server.RequestHandlerClass.state.allowed_hosts)
        finally:
            server.server_close()

    def test_proxy_mode_allows_only_configured_domain_host(self):
        for host, expected in (('panel.example.com', 200),
                               ('panel.example.com:443', 200),
                               ('PANEL.EXAMPLE.COM', 200),
                               ('panel.example.com:8443', 403),
                               ('127.0.0.1:%d' % self.port, 403),
                               ('localhost:%d' % self.port, 403),
                               ('evil.example', 403)):
            with self.subTest(host=host):
                status, _, raw = self.request(headers={'Host': host})
                self.assertEqual(status, expected, raw)

    def test_proxy_mode_generate_requires_exact_https_origin(self):
        ok = {'Host': 'panel.example.com', 'Origin': self.ORIGIN,
              'Content-Type': 'application/json'}
        status, _, raw = self.request('GET', '/api/session', None,
                                      {'Host': 'panel.example.com'})
        token = json.loads(raw)['csrf_token']
        good = dict(ok, **{'X-CSRF-Token': token})
        status, _, raw = self.request('POST', '/api/generate',
                                      json.dumps({'kind': 'ros', 'identifier': '4JZ2-H049'}), good)
        self.assertEqual(status, 200, raw)
        self.assertIs(json.loads(raw)['verified'], True)
        for origin in ('https://evil.example', 'http://panel.example.com',
                       'https://panel.example.com.evil.example'):
            with self.subTest(origin=origin):
                status, _, _ = self.request('POST', '/api/generate',
                                            json.dumps({'kind': 'ros', 'identifier': '4JZ2-H049'}),
                                            dict(good, Origin=origin))
                self.assertEqual(status, 403)
        status, _, _ = self.request('POST', '/api/generate',
                                    json.dumps({'kind': 'ros', 'identifier': '4JZ2-H049'}),
                                    {k: v for k, v in good.items() if k != 'Origin'})
        self.assertEqual(status, 403)

    def test_health_endpoint_flag_gated_and_host_checked(self):
        status, _, raw = self.request(path='/api/health',
                                      headers={'Host': 'panel.example.com'})
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw), {'status': 'ok'})
        status, _, _ = self.request(path='/api/health',
                                    headers={'Host': 'evil.example'})
        self.assertEqual(status, 403)
        default = self.make_server()
        try:
            handler, thread = default.RequestHandlerClass, None
            thread = threading.Thread(target=default.serve_forever, daemon=True)
            thread.start()
            conn = http.client.HTTPConnection('127.0.0.1', default.server_port, timeout=15)
            try:
                conn.request('GET', '/api/health', None,
                             {'Host': '127.0.0.1:%d' % default.server_port})
                self.assertEqual(conn.getresponse().status, 404)
            finally:
                conn.close()
        finally:
            default.shutdown()
            default.server_close()


class VPSCLITests(unittest.TestCase):
    def test_startup_errors_exit_cleanly_without_key_contents(self):
        import os
        import subprocess
        import license
        private, _ = license.generate_kcdsa_keypair()
        marker = 'TEST_SECRET_DO_NOT_LOG'
        with tempfile.TemporaryDirectory() as tmp:
            key_file = Path(tmp) / 'private.hex'
            env = dict(os.environ)
            env.pop('ALI_LICENSE_PRIVATE_KEY', None)
            for extra, key in (
                ([], marker), ([], b'\xff'),
                (['--allowed-origin', 'http://panel.example.com'], private.hex()),
                (['--cooldown', 'nan'], private.hex()),
                (['--cooldown', '-1'], private.hex()),
                (['--port', '-1'], private.hex()),
                (['--port', '65536'], private.hex()),
            ):
                with self.subTest(extra=extra, key_type=type(key).__name__):
                    key_file.write_bytes(key if isinstance(key, bytes) else key.encode('ascii'))
                    result = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/license_server.py'),
                        '--private-key-file', str(key_file), *extra],
                        capture_output=True, text=True, timeout=8, env=env)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertEqual(result.stdout, '')
                    self.assertNotIn(marker, result.stderr)
                    self.assertNotIn(private.hex(), result.stderr)
                    self.assertNotIn('Traceback', result.stderr)

    def test_proxy_flags_are_passed_to_server(self):
        from scripts import license_server
        from unittest.mock import patch, MagicMock
        from contextlib import redirect_stdout
        import io
        import license
        private, _ = license.generate_kcdsa_keypair()
        fake = MagicMock()
        fake.server_port = 12760
        fake.serve_forever.side_effect = KeyboardInterrupt
        with patch.dict('os.environ', {'ALI_LICENSE_PRIVATE_KEY': private.hex()}):
            with patch.object(license_server, 'create_server', return_value=fake) as create:
                with redirect_stdout(io.StringIO()):
                    result = license_server.main(['--allowed-origin', 'https://panel.example.com',
                                                  '--health-endpoint'])
        self.assertEqual(result, 0)
        self.assertEqual(create.call_args.kwargs['allowed_origin'], 'https://panel.example.com')
        self.assertTrue(create.call_args.kwargs['health_endpoint'])
        fake.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
