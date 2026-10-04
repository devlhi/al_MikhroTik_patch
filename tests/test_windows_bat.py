"""Tests for the root generate-license.bat Windows launcher.

Honest scope, split by what actually runs on each host:

- Text/structure checks run everywhere, but they NEVER execute the batch and
  never prove cmd.exe behaviour.
- Native execution tests run the real .bat through cmd.exe and are skipped
  with an explicit message on non-Windows hosts. They are the only tests that
  exercise cmd.exe. The parent workflow runs them on a Windows runner.
- No fake shell interpreter of the .bat is used anywhere.
- All key material is an ephemeral synthetic keypair generated per test run;
  sample identifiers pjLQ21gHzfI / 4JZ2-H049 are public repo fixtures.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / 'generate-license.bat'
NATIVE_CMD_REASON = ('native cmd.exe execution requires Windows; '
                     'this host ran only text checks')
# Directory name that stresses cmd quoting: space, ampersand, caret-food, '!'
HOSTILE_NAME = 'lab repo & !copy!'


def copy_lab_sources(target):
    """Generator dependencies only; no workflow files, no real keys."""
    import shutil
    for name in ('license.py', 'mikro.py', 'sha256.py'):
        shutil.copy2(ROOT / name, target / name)
    shutil.copytree(ROOT / 'toyecc', target / 'toyecc',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    (target / 'scripts').mkdir()
    for name in ('license_util.py', 'license_server.py', 'license_cli.py'):
        shutil.copy2(ROOT / 'scripts' / name, target / 'scripts' / name)
    (target / 'generate-license.bat').write_bytes(BAT.read_bytes())


class BatStructureTests(unittest.TestCase):
    """Text-only checks; these do not run cmd.exe."""

    def test_bat_is_ascii_with_crlf_lines(self):
        raw = BAT.read_bytes()
        text = raw.decode('ascii')  # raises if non-ASCII
        self.assertNotIn('\n', text.replace('\r\n', ''), 'bare LF found')
        self.assertGreaterEqual(text.count('\r\n'), 10, 'file must use CRLF lines')

    def test_required_safety_and_flow_lines_present(self):
        text = BAT.read_text(encoding='ascii')
        for required in (
                '@echo off',
                'setlocal DisableDelayedExpansion',
                'pushd "%~dp0"',
                'popd',
                'scripts\\license_cli.py',
                'ALI_LICENSE_NO_PAUSE',
                'python.org',
                'exit /b',
        ):
            with self.subTest(required=required):
                self.assertIn(required, text)
        self.assertIn(':cleanup\npopd', text, 'successful pushd paths share cleanup')
        self.assertGreaterEqual(text.count('pause'), 1)
        self.assertRegex(text, r'if not "%ALI_LICENSE_NO_PAUSE%"=="1" pause')

    def test_forbidden_constructs_absent(self):
        text = BAT.read_text(encoding='ascii')
        for forbidden, why in (
                ('%*', 'arbitrary argument forwarding'),
                ('set /p', 'interactive input must live in Python'),
                ('license_util.py', 'must call license_cli.py, not the library'),
                ('powershell', 'no PowerShell bridging'),
                ('CUSTOM_LICENSE_PRIVATE_KEY', 'no key names or values in batch'),
                ('ALI_LICENSE_PRIVATE_KEY', 'key must stay in file/env handled by Python'),
                ('CUSTOM_LICENSE_PUBLIC_KEY', 'no key names or values in batch'),
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)
        self.assertIsNone(re.search(r'[0-9a-fA-F]{64}', text), 'hardcoded key material')

    def test_no_delayed_expansion_variables(self):
        text = BAT.read_text(encoding='ascii')
        self.assertIsNone(re.search(r'![A-Za-z_]+!', text),
                          'delayed expansion is disabled and unused')


    def test_echo_statements_are_fixed_literals_only(self):
        # No expansion into echo: typed/generated material never passes cmd.
        text = BAT.read_text(encoding='ascii')
        for line in text.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith('echo') and stripped != '@echo off':
                self.assertNotIn('%', line, 'echo must not expand variables')


@unittest.skipUnless(sys.platform == 'win32', NATIVE_CMD_REASON)
class BatNativeCmdTests(unittest.TestCase):
    """Real cmd.exe execution of the real .bat; Windows hosts only."""

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(ROOT))
        import license as repo_license
        cls.private, cls.public = repo_license.generate_kcdsa_keypair()

    def setUp(self):
        from scripts import license_util
        self.util = license_util
        self.temp = tempfile.TemporaryDirectory(prefix='bat-native-')
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name) / HOSTILE_NAME  # spaces & ! in the path
        self.repo = base / 'repo'
        self.repo.mkdir(parents=True)
        copy_lab_sources(self.repo)
        (self.repo / '.ali_license_private_key').write_text(
            self.private.hex(), encoding='utf-8')
        self.env = dict(os.environ)
        self.env['ALI_LICENSE_NO_PAUSE'] = '1'
        self.env['PYTHONIOENCODING'] = 'utf-8'
        self.env['PYTHONDONTWRITEBYTECODE'] = '1'
        self.env.pop('ALI_LICENSE_PRIVATE_KEY', None)
        self.env.pop('PYTHONPATH', None)
        self.cwd = Path(self.temp.name) / 'elsewhere'
        self.cwd.mkdir()

    def make_venv(self):
        # Controlled interpreter: a real venv built from the running
        # interpreter; no licensing behaviour is simulated or faked.
        subprocess.run([sys.executable, '-m', 'venv', '--without-pip',
                        str(self.repo / 'venv')], check=True, timeout=120,
                       capture_output=True)

    def run_bat(self, stdin):
        # Extra quotes: cmd /c strips the outer pair, keeping & ! literal.
        cmd = os.environ.get('COMSPEC', str(Path(os.environ['SystemRoot']) / 'System32' / 'cmd.exe'))
        command = f'"{cmd}" /d /v:off /s /c ""{self.repo / "generate-license.bat"}""'
        return subprocess.run(
            command, shell=False,
            input=stdin, capture_output=True, text=True, encoding='utf-8',
            env=self.env, cwd=str(self.cwd), timeout=180)

    def test_double_click_menu_generates_verifiable_license_file(self):
        self.make_venv()
        result = self.run_bat('1\npjLQ21gHzfI\n\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.repo / 'ali-lab-license-chr.txt'
        self.assertTrue(output.is_file())
        fields = self.util.parse(output.read_text(encoding='utf-8'),
                                 self.public.hex())
        self.assertEqual(fields['kind'], 'chr')
        self.assertEqual(fields['System ID'], 'pjLQ21gHzfI')
        combined = result.stdout + result.stderr
        self.assertNotIn(self.private.hex(), combined)
        self.assertNotIn('-----BEGIN MIKROTIK', combined)
        self.assertNotIn('Traceback', combined)

    def test_ros_choice_generates_ros_license(self):
        self.make_venv()
        result = self.run_bat('2\n4JZ2-H049\n\n')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.repo / 'ali-lab-license-ros.txt'
        fields = self.util.parse(output.read_text(encoding='utf-8'),
                                 self.public.hex())
        self.assertEqual(fields['kind'], 'ros')
        self.assertEqual(fields['Software ID'], '4JZ2-H049')

    def test_invalid_identifier_exits_nonzero_and_writes_no_file(self):
        self.make_venv()
        result = self.run_bat('1\npjLQ21gHzf#\n\n')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.repo / 'ali-lab-license-chr.txt').exists())
        self.assertNotIn('Traceback', result.stdout + result.stderr)

    def test_missing_interpreter_reports_python_org_and_exits_nonzero(self):
        # No venv in this copy; a PATH without py/python forces the
        # missing-interpreter branch of the launcher itself.
        empty = Path(self.temp.name) / 'empty path'
        empty.mkdir()
        self.env['PATH'] = str(empty)
        result = self.run_bat('')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('python.org', result.stdout + result.stderr)
        self.assertFalse((self.repo / 'ali-lab-license-chr.txt').exists())


if __name__ == '__main__':
    unittest.main()
