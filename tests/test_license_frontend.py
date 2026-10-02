"""Offline contracts for the local lab license console (no signing keys)."""

from html.parser import HTMLParser
from pathlib import Path
import shutil
import subprocess
import unittest


# These are transport/DOM fixtures, not generated licenses or firmware checks.
# The parent task performs real-browser integration with the actual server.
NODE_HARNESS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Element {
  constructor() {
    this.listeners = {};
    this.attributes = {};
    this.dataset = {};
    this.value = '';
    this.textContent = '';
    this.disabled = false;
    this.hidden = false;
  }
  addEventListener(name, fn) { (this.listeners[name] ||= []).push(fn); }
  async emit(name) {
    for (const fn of this.listeners[name] || []) await fn({ preventDefault() {} });
  }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  removeAttribute(name) { delete this.attributes[name]; }
  focus() { this.focused = true; }
  select() { this.selected = true; }
  click() { this.clicked = true; }
  appendChild(child) { this.child = child; }
  removeChild(child) { child.removed = true; }
  remove() { this.removed = true; }
}
const ids = [...fs.readFileSync(process.argv[1].replace('app.js', 'index.html'), 'utf8')
  .matchAll(/id="([^"]+)"/g)].map(match => match[1]);
const nodes = Object.fromEntries(ids.map(id => [id, new Element()]));
const modes = [nodes['kind-chr'], nodes['kind-ros']];
modes[0].value = 'chr'; modes[0].checked = true;
modes[1].value = 'ros'; modes[1].checked = false;
for (const id of ['generate-button', 'copy-button', 'download-button']) nodes[id].disabled = true;
const select = selector => {
  if (selector.includes(':checked')) return modes.find(mode => mode.checked);
  if (selector.startsWith('#')) return nodes[selector.slice(1)];
  throw new Error('Unsupported test selector: ' + selector);
};
nodes['license-form'].querySelector = select;
nodes['license-form'].querySelectorAll = () => modes;
const document = {
  getElementById: id => nodes[id], querySelector: select,
  querySelectorAll: () => modes, body: new Element(),
  createElement: () => new Element()
};
const requests = [];
const timers = [];
const navigator = {};
const objectUrls = [];
const URL = {
  createObjectURL: blob => { objectUrls.push({ blob, revoked: false }); return 'blob:fixture'; },
  revokeObjectURL: url => { objectUrls.at(-1).revoked = true; }
};
vm.runInNewContext(fs.readFileSync(process.argv[1], 'utf8'), {
  document, navigator, URL, Blob, AbortController, console,
  setTimeout: (fn, delay) => { timers.push({ fn, delay }); return timers.length; },
  clearTimeout: () => {},
  fetch: (url, options) => new Promise((resolve, reject) => {
    requests.push({ url, options, resolve, reject });
  })
});
const settle = () => new Promise(resolve => setImmediate(resolve));
const answer = async (request, data, status = 200) => {
  request.resolve({ ok: status >= 200 && status < 300, status, json: async () => data });
  await settle();
};
const sessionFixture = {
  csrf_token: 'test-only-session-token', key_fingerprint: 'test-only-public-fingerprint',
  brand: 'Ali Patch Code', scope: 'custom-lab-only'
};
const makeReady = async () => answer(requests[0], sessionFixture);
const input = async value => { nodes.identifier.value = value; await nodes.identifier.emit('input'); };
const switchMode = async kind => {
  for (const mode of modes) mode.checked = mode.value === kind;
  await nodes['kind-' + kind].emit('change');
};
const submit = () => nodes['license-form'].emit('submit');
"""


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "license"


class Document(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))

    def by_id(self, identifier):
        return next(attrs for _, attrs in self.elements if attrs.get("id") == identifier)


class LicenseFrontendContracts(unittest.TestCase):
    def run_javascript(self, checks):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node is required for the offline DOM/transport contract checks")
        script = NODE_HARNESS + "\n(async () => {\n" + checks + "\n})().catch(error => { console.error(error); process.exitCode = 1; });"
        result = subprocess.run(
            [node, "-e", script, str(FRONTEND / "app.js")],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_session_must_be_ready_before_generation(self):
        self.run_javascript(r"""
assert.equal(requests.length, 1, 'The console must request its local session');
assert.equal(requests[0].url, '/api/session');
assert.equal(requests[0].options.method, 'GET');
assert.equal(requests[0].options.cache, 'no-store');
await input('AbCdEf12+/X');
assert.equal(nodes['generate-button'].disabled, true);
await makeReady();
assert.equal(nodes['key-fingerprint'].textContent, sessionFixture.key_fingerprint);
assert.equal(nodes['session-status'].dataset.state, 'ready');
assert.equal(nodes['generate-button'].disabled, false);
assert.equal(nodes['session-retry'].hidden, true);
assert.equal(nodes['copy-button'].disabled, true);
assert.equal(nodes['download-button'].disabled, true);
""")

    def test_chr_request_preserves_case_and_displays_verified_current_result(self):
        self.run_javascript(r"""
await makeReady();
await input(' \tAbCdEf12+/X \n');
const completed = submit();
assert.equal(requests.length, 2, 'Submitting must call the local generator');
const request = requests[1];
assert.equal(request.url, '/api/generate');
assert.equal(request.options.method, 'POST');
assert.equal(request.options.headers['X-CSRF-Token'], sessionFixture.csrf_token);
assert.equal(request.options.headers['Content-Type'], 'application/json');
assert.equal(request.options.headers.Origin, undefined);
assert.equal(request.options.cache, 'no-store');
assert.deepEqual(JSON.parse(request.options.body), { kind: 'chr', identifier: 'AbCdEf12+/X' });
assert.equal(nodes['result-panel'].attributes['aria-busy'], 'true');
assert.equal(nodes['generate-button'].disabled, true);
assert.equal(nodes['license-output'].value, '');
const fixture = '<b>TRANSPORT FIXTURE ONLY</b>';
await answer(request, {
  kind: 'chr', identifier: 'AbCdEf12+/X', license: fixture,
  verified: true, scope: 'custom-lab-only'
});
await completed;
assert.equal(nodes['license-output'].value, fixture);
assert.equal(nodes['result-identifier'].textContent, 'AbCdEf12+/X');
assert.equal(nodes['result-panel'].dataset.state, 'success');
assert.equal(nodes['result-panel'].attributes['aria-busy'], 'false');
assert.equal(nodes['copy-button'].disabled, false);
assert.equal(nodes['download-button'].disabled, false);
assert.equal(nodes['generate-button'].disabled, false);
""")

    def test_changes_cancel_inflight_response_and_cannot_restore_old_result(self):
        self.run_javascript(r"""
await makeReady();
await input('AbCdEf12+/X');
await submit();
const oldRequest = requests[1];
await input('X/CdEf12+/A');
assert.equal(oldRequest.options.signal.aborted, true);
await input('AbCdEf12+/X');
await answer(oldRequest, { kind: 'chr', identifier: 'AbCdEf12+/X',
  license: 'STALE TRANSPORT FIXTURE', verified: true, scope: 'custom-lab-only' });
assert.equal(nodes['license-output'].value, '');
assert.equal(nodes['copy-button'].disabled, true);
assert.equal(nodes['download-button'].disabled, true);
await submit();
assert.equal(nodes['result-panel'].dataset.state, 'loading');
const currentRequest = requests[2];
await switchMode('ros');
assert.equal(currentRequest.options.signal.aborted, true);
await answer(currentRequest, { kind: 'chr', identifier: 'AbCdEf12+/X',
  license: 'STALE TRANSPORT FIXTURE', verified: true, scope: 'custom-lab-only' });
assert.equal(nodes['license-output'].value, '');
assert.equal(nodes['result-panel'].attributes['aria-busy'], 'false');
""")

    def test_failed_generation_clears_previous_result_and_403_requires_session_retry(self):
        self.run_javascript(r"""
await makeReady();
await input('AbCdEf12+/X');
for (const status of [400, 413, 415, 429, 500, 403]) {
  await submit();
  await answer(requests.at(-1), { kind: 'chr', identifier: 'AbCdEf12+/X',
    license: 'TRANSPORT FIXTURE ONLY', verified: true, scope: 'custom-lab-only' });
  assert.equal(nodes['copy-button'].disabled, false);
  await submit();
  assert.equal(nodes['license-output'].value, '');
  assert.equal(nodes['copy-button'].disabled, true);
  const error = '<img src=x> Permintaan ditolak ' + status;
  await answer(requests.at(-1), { error }, status);
  assert.equal(nodes['operation-status'].dataset.state, 'error');
  assert.ok(nodes['operation-status'].textContent.includes(error));
  assert.equal(nodes['result-panel'].dataset.state, 'error');
  assert.equal(nodes['license-output'].value, '');
  assert.equal(nodes['download-button'].disabled, true);
}
assert.equal(nodes['session-retry'].hidden, false);
assert.equal(nodes['generate-button'].disabled, true);
assert.equal(requests.filter(request => request.url === '/api/session').length, 1,
  'A rejected session is retried explicitly, not silently');
const retried = nodes['session-retry'].emit('click');
await answer(requests.at(-1), sessionFixture);
await retried;
assert.equal(nodes['generate-button'].disabled, false);
""")

    def test_network_failure_keeps_output_empty_and_allows_retry(self):
        self.run_javascript(r"""
await makeReady();
await input('AbCdEf12+/X');
await submit();
requests[1].reject(new Error('test-only simulated offline transport'));
await settle();
assert.equal(nodes['license-output'].value, '');
assert.equal(nodes['copy-button'].disabled, true);
assert.equal(nodes['download-button'].disabled, true);
assert.equal(nodes['generate-button'].disabled, false);
assert.equal(nodes['result-panel'].dataset.state, 'error');
assert.equal(nodes['result-panel'].attributes['aria-busy'], 'false');
assert.ok(nodes['operation-status'].textContent.includes('Server lokal tidak dapat dihubungi'));
""")

    def test_copy_uses_clipboard_and_ignores_stale_async_feedback(self):
        self.run_javascript(r"""
await makeReady();
await input('AbCdEf12+/X');
await submit();
await answer(requests[1], { kind: 'chr', identifier: 'AbCdEf12+/X',
  license: 'TRANSPORT FIXTURE ONLY', verified: true, scope: 'custom-lab-only' });
let copied;
navigator.clipboard = { writeText: async text => { copied = text; } };
await nodes['copy-button'].emit('click');
await settle();
assert.equal(copied, 'TRANSPORT FIXTURE ONLY');
assert.equal(nodes['export-status'].textContent, 'Lisensi tersalin ke clipboard.');
let rejectCopy;
navigator.clipboard = { writeText: () => new Promise((resolve, reject) => { rejectCopy = reject; }) };
const copying = nodes['copy-button'].emit('click');
await input('X/CdEf12+/A');
rejectCopy(new Error('test-only clipboard rejection'));
await copying;
await settle();
assert.equal(nodes['license-output'].value, '');
assert.notEqual(nodes['license-output'].selected, true, 'Stale clipboard failure must not select a different result');
assert.ok(!nodes['export-status'].textContent.includes('diseleksi'));
""")

    def test_download_uses_safe_filename_and_releases_object_url_after_dispatch(self):
        self.run_javascript(r"""
await makeReady();
await switchMode('ros');
await input(' A1B2-C3D4 ');
await submit();
assert.deepEqual(JSON.parse(requests[1].options.body), { kind: 'ros', identifier: 'A1B2-C3D4' });
await answer(requests[1], { kind: 'ros', identifier: 'A1B2-C3D4',
  license: 'TRANSPORT FIXTURE ONLY', verified: true, scope: 'custom-lab-only' });
await nodes['download-button'].emit('click');
const link = document.body.child;
assert.equal(link.download, 'ali-patch-code-ros-license.txt');
assert.equal(link.clicked, true);
assert.equal(link.removed, true);
assert.equal(await objectUrls[0].blob.text(), 'TRANSPORT FIXTURE ONLY');
assert.equal(objectUrls[0].revoked, false, 'The browser needs time to consume the Blob URL');
for (const timer of timers) timer.fn();
assert.equal(objectUrls[0].revoked, true);
assert.ok(nodes['export-status'].textContent.includes('dikirim ke browser'),
  'The frontend cannot claim that the user saved the file');
""")

    def test_validation_blocks_invalid_ids_and_duplicate_inflight_submit(self):
        self.run_javascript(r"""
await makeReady();
for (const invalid of ['', 'AbCdEf12+/X=', 'Ab CdEf12/X', 'ABCDEF1234', 'ABCDEF123456', 'éBCDEFGHIJK']) {
  await input(invalid);
  assert.equal(nodes['generate-button'].disabled, true);
  await submit();
  assert.equal(requests.length, 1);
}
await switchMode('ros');
assert.equal(nodes['identifier-label'].textContent, 'RouterOS Software ID');
for (const invalid of ['ABCD1234', 'ABCD--1234', 'ABC-1234', 'ABC_-1234', 'ABCD 1234']) {
  await input(invalid);
  await submit();
  assert.equal(requests.length, 1);
  assert.equal(nodes.identifier.attributes['aria-invalid'], 'true');
}
await input('ABCD-EF12');
assert.equal(nodes['generate-button'].disabled, false);
await submit();
assert.deepEqual(JSON.parse(requests[1].options.body), { kind: 'ros', identifier: 'ABCD-EF12' });
await submit();
assert.equal(requests.length, 2, 'A disabled pending form must not post twice on Enter');
""")

    def test_malformed_or_unverified_success_never_enables_export(self):
        self.run_javascript(r"""
await makeReady();
await input('AbCdEf12+/X');
const goodShape = { kind: 'chr', identifier: 'AbCdEf12+/X',
  license: 'TRANSPORT FIXTURE ONLY', verified: true, scope: 'custom-lab-only' };
for (const payload of [null, {}, { ...goodShape, verified: 'true' },
  { ...goodShape, verified: false }, { ...goodShape, kind: 'ros' },
  { ...goodShape, identifier: 'abcdefghijk' }, { ...goodShape, scope: 'official' },
  { ...goodShape, license: '' }, { ...goodShape, license: ' \n\t' }]) {
  await submit();
  await answer(requests.at(-1), payload);
  assert.equal(nodes['license-output'].value, '');
  assert.equal(nodes['copy-button'].disabled, true);
  assert.equal(nodes['download-button'].disabled, true);
  assert.equal(nodes['result-panel'].dataset.state, 'error');
}
""")

    def test_regeneration_removes_verified_export_feedback_and_reset_restores_chr(self):
        self.run_javascript(r"""
await makeReady();
await switchMode('ros');
await input('A1B2-C3D4');
await submit();
await answer(requests[1], { kind: 'ros', identifier: 'A1B2-C3D4',
  license: 'TRANSPORT FIXTURE ONLY', verified: true, scope: 'custom-lab-only' });
await submit();
assert.equal(nodes['export-status'].textContent,
  'Salin dan unduh tersedia hanya untuk hasil yang terverifikasi.');
await nodes['reset-button'].emit('click');
assert.equal(requests[2].options.signal.aborted, true);
assert.equal(nodes.identifier.value, '');
assert.equal(nodes['kind-chr'].checked, true);
assert.equal(nodes['identifier-label'].textContent, 'CHR System ID');
assert.equal(nodes['license-output'].value, '');
assert.equal(nodes['result-panel'].dataset.state, 'empty');
assert.equal(nodes['copy-button'].disabled, true);
assert.equal(nodes['download-button'].disabled, true);
assert.equal(nodes.identifier.focused, true);
""")

    def test_ros_rejects_lowercase_and_letter_o(self):
        self.run_javascript(r"""
await makeReady();
await switchMode('ros');
for (const invalid of ['abcd-Ef12', 'A1B2-C3d4', 'O1B2-C3D4', 'A1B2-C3O4']) {
  await input(invalid);
  assert.equal(nodes['generate-button'].disabled, true, invalid + ' must be rejected');
  await submit();
  assert.equal(requests.length, 1, invalid + ' must not be posted');
}
await input('A1B2-C3D4');
assert.equal(nodes['generate-button'].disabled, false);
assert.ok(nodes['identifier-hint'].textContent.includes('huruf besar'),
  'The hint must state the uppercase-only table');
assert.ok(nodes['identifier-hint'].textContent.includes('O'),
  'The hint must state that the letter O is excluded');
""")

    def test_accessible_console_starts_empty_with_disabled_export(self):
        path = FRONTEND / "index.html"
        self.assertTrue(path.is_file(), "The accessible console document is missing")
        source = path.read_text(encoding="utf-8")
        dom = Document(source)
        self.assertIn(('html', {"lang": "id"}), dom.elements)
        self.assertIn("Ali Patch Code", source)
        self.assertIn("Local lab license console", source)
        self.assertIn("Target RouterOS", source)
        self.assertIn("7.24.4", source)
        self.assertIn("Kompatibilitas RouterOS 7.24.4 belum diuji boot.", source)
        self.assertIn("bukan lisensi resmi MikroTik", source)
        self.assertIn(("link", {"rel": "stylesheet", "href": "/app.css"}), dom.elements)
        scripts = [attrs for tag, attrs in dom.elements if tag == "script"]
        self.assertEqual(scripts, [{"src": "/app.js", "defer": None}])
        self.assertFalse(any(tag == "style" for tag, _ in dom.elements))
        self.assertFalse(any("style" in attrs for _, attrs in dom.elements))
        self.assertFalse(any(name.startswith("on") for _, attrs in dom.elements for name in attrs))
        self.assertFalse(any(attrs.get("type") == "password" for _, attrs in dom.elements))
        modes = [attrs for tag, attrs in dom.elements if tag == "input" and attrs.get("name") == "kind"]
        self.assertEqual({attrs["value"] for attrs in modes}, {"chr", "ros"})
        self.assertIn("checked", next(attrs for attrs in modes if attrs["value"] == "chr"))
        labels = {attrs.get("for") for tag, attrs in dom.elements if tag == "label"}
        self.assertTrue({"identifier", "license-output", "kind-chr", "kind-ros"} <= labels)
        identifier = dom.by_id("identifier")
        self.assertEqual(identifier["autocomplete"], "off")
        self.assertEqual(identifier["autocapitalize"], "none")
        self.assertEqual(identifier["spellcheck"], "false")
        self.assertIn("readonly", dom.by_id("license-output"))
        self.assertIn("disabled", dom.by_id("copy-button"))
        self.assertIn("disabled", dom.by_id("download-button"))
        self.assertIn("disabled", dom.by_id("generate-button"))
        self.assertEqual(dom.by_id("operation-status")["aria-live"], "polite")
        self.assertEqual(dom.by_id("session-status")["aria-live"], "polite")
        self.assertTrue(any(tag == "noscript" for tag, _ in dom.elements))
        css_path = FRONTEND / "app.css"
        self.assertTrue(css_path.is_file(), "The offline responsive stylesheet is missing")
        css = css_path.read_text(encoding="utf-8")
        self.assertIn("grid-template-columns:", css)
        self.assertIn("@media", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("44px", css)
        self.assertIn("Arial", css)
        self.assertNotIn("gradient", css.lower())
        self.assertNotIn("@import", css)
        self.assertNotIn("https://", source + css)
        self.assertNotIn("http://", source + css)


if __name__ == "__main__":
    unittest.main()
