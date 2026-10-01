"""Exercise the release staging CLI with synthetic bytes, never firmware."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_assets.py"
VERSION = "7.23.3"


def expected_sources():
    names = [
        f"mikrotik-{VERSION}-patched.iso",
        f"routeros-{VERSION}-patched.npk",
        f"all_packages-{VERSION}-patched.zip",
        f"netinstall-{VERSION}-patched.zip",
        f"netinstall64-{VERSION}-patched.zip",
        f"netinstall-{VERSION}-patched.tar.gz",
    ]
    for image in ("chr", "install-image"):
        for fmt in ("img", "qcow2", "vmdk", "vhd", "vhdx", "vdi"):
            names.append(f"{image}-{VERSION}-patched.{fmt}.zip")
    return names


class ReleaseAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "build"
        self.source.mkdir()
        self.output = self.root / "dist"
        self.changelog = self.source / "CHANGELOG"
        self.changelog.write_text("Synthetic changelog for tests only.\n")
        self.payloads = {}
        for name in expected_sources():
            data = f"SYNTHETIC TEST FIXTURE, NOT FIRMWARE: {name}\n".encode()
            (self.source / name).write_bytes(data)
            self.payloads[name] = data

    def invoke(self, version=VERSION):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--source", str(self.source),
             "--output", str(self.output), "--version", version,
             "--changelog", str(self.changelog)],
            text=True, capture_output=True, timeout=15,
        )

    def test_rejects_existing_output_without_overwriting(self):
        self.output.mkdir()
        marker = self.output / "keep.txt"
        marker.write_text("keep")
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.output.iterdir()), [marker])
        self.assertEqual(marker.read_text(), "keep")

    def test_missing_asset_leaves_no_partial_release(self):
        (self.source / expected_sources()[-1]).unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists(), "Incomplete release must not be staged")

    def test_stages_all_x86_assets_with_brand_and_preserves_bytes(self):
        self.assertTrue(SCRIPT.is_file(), "Release staging CLI is not implemented")
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((self.output / "manifest.json").read_text())
        self.assertEqual(manifest["brand"], "Ali Patch Code")
        self.assertEqual(manifest["routeros_version"], VERSION)
        self.assertEqual(manifest["architecture"], "x86")
        self.assertEqual(manifest["boot_tested"], False)
        self.assertEqual(len(manifest["assets"]), len(self.payloads))
        checksums = (self.output / "SHA256SUMS").read_text().splitlines()
        for name, payload in self.payloads.items():
            branded = f"ali-patch-code-x86-{name}"
            self.assertEqual((self.output / branded).read_bytes(), payload)
            self.assertEqual((self.source / name).read_bytes(), payload)
            digest = hashlib.sha256(payload).hexdigest()
            self.assertIn(f"{digest}  {branded}", checksums)
            entry = next(a for a in manifest["assets"] if a["filename"] == branded)
            self.assertEqual(entry["sha256"], digest)
            self.assertEqual(entry["size"], len(payload))
        body = (self.output / "RELEASE_NOTES.md").read_text()
        self.assertIn("Ali Patch Code — RouterOS 7.23.3 — x86", body)
        self.assertIn("BELUM diuji boot", body)
        self.assertIn(self.changelog.read_text(), body)
        self.assertEqual(len(checksums), len(self.payloads))


if __name__ == "__main__":
    unittest.main()
