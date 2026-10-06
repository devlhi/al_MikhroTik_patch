"""Synthetic offline CLI tests; no hardware/network or compatibility evidence."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sfp_link_report.py"
A = """name: sfp1
sfp-module-present: yes
sfp-vendor-name: SYNTHETIC
sfp-vendor-part-number: DEMO-A
sfp-wavelength: 1310nm
eeprom-checksum: good
sfp-tx-power: 0dBm
sfp-rx-power: -8dBm
"""
B = """name: sfp2
sfp-module-present: yes
sfp-wavelength: 1550nm
sfp-tx-power: -2dBm
sfp-rx-power: -5dBm
"""
ETHTOOL = """Identifier: 0x03 (SFP)
Vendor name: SYNTHETIC
Vendor PN: DEMO-B
Optical diagnostics support: Yes
Laser output power: 1.000 mW / 0.00 dBm
Receiver signal average optical power: 0.100 mW / -10.00 dBm
"""


class LinkReportCLI(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.a = Path(self.temp.name) / "a.txt"
        self.b = Path(self.temp.name) / "b.txt"
        self.a.write_text(A, encoding="utf-8")
        self.b.write_text(B, encoding="utf-8")

    def cli(self, *extra, confirmed=True):
        argv = [sys.executable, "-B", str(SCRIPT),
                "--a-input", str(self.a), "--a-format", "routeros",
                "--b-input", str(self.b), "--b-format", "routeros",
                "--a-captured-at", "2026-10-04T12:00:00Z",
                "--b-captured-at", "2026-10-04T12:00:05+00:00",
                "--max-skew-seconds", "5"]
        if confirmed:
            argv.append("--confirm-optical-pairing")
        return subprocess.run(argv + list(extra), capture_output=True, text=True, timeout=15)

    def report(self, *extra, confirmed=True):
        result = self.cli(*extra, confirmed=confirmed)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        return json.loads(result.stdout)

    def unavailable(self, result, indices=(0, 1), reason=None):
        for index in indices:
            direction = result["directions"][index]
            self.assertEqual(direction["status"], "unavailable")
            self.assertIsNone(direction["estimated_path_loss_db"])
            self.assertTrue(direction["reasons"])
            if reason:
                self.assertIn(reason, " ".join(direction["reasons"]))

    def invalid(self, *extra):
        result = self.cli(*extra)
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertIn("error:", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_routeros_zero_and_explicit_cross_endpoint_directions(self):
        result = self.report()
        self.assertEqual(result["endpoints"]["A"]["power_dbm"]["tx"], 0.0)
        self.assertEqual([d["estimated_path_loss_db"] for d in result["directions"]], [5.0, 6.0])
        self.assertEqual(result["directions"][0]["formula"], "A TX dBm - B RX dBm")
        self.assertEqual(result["directions"][1]["formula"], "B TX dBm - A RX dBm")
        self.assertEqual(result["directions"][0]["tx_endpoint"], "A")
        self.assertEqual(result["directions"][0]["rx_endpoint"], "B")

    def test_mixed_formats_preserve_sources(self):
        self.b.write_text(ETHTOOL, encoding="utf-8")
        result = self.report("--b-format", "ethtool", "--b-interface", "eth2")
        self.assertEqual(result["endpoints"]["A"]["source"], "routeros-monitor-text")
        self.assertEqual(result["endpoints"]["B"]["source"], "linux-ethtool-text")
        self.assertEqual(result["endpoints"]["B"]["interface"], "eth2")
        self.assertEqual([d["estimated_path_loss_db"] for d in result["directions"]], [10.0, 8.0])

    def test_two_ethtool_endpoints(self):
        self.a.write_text(ETHTOOL, encoding="utf-8")
        self.b.write_text(ETHTOOL, encoding="utf-8")
        result = self.report("--a-format", "ethtool", "--b-format", "ethtool")
        self.assertEqual([d["estimated_path_loss_db"] for d in result["directions"]], [10.0, 10.0])

    def test_pairing_confirmation_required(self):
        self.unavailable(self.report(confirmed=False), reason="pairing")

    def test_bidi_different_wavelengths_not_rejected_or_verified(self):
        result = self.report()
        self.assertTrue(result["optical_pairing_confirmed_by_user"])
        self.assertFalse(result["wavelength_pairing_verified"])
        self.assertEqual(result["directions"][0]["status"], "estimated")
        self.assertNotEqual(result["endpoints"]["A"]["module"]["wavelength_nm"],
                            result["endpoints"]["B"]["module"]["wavelength_nm"])

    def test_equal_wavelengths_do_not_imply_pairing(self):
        self.b.write_text(B.replace("1550", "1310"), encoding="utf-8")
        self.unavailable(self.report(confirmed=False), reason="pairing")

    def test_skew_boundary_inclusive(self):
        self.assertEqual(self.report()["capture_skew_seconds"], 5.0)
        self.unavailable(self.report("--max-skew-seconds", "4.999"), reason="skew")

    def test_negative_skew_is_absolute(self):
        self.unavailable(self.report("--b-captured-at", "2026-10-04T11:59:54Z"), reason="skew")

    def test_timezone_offsets_and_fractional_seconds(self):
        result = self.report("--a-captured-at", "2026-10-04T14:00:00.250+02:00",
                             "--b-captured-at", "2026-10-04T07:00:00.250-05:00",
                             "--max-skew-seconds", "0")
        self.assertEqual(result["capture_skew_seconds"], 0)
        self.assertEqual(result["directions"][0]["status"], "estimated")

    def test_known_stale_flags(self):
        for side in ("a", "b"):
            with self.subTest(side=side):
                self.unavailable(self.report(f"--{side}-stale"), reason="stale")

    def test_historical_pair_not_compared_to_wall_clock(self):
        result = self.report("--a-captured-at", "2000-01-01T00:00:00Z",
                             "--b-captured-at", "2000-01-01T00:00:00Z")
        self.assertEqual(result["directions"][0]["status"], "estimated")

    def test_negative_loss_warned_not_clamped(self):
        self.b.write_text(B.replace("-5dBm", "2dBm"), encoding="utf-8")
        direction = self.report()["directions"][0]
        self.assertEqual(direction["estimated_path_loss_db"], -2.0)
        self.assertEqual(direction["status"], "estimated")
        self.assertIn("negative", direction["warnings"][0])

    def test_zero_loss_valid(self):
        self.b.write_text(B.replace("-5dBm", "0dBm"), encoding="utf-8")
        direction = self.report()["directions"][0]
        self.assertEqual(direction["estimated_path_loss_db"], 0.0)
        self.assertEqual(direction["warnings"], [])

    def test_missing_power_only_blocks_affected_direction(self):
        self.a.write_text(A.replace("sfp-tx-power: 0dBm\n", ""), encoding="utf-8")
        result = self.report()
        self.unavailable(result, (0,), "A TX")
        self.assertEqual(result["directions"][1]["estimated_path_loss_db"], 6.0)

    def test_absent_module_ignores_cached_power(self):
        self.a.write_text(A.replace("present: yes", "present: no"), encoding="utf-8")
        result = self.report()
        self.unavailable(result, reason="module-absent")
        self.assertEqual(result["endpoints"]["A"]["power_dbm"], {"tx": None, "rx": None})

    def test_absent_dom(self):
        self.a.write_text("name: sfp1\nstatus: link-ok\n", encoding="utf-8")
        self.unavailable(self.report(), reason="not-reported")

    def test_unsupported_dom_ignores_ethtool_power(self):
        self.b.write_text(ETHTOOL.replace("support: Yes", "support: No"), encoding="utf-8")
        self.unavailable(self.report("--b-format", "ethtool"), reason="diagnostics-not-supported")

    def test_bad_or_unknown_checksum(self):
        for value in ("bad", "invalid", "unknown", ""):
            with self.subTest(checksum=value):
                self.a.write_text(A.replace("checksum: good", f"checksum: {value}"), encoding="utf-8")
                self.unavailable(self.report(), reason="checksum")

    def test_nonfinite_readings_unavailable(self):
        for value in ("NaNdBm", "infdBm", "-infdBm", "9" * 400 + "dBm"):
            with self.subTest(value=value[:20]):
                self.a.write_text(A.replace("0dBm", value), encoding="utf-8")
                self.unavailable(self.report(), (0,), "A TX")

    def test_units_dbm_for_power_db_for_difference(self):
        result = self.report()
        self.assertIn("power_dbm", result["endpoints"]["A"])
        self.assertIn("estimated_path_loss_db", result["directions"][0])
        self.assertNotIn("estimated_path_loss_dbm", result["directions"][0])
        for value in ("0dB", "1mW", "0"):
            self.a.write_text(A.replace("0dBm", value), encoding="utf-8")
            self.unavailable(self.report(), (0,))

    def test_inconsistent_ethtool_mw_dbm_unavailable(self):
        self.b.write_text(ETHTOOL.replace("0.100 mW", "1.000 mW"), encoding="utf-8")
        self.unavailable(self.report("--b-format", "ethtool"), (0,), "B RX")

    def test_ethtool_explicit_checksum_annotation(self):
        self.b.write_text(ETHTOOL + "EEPROM checksum: bad\n", encoding="utf-8")
        self.unavailable(self.report("--b-format", "ethtool"), reason="checksum")
        self.b.write_text(ETHTOOL + "EEPROM checksum: good\neeprom-checksum: bad\n", encoding="utf-8")
        self.invalid("--b-format", "ethtool")

    def test_symlink_parent_rejected(self):
        link = self.a.parent / "linked-directory"
        target = self.a.parent / "real-directory"
        target.mkdir()
        (target / "input.txt").write_text(A, encoding="utf-8")
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("host cannot create directory symlinks without additional privileges")
        self.invalid("--a-input", str(link / "input.txt"))

    def test_manual_nic_metadata_not_autodetected(self):
        result = self.report("--a-nic-model", "Synthetic NIC", "--a-driver", "manual-driver")
        self.assertEqual(result["endpoints"]["A"]["nic"], {
            "model": "Synthetic NIC", "driver": "manual-driver", "source": "user-supplied", "autodetected": False})
        self.assertIsNone(result["endpoints"]["B"]["nic"]["model"])
        self.assertIsNone(result["endpoints"]["B"]["nic"]["driver"])

    def test_private_fields_not_copied_and_claims_false(self):
        self.a.write_text(A + "sfp-vendor-serial: SECRET-SERIAL\nmac-address: 00:11:22:33:44:55\nlicense: SECRET-LICENSE\n", encoding="utf-8")
        self.b.write_text(ETHTOOL + "Vendor SN: SECRET-SN\nVendor OUI: 00:11:22\n", encoding="utf-8")
        result = self.report("--b-format", "ethtool")
        text = json.dumps(result)
        for secret in ("SECRET-SERIAL", "SECRET-LICENSE", "SECRET-SN", "00:11:22"):
            self.assertNotIn(secret, text)
        for item in (result, *result["endpoints"].values()):
            self.assertFalse(item["hardware_verified"])
            self.assertFalse(item["native_routeros_support"])
        self.assertNotIn(str(self.a), text)

    def test_invalid_timestamps(self):
        for value in ("2026-10-04", "2026-10-04T12:00:00", "2026-02-30T12:00:00Z",
                      "2026-10-04T12:00:00+25:00", "2026-10-04T12:00:00+00:99",
                      "2026-10-04T12:00:00-00:00", "20261004T120000Z", "garbage"):
            with self.subTest(value=value):
                self.invalid("--a-captured-at", value)

    def test_invalid_max_skew(self):
        for value in ("nan", "inf", "-1", "86401", "no", "1e999"):
            with self.subTest(value=value):
                self.invalid("--max-skew-seconds", value)

    def test_invalid_identity_labels(self):
        for value in ("", " ", "X" * 161, "bad\nlabel", "bad\x1blabel"):
            with self.subTest(value=value):
                self.invalid("--a-nic-model", value)

    def test_routeros_interface_mismatch(self):
        self.invalid("--a-interface", "different")

    def test_multilane_and_duplicate_schema_rejected(self):
        for text in (A + "sfp-type: QSFP+\n", A + "name: sfp2\n", A + "sfp-tx-power: 1dBm\n"):
            self.a.write_text(text, encoding="utf-8")
            self.invalid()

    def test_input_size_bound(self):
        self.a.write_bytes(b"x" * 262145)
        self.invalid()

    def test_binary_controls_empty_and_unrecognized_text(self):
        for raw in (b"\xff", b"name: sfp1\x00", b"", b"unrecognized text"):
            self.a.write_bytes(raw)
            self.invalid()

    def test_nonfile_and_missing_paths(self):
        self.invalid("--a-input", self.temp.name)
        self.invalid("--a-input", str(self.a.parent / "missing"))
        self.invalid("--a-input", "-")

    def test_symlink_rejected(self):
        link = self.a.parent / "link.txt"
        try:
            os.symlink(self.a, link)
        except (OSError, NotImplementedError):
            self.skipTest("host cannot create symlinks without additional privileges")
        self.invalid("--a-input", str(link))

    def test_unknown_flags_formats_and_abbreviations_rejected(self):
        self.invalid("--hardware-verified")
        self.invalid("--a-format", "json")
        self.invalid("--confirm-optical")

    def test_help_labels_offline_scope(self):
        result = self.cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("Offline", result.stdout)
        self.assertIn("firmware fix", result.stdout)


if __name__ == "__main__":
    unittest.main()
