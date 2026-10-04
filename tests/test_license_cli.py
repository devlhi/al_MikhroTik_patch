"""CLI tests use real signing in isolated copies, never deployment keys/firmware."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import license_util
import license as repo_license


def copy_lab_sources(target):
    """Only generator dependencies; intentionally do not copy workflow/key files."""
    for name in ('license.py', 'mikro.py', 'sha256.py'):
        shutil.copy2(ROOT / name, target / name)
    shutil.copytree(ROOT / 'toyecc', target / 'toyecc',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (target / 'scripts').mkdir()
    for name in ('license_util.py', 'license_server.py', 'license_cli.py'):
        source = ROOT / 'scripts' / name
        if source.is_file():
            shutil.copy2(source, target / 'scripts' / name)


class LicenseCLITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private, cls.public = repo_license.generate_kcdsa_keypair()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='license-cli-')
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.repo = self.base / 'lab repo & !'
        self.repo.mkdir()
        copy_lab_sources(self.repo)
        self.outside = self.base / 'outside'
        self.outside.mkdir()
        self.key_file = self.base / 'private fixture.hex'
        self.key_file.write_text(self.private.hex(), encoding='utf-8')
        self.output = self.outside / 'hasil lisensi café.txt'
        self.env = dict(os.environ)
        self.env.pop('ALI_LICENSE_PRIVATE_KEY', None)
        self.env.pop('PYTHONPATH', None)
        self.env['PYTHONIOENCODING'] = 'utf-8'
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'

    def run_cli(self, *args, stdin='', python_args=(), env=None):
        return subprocess.run(
            [sys.executable, '-B', *python_args,
             str(self.repo / 'scripts' / 'license_cli.py'), *args],
            input=stdin, capture_output=True, text=True, encoding='utf-8',
            env=self.env if env is None else env, cwd=self.outside, timeout=30)

    def flags(self, kind='chr', identifier='pjLQ21gHzfI', output=None):
        return ['--kind', kind, '--id', identifier,
                '--output', str(self.output if output is None else output),
                '--private-key-file', str(self.key_file)]

    def assert_safe(self, result):
        # Boolean assertions avoid printing material even when the test fails.
        text = result.stdout + result.stderr
        self.assertFalse(self.private.hex() in text, 'private material leaked')
        self.assertFalse('-----BEGIN MIKROTIK' in text, 'license material leaked')
        self.assertFalse('Traceback' in text, 'uncaught exception')

    def assert_license(self, path, kind, identifier, public=None):
        fields = license_util.parse(path.read_text(encoding='utf-8'),
                                    (public or self.public).hex())
        self.assertEqual(fields.get('License valid'), 'True')
        self.assertEqual(fields.get('kind'), kind)
        field = 'System ID' if kind == 'chr' else 'Software ID'
        self.assertEqual(fields.get(field), identifier)

    def test_chr_flags_sign_verify_save_outside_repo_cwd(self):
        result = self.run_cli(*self.flags())
        self.assertEqual(result.returncode, 0, 'CLI must generate a real file')
        self.assertTrue(self.output.is_file())
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.assert_safe(result)
        self.assertIn(str(self.output), result.stdout)
        self.assertIn('custom-lab-only', result.stdout)
        self.assertIn('bukan lisensi resmi MikroTik', result.stdout)
        self.assertEqual(list(self.outside.glob('.ali-license-*')), [], 'staging must be cleaned')

    def test_ros_flags_sign_verify_save(self):
        result = self.run_cli(*self.flags('ros', '4JZ2-H049'))
        self.assertEqual(result.returncode, 0, 'ROS is a separate signed payload')
        self.assert_license(self.output, 'ros', '4JZ2-H049')
        self.assert_safe(result)

    def test_interactive_chr_menu_uses_python_input_and_default_repo_output(self):
        (self.repo / '.ali_license_private_key').write_text(
            self.private.hex(), encoding='utf-8')
        result = self.run_cli(stdin='1\npjLQ21gHzfI\n\n')
        self.assertEqual(result.returncode, 0, 'interactive input must generate')
        self.assert_license(self.repo / 'ali-lab-license-chr.txt', 'chr', 'pjLQ21gHzfI')
        self.assert_safe(result)
        self.assertIn('CHR', result.stdout)
        self.assertIn('RouterOS', result.stdout)


    def test_wrong_payload_kind_is_rejected_before_save(self):
        # Fault injection at the generator boundary; parse/signatures are real.
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli, license_server
        wrong = license_util.generate_ros('4JZ2-H049', self.private.hex())
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_util, 'generate_chr', return_value=wrong), \
                patch.object(license_cli, 'REPO_ROOT', self.repo), \
                patch.object(license_server, 'REPO_ROOT', self.repo):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main(self.flags())
        self.assertNotEqual(rc, 0, 'a valid signature alone is not sufficient')
        self.assertFalse(self.output.exists())
        self.assert_safe(subprocess.CompletedProcess([], rc, stdout.getvalue(), stderr.getvalue()))
        self.assertIn('verifikasi', stderr.getvalue().lower())


    def test_existing_output_file_is_refused_not_overwritten(self):
        self.output.write_text('KEEP ME', encoding='utf-8')
        result = self.run_cli(*self.flags())
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(encoding='utf-8'), 'KEEP ME')
        self.assert_safe(result)
        self.assertIn('sudah ada', result.stderr + result.stdout)

    def test_dangling_output_symlink_is_refused_without_creating_target(self):
        target = self.outside / 'absent target.txt'
        self.assertFalse(target.exists())
        try:
            self.output.symlink_to(target)
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 1314):
                raise
            self.skipTest('Windows denied symlink creation (winerror %s)' % error.winerror)
        link_before = self.output.readlink()
        result = self.run_cli(*self.flags())
        with self.subTest(check='nonzero exit'):
            self.assertNotEqual(result.returncode, 0)
        with self.subTest(check='target remains absent'):
            self.assertFalse(target.exists(), 'dangling target must not be created')
        self.assertTrue(self.output.is_symlink(), 'output link must be preserved')
        self.assertEqual(self.output.readlink(), link_before)
        self.assert_safe(result)

    def test_existing_output_symlink_is_refused_with_target_preserved(self):
        target = self.outside / 'existing target.txt'
        target.write_text('KEEP ME', encoding='utf-8')
        try:
            self.output.symlink_to(target)
        except OSError as error:
            if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 1314):
                raise
            self.skipTest('Windows denied symlink creation (winerror %s)' % error.winerror)
        link_before = self.output.readlink()
        result = self.run_cli(*self.flags())
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.output.is_symlink(), 'output link must be preserved')
        self.assertEqual(target.read_text(encoding='utf-8'), 'KEEP ME')
        self.assert_safe(result)
        self.assertEqual(self.output.readlink(), link_before)


    def test_symlink_inserted_at_publication_does_not_create_target(self):
        """Inject a symlink at the single publication syscall; no open on output."""
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli, license_server
        target = self.outside / 'race target.txt'
        original_link = os.link
        injected = []

        def insert_link():
            try:
                self.output.symlink_to(target)
            except OSError as error:
                if os.name != 'nt' or getattr(error, 'winerror', None) not in (5, 1314):
                    raise
                self.skipTest('Windows denied symlink creation (winerror %s)' % error.winerror)
            injected.append(self.output.readlink())

        def racing_link(source, destination, *args, **kwargs):
            if Path(destination) == self.output:
                insert_link()
            return original_link(source, destination, *args, **kwargs)

        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_cli, 'REPO_ROOT', self.repo), \
                patch.object(license_server, 'REPO_ROOT', self.repo), \
                patch.object(os, 'link', side_effect=racing_link):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main(self.flags())
        self.assertEqual(len(injected), 1, 'must exercise the publication boundary')
        with self.subTest(check='nonzero exit'):
            self.assertNotEqual(rc, 0)
        with self.subTest(check='no race target'):
            self.assertFalse(target.exists(), 'race must not create another target')
        self.assertTrue(self.output.is_symlink())
        self.assertEqual(self.output.readlink(), injected[0])
        self.assert_safe(subprocess.CompletedProcess([], rc, stdout.getvalue(), stderr.getvalue()))
        self.assertEqual(list(self.outside.glob('.ali-license-*')), [], 'staging must be cleaned')

    def test_invalid_identifier_is_sanitized_and_never_writes(self):
        for bad in ('', 'pjLQ21gHzf#', '///////////',
                    'x & calc.exe', 'a$(reboot)b', 'c`d`e;f', 'g | h > i'):
            with self.subTest(case_length=len(bad)):
                result = self.run_cli(*self.flags(identifier=bad))
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists(), 'no file on invalid ID')
                self.assert_safe(result)
                if bad:
                    self.assertFalse(bad in result.stdout + result.stderr)


    def test_key_priority_explicit_file_then_environment_then_default_file(self):
        default_private, _ = repo_license.generate_kcdsa_keypair()
        (self.repo / '.ali_license_private_key').write_text(
            default_private.hex(), encoding='utf-8')
        env = dict(self.env, ALI_LICENSE_PRIVATE_KEY=self.private.hex())
        # Without an explicit file, env must beat the default repo file.
        result = self.run_cli(*self.flags()[:-2], env=env)
        self.assertEqual(result.returncode, 0)
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.output.unlink()
        # Explicit file must beat even an invalid environment value.
        result = self.run_cli(*self.flags(), env=dict(env, ALI_LICENSE_PRIVATE_KEY='INVALID'))
        self.assertEqual(result.returncode, 0)
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.assert_safe(result)


    def test_explicit_bad_key_file_never_falls_back_or_leaks_contents(self):
        env = dict(self.env, ALI_LICENSE_PRIVATE_KEY=self.private.hex())
        (self.repo / '.ali_license_private_key').write_text(self.private.hex(), encoding='utf-8')
        for content in (None, b'\xff', b'NOT_A_KEY_SECRET_MARKER', b'00' * 32):
            with self.subTest(case_type=type(content).__name__):
                self.key_file.unlink(missing_ok=True)
                if content is not None:
                    self.key_file.write_bytes(content)
                result = self.run_cli(*self.flags(), env=env)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
                self.assert_safe(result)
                self.assertFalse('NOT_A_KEY_SECRET_MARKER' in result.stdout + result.stderr)
                self.assertFalse(str(self.key_file) in result.stderr)
                self.assertIn('kunci', result.stderr.lower())


    def write_workflow(self, env):
        # JSON is valid YAML; only ephemeral synthetic key material is written.
        import json
        target = self.repo / '.github' / 'workflows' / 'patch7.yml'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'env': env}), encoding='utf-8')
        return target

    def test_workflow_pair_is_last_fallback_and_real_signature_verifies(self):
        self.write_workflow({'CUSTOM_LICENSE_PRIVATE_KEY': self.private.hex(),
                             'CUSTOM_LICENSE_PUBLIC_KEY': self.public.hex()})
        result = self.run_cli(*self.flags()[:-2])
        self.assertEqual(result.returncode, 0, 'workflow pair fallback must work')
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.assert_safe(result)


    def test_selected_key_must_match_workflow_public_when_present(self):
        other_private, other_public = repo_license.generate_kcdsa_keypair()
        self.write_workflow({'CUSTOM_LICENSE_PRIVATE_KEY': other_private.hex(),
                             'CUSTOM_LICENSE_PUBLIC_KEY': other_public.hex()})
        result = self.run_cli(*self.flags())
        self.assertNotEqual(result.returncode, 0, 'override must match workflow public')
        self.assertFalse(self.output.exists())
        self.assert_safe(result)
        self.assertIn('tidak cocok', result.stderr)
        self.assertFalse(other_private.hex() in result.stdout + result.stderr)


    def test_missing_optional_yaml_only_blocks_workflow_loading(self):
        # -S supplies a real interpreter without site packages (including YAML).
        result = self.run_cli(*self.flags(), python_args=('-S',))
        self.assertEqual(result.returncode, 0, 'explicit file does not need YAML')
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.output.unlink()
        env = dict(self.env, ALI_LICENSE_PRIVATE_KEY=self.private.hex())
        result = self.run_cli(*self.flags()[:-2], python_args=('-S',), env=env)
        self.assertEqual(result.returncode, 0, 'env without workflow does not need YAML')
        self.assert_license(self.output, 'chr', 'pjLQ21gHzfI')
        self.output.unlink()
        self.write_workflow({'CUSTOM_LICENSE_PRIVATE_KEY': self.private.hex(),
                             'CUSTOM_LICENSE_PUBLIC_KEY': self.public.hex()})
        for args in (self.flags(), self.flags()[:-2]):
            result = self.run_cli(*args, python_args=('-S',))
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.output.exists())
            self.assert_safe(result)
            self.assertIn('PyYAML', result.stderr)


    def test_missing_pair_config_fails_without_ambiguous_success(self):
        for args in (self.flags()[:-2],):
            with self.subTest(mode='no explicit key'):
                result = self.run_cli(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(self.output.exists())
                self.assert_safe(result)
                self.assertIn('kunci', result.stderr.lower())

    def test_output_write_failure_is_nonzero_without_traceback(self):
        # A regular-file parent reliably fails on POSIX and Windows alike.
        blocked = self.outside / 'not a directory'
        blocked.write_text('keep', encoding='utf-8')
        result = self.run_cli(*self.flags(output=blocked / 'x.txt'))
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((blocked / 'x.txt').exists())
        self.assert_safe(result)


    def test_interactive_eof_is_clean_nonzero_without_output(self):
        result = self.run_cli(stdin='')
        self.assertNotEqual(result.returncode, 0)
        self.assert_safe(result)
        self.assertFalse((self.repo / 'ali-lab-license-chr.txt').exists())
        self.assertIn('dibatalkan', result.stderr.lower())


    def test_interactive_menu_loop_retries_on_invalid_kind_choice(self):
        (self.repo / '.ali_license_private_key').write_text(
            self.private.hex(), encoding='utf-8')
        result = self.run_cli(stdin='9\nx\n1\npjLQ21gHzfI\n\n')
        self.assertEqual(result.returncode, 0, 'invalid choices must retry, not crash')
        self.assert_license(self.repo / 'ali-lab-license-chr.txt', 'chr', 'pjLQ21gHzfI')
        self.assert_safe(result)

    def test_interactive_existing_file_is_refused(self):
        target = self.repo / 'ali-lab-license-chr.txt'
        target.write_text('KEEP', encoding='utf-8')
        (self.repo / '.ali_license_private_key').write_text(
            self.private.hex(), encoding='utf-8')
        # Refuse even with additional input: there is no overwrite operation.
        for answer in ('n\n', ''):
            with self.subTest(answer=answer.strip() or 'EOF'):
                result = self.run_cli(stdin='1\npjLQ21gHzfI\n' + str(target) + '\n' + answer)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_text(encoding='utf-8'), 'KEEP')
                self.assert_safe(result)


    def test_keyboard_interrupt_exits_130_without_file(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli, license_server
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_cli, 'REPO_ROOT', self.repo), \
                patch.object(license_server, 'REPO_ROOT', self.repo), \
                patch('builtins.input', side_effect=KeyboardInterrupt):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main([])
        self.assertEqual(rc, 130)
        self.assertFalse((self.repo / 'ali-lab-license-chr.txt').exists())
        self.assertFalse('Traceback' in stderr.getvalue())
        self.assertIn('dibatalkan', stderr.getvalue().lower())


    def test_corrupt_generated_signature_is_not_saved_or_printed(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli, license_server
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_cli, 'REPO_ROOT', self.repo), \
                patch.object(license_server, 'REPO_ROOT', self.repo), \
                patch.object(license_util, 'generate_chr', return_value='CORRUPTED_SECRET'):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main(self.flags())
        self.assertNotEqual(rc, 0)
        self.assertFalse(self.output.exists())
        self.assertIn('verifikasi', stderr.getvalue().lower())
        self.assertFalse('CORRUPTED_SECRET' in stderr.getvalue() + stdout.getvalue())


    def test_malformed_workflow_is_sanitized_for_explicit_key(self):
        target = self.write_workflow({})
        target.write_text('env: [SECRET_YAML_MARKER}\n', encoding='utf-8')
        result = self.run_cli(*self.flags())
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assert_safe(result)
        self.assertFalse('SECRET_YAML_MARKER' in result.stdout + result.stderr)
        self.assertIn('YAML', result.stderr)


    def test_argument_errors_do_not_echo_raw_input(self):
        for args in (['--kind', 'SECRET_ARGUMENT_MARKER'],
                     ['--private-key', 'SECRET_ARGUMENT_MARKER']):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 2)
            self.assertFalse('SECRET_ARGUMENT_MARKER' in result.stdout + result.stderr)
            self.assert_safe(result)


    def test_partial_output_is_removed_on_write_error(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli, license_server
        original_open = Path.open
        def failing_open(path, mode='r', *args, **kwargs):
            stream = original_open(path, mode, *args, **kwargs)
            if mode == 'x' and path.name == 'license.tmp':
                class BrokenWriter:
                    def __enter__(self):
                        return self
                    def __exit__(self, *exc):
                        stream.close()
                    def write(self, text):
                        stream.write('partial fixture')
                        stream.flush()
                        raise OSError('SECRET_ERROR_MARKER')
                return BrokenWriter()
            return stream
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_cli, 'REPO_ROOT', self.repo), \
                patch.object(license_server, 'REPO_ROOT', self.repo), \
                patch.object(Path, 'open', failing_open):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main(self.flags())
        self.assertNotEqual(rc, 0)
        self.assertFalse(self.output.exists(), 'partial output must be removed')
        self.assertFalse('SECRET_ERROR_MARKER' in stdout.getvalue() + stderr.getvalue())
        self.assert_safe(subprocess.CompletedProcess([], rc, stdout.getvalue(), stderr.getvalue()))
        self.assertEqual(list(self.outside.glob('.ali-license-*')), [], 'partial staging must be cleaned')


    def test_unsupported_python_exits_with_official_install_hint(self):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from unittest.mock import patch
        from scripts import license_cli
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(license_cli.sys, 'version_info', (3, 9, 0)):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                rc = license_cli.main(['--help'])
        self.assertNotEqual(rc, 0)
        self.assertIn('3.10', stderr.getvalue())
        self.assertIn('python.org', stderr.getvalue())


    def test_workflow_fallback_rejects_mismatch_and_missing_pair(self):
        _, other_public = repo_license.generate_kcdsa_keypair()
        for config in ({}, {'CUSTOM_LICENSE_PRIVATE_KEY': self.private.hex()},
                       {'CUSTOM_LICENSE_PRIVATE_KEY': self.private.hex(),
                        'CUSTOM_LICENSE_PUBLIC_KEY': other_public.hex()}):
            self.write_workflow(config)
            result = self.run_cli(*self.flags()[:-2])
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.output.exists())
            self.assert_safe(result)

    def test_interactive_ros_uses_unicode_output_path(self):
        (self.repo / '.ali_license_private_key').write_text(self.private.hex(), encoding='utf-8')
        result = self.run_cli(stdin='2\n4JZ2-H049\n' + str(self.output) + '\n')
        self.assertEqual(result.returncode, 0)
        self.assert_license(self.output, 'ros', '4JZ2-H049')
        self.assert_safe(result)


    def test_interactive_invalid_output_path_is_sanitized(self):
        (self.repo / '.ali_license_private_key').write_text(self.private.hex(), encoding='utf-8')
        result = self.run_cli(stdin='1\npjLQ21gHzfI\nINVALID_PATH_SECRET\0bad\n')
        self.assertNotEqual(result.returncode, 0)
        self.assert_safe(result)
        self.assertFalse('INVALID_PATH_SECRET' in result.stdout + result.stderr)
        self.assertFalse((self.repo / 'ali-lab-license-chr.txt').exists())


if __name__ == '__main__':
    unittest.main()
