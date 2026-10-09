"""TDD tests for scripts/license_util.py — custom lab licenses only.

All key material in these tests is generated fresh via the repo's
generate_kcdsa_keypair(); no real or workflow key values are embedded.
These licenses only work on patched "Ali Patch Code" lab firmware.
"""
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LicenseUtilTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo_license = load("repo_license_test", ROOT / "license.py")
        cls.util = load("license_util_test", ROOT / "scripts" / "license_util.py")
        # A fresh lab-style keypair per test run; never printed anywhere.
        cls.private_key, cls.public_key = cls.repo_license.generate_kcdsa_keypair()

    # --- happy path: generate then verify round-trip --------------------

    def test_generate_ros_round_trips_against_public_key(self):
        software_id = "4JZ2-H049"  # documented repo example
        lic = self.util.generate_ros(software_id, self.private_key.hex())
        self.assertIn("-----BEGIN MIKROTIK SOFTWARE KEY", lic)
        fields = self.util.parse(lic, self.public_key.hex())
        self.assertEqual(fields["kind"], "ros")
        self.assertIn(software_id, fields.get("Software ID", ""))
        self.assertEqual(fields.get("License valid"), "True")

    def test_generate_chr_round_trips_against_public_key(self):
        system_id = "pjLQ21gHzfI"  # documented repo example (case-sensitive)
        lic = self.util.generate_chr(system_id, self.private_key.hex())
        fields = self.util.parse(lic, self.public_key.hex())
        self.assertEqual(fields["kind"], "chr")
        self.assertIn(system_id, fields.get("System ID", ""))
        self.assertEqual(fields.get("License valid"), "True")

    def test_repeated_generation_preserves_id_and_signature_validity(self):
        # KCDSA uses a fresh random nonce; valid signatures need not be equal.
        software_id = "4JZ2-H049"
        first = self.util.parse(
            self.util.generate_ros(software_id, self.private_key.hex()),
            self.public_key.hex())
        second = self.util.parse(
            self.util.generate_ros(software_id, self.private_key.hex()),
            self.public_key.hex())
        for fields in (first, second):
            self.assertIn(software_id, fields["Software ID"])
            self.assertEqual(fields["License valid"], "True")

    # --- ROS feature nibble (byte 7 = feature bits << 4 | level) ----------

    def test_generate_ros_default_keeps_legacy_feature_byte(self):
        fields = self.util.parse(
            self.util.generate_ros("4JZ2-H049", self.private_key.hex()),
            self.public_key.hex())
        # Legacy community value 0x16: level 6 + feature bit 1 rendered by
        # RouterOS as "extra-channels" in the License Features field.
        self.assertEqual(fields.get("License Level"), "6")
        self.assertEqual(fields.get("Feature Bits"), "1")

    def test_generate_ros_feature_bits_zero_round_trips(self):
        lic = self.util.generate_ros(
            "4JZ2-H049", self.private_key.hex(), feature_bits=0)
        fields = self.util.parse(lic, self.public_key.hex())
        self.assertEqual(fields["kind"], "ros")
        self.assertIn("4JZ2-H049", fields.get("Software ID", ""))
        self.assertEqual(fields.get("License valid"), "True")
        self.assertEqual(fields.get("License Level"), "6")
        self.assertEqual(fields.get("Feature Bits"), "0")

    def test_generate_ros_rejects_invalid_feature_bits(self):
        for bad in (-1, 16, 1.5, "1", None, True):
            with self.subTest(bad=repr(bad)):
                with self.assertRaises(ValueError):
                    self.util.generate_ros(
                        "4JZ2-H049", self.private_key.hex(), feature_bits=bad)

    # --- identifier validation -------------------------------------------

    def test_generate_ros_rejects_malformed_software_id(self):
        for bad in ("", "1234", "4JZ2H049", "4JZ2-H04", "4jz2-h049",
                    "4JZ2-H04O", "AAAA-BBBB-CCCC", "X" * 200):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    self.util.generate_ros(bad, self.private_key.hex())
                self.assertIn("XXXX-XXXX", str(ctx.exception))

    def test_generate_chr_rejects_malformed_system_id(self):
        for bad in ("", "pjLQ21gHzf", "pjLQ21gHzfIxx", "pjLQ21gHzf#",
                    " " * 11, "X" * 200):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError) as ctx:
                    self.util.generate_chr(bad, self.private_key.hex())
                self.assertIn("11", str(ctx.exception))

    def test_generate_accepts_surrounding_whitespace(self):
        lic = self.util.generate_ros("  4JZ2-H049 \n", self.private_key.hex())
        fields = self.util.parse(lic, self.public_key.hex())
        self.assertIn("4JZ2-H049", fields.get("Software ID", ""))

    # --- key validation ---------------------------------------------------

    def test_generate_rejects_invalid_private_key(self):
        for bad in ("", "zz", "AB" * 31, "AB" * 33, "0" * 63, None, 12345):
            with self.subTest(bad=repr(bad)[:20]):
                with self.assertRaises(ValueError):
                    self.util.generate_ros("4JZ2-H049", bad)

    def test_generate_rejects_non_string_identifier(self):
        with self.assertRaises(ValueError):
            self.util.generate_ros(None, self.private_key.hex())
        with self.assertRaises(ValueError):
            self.util.generate_chr(12345, self.private_key.hex())

    # --- parse validation ---------------------------------------------------

    def test_parse_rejects_garbage_license(self):
        for bad in ("", "not a license", "-----BEGIN FAKE-----\nAAAA\n"
                    "-----END FAKE-----", "X" * 5000):
            with self.subTest(bad=bad[:16]):
                with self.assertRaises(ValueError):
                    self.util.parse(bad, self.public_key.hex())

    def test_parse_rejects_invalid_public_key(self):
        lic = self.util.generate_ros("4JZ2-H049", self.private_key.hex())
        for bad in ("", "nothex", "AB" * 31):
            with self.subTest(bad=bad[:8]):
                with self.assertRaises(ValueError):
                    self.util.parse(lic, bad)

    def test_parse_rejects_wrong_verification_key(self):
        other_private, _ = self.repo_license.generate_kcdsa_keypair()
        lic = self.util.generate_ros("4JZ2-H049", other_private.hex())
        with self.assertRaises(ValueError):
            self.util.parse(lic, self.public_key.hex())

    def test_parse_rejects_tampered_signature(self):
        import mikro
        lic = self.util.generate_ros("4JZ2-H049", self.private_key.hex())
        lines = lic.splitlines()
        raw = bytearray(mikro.mikro_base64_decode("".join(lines[1:-1])))
        raw[-1] ^= 1
        tampered = "\n".join((lines[0], mikro.mikro_base64_encode(bytes(raw), True), lines[-1]))
        with self.assertRaises(ValueError):
            self.util.parse(tampered, self.public_key.hex())

    def test_chr_rejects_base64_id_that_overflows_64_bits(self):
        with self.assertRaises(ValueError):
            self.util.generate_chr("///////////", self.private_key.hex())

    def test_invalid_scalar_is_rejected_before_vendor_signing(self):
        from unittest import mock
        import mikro
        order = mikro.getcurvebyname("Curve25519").n
        for value in (0, order):
            with self.subTest(value_is_zero=value == 0):
                with mock.patch.object(self.util.repo_license, "lic_gen_ros") as sign:
                    with self.assertRaises(ValueError):
                        self.util.generate_ros("4JZ2-H049", value.to_bytes(32, "little").hex())
                    sign.assert_not_called()

    # --- import hygiene ---------------------------------------------------

    def test_importing_util_does_not_run_cli_or_print(self):
        result = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r); "
             "import license_util" % (str(ROOT / "scripts"), str(ROOT))],
            text=True, capture_output=True, timeout=30,
            cwd=str(ROOT))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
