"""Diagnostic fixtures are synthetic, never hardware-compatibility evidence."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sfp_diagnostics.py"


def load_module():
    if not SCRIPT.is_file():
        raise AssertionError("Read-only SFP diagnostics implementation does not exist yet")
    spec = importlib.util.spec_from_file_location("sfp_diagnostics", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RouterOSTests(unittest.TestCase):
    def test_single_port_preserves_zero_dbm_and_omits_serial(self):
        module = load_module()
        result = module.parse_routeros("""name: ether1
status: link-ok
sfp-module-present: yes
sfp-vendor-name: SYNTHETIC VENDOR
sfp-vendor-part-number: DEMO-NOT-HARDWARE
sfp-vendor-serial: PRIVATE-SERIAL
sfp-tx-power: 0dBm
sfp-rx-power: -18.25dBm
sfp-temperature: 42C
sfp-supply-voltage: 3.30V
""")
        self.assertEqual(result["source"], "routeros-monitor-text")
        self.assertEqual(result["status"], "power-reported")
        self.assertEqual(result["interface"], "ether1")
        self.assertEqual(result["power_dbm"], {"tx": 0.0, "rx": -18.25})
        self.assertEqual(result["sensors"], {"temperature_c": 42.0, "voltage_v": 3.30})
        self.assertNotIn("PRIVATE-SERIAL", str(result))
        self.assertFalse(result["hardware_verified"])
        self.assertFalse(result["routeros_support_verified"])

    def test_missing_data_never_becomes_zero_or_unsupported_hardware(self):
        module = load_module()
        for body in ("name: ether1\nstatus: link-ok", "name: ether1\nsfp-rx-power: N/A"):
            with self.subTest(body=body):
                result = module.parse_routeros(body)
                self.assertEqual(result["status"], "not-reported")
                self.assertEqual(result["power_dbm"], {"tx": None, "rx": None})
                self.assertTrue(result["warnings"])

    def test_partial_reading_does_not_invent_other_direction(self):
        result = load_module().parse_routeros("name: ether2\nsfp-rx-power: -9.2 dBm")
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["power_dbm"], {"tx": None, "rx": -9.2})
        self.assertEqual(result["sensors"], {})

    def test_routeros_requires_one_nonempty_port_name(self):
        for body in ("sfp-tx-power: 1dBm\nsfp-rx-power: -2dBm",
                     "name: \nsfp-tx-power: 1dBm\nsfp-rx-power: -2dBm"):
            with self.subTest(body=body):
                with self.assertRaisesRegex(ValueError, "name"):
                    load_module().parse_routeros(body)

    def test_routeros_interface_label_must_match_port_name(self):
        module = load_module()
        body = "name: ether1\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm"
        self.assertEqual(module.parse_routeros(body, interface="ether1")["interface"], "ether1")
        with self.assertRaisesRegex(ValueError, "cocok"):
            module.parse_routeros(body, interface="ether2")

    def test_absent_module_does_not_show_stale_power(self):
        result = load_module().parse_routeros(
            "name: ether1\nsfp-module-present: no\nsfp-rx-power: -10dBm\nsfp-tx-power: 2dBm")
        self.assertEqual(result["status"], "module-absent")
        self.assertEqual(result["power_dbm"], {"tx": None, "rx": None})

    def test_invalid_or_ambiguous_units_are_not_measurements(self):
        for value in ("NaNdBm", "infdBm", "-infdBm", "-4", "10W", "1dBm junk", "-1,-2dBm"):
            with self.subTest(value=value):
                result = load_module().parse_routeros(f"name: ether1\nsfp-rx-power: {value}")
                self.assertIsNone(result["power_dbm"]["rx"])
                self.assertTrue(result["warnings"])

    def test_rejects_multiple_ports_instead_of_merging(self):
        with self.assertRaisesRegex(ValueError, "satu port"):
            load_module().parse_routeros("name: ether1\nsfp-rx-power: -10dBm\nname: ether2\nsfp-tx-power: 1dBm")

    def test_rejects_duplicate_measurement_instead_of_last_wins(self):
        with self.assertRaisesRegex(ValueError, "duplikat"):
            load_module().parse_routeros("name: ether1\nsfp-rx-power: -10dBm\nsfp-rx-power: -20dBm")

    def test_rejects_unrecognized_empty_oversized_and_control_text(self):
        for body in ("", "arbitrary log line", "x" * 262145, "name: eth\x1b[31m"):
            with self.subTest(length=len(body)):
                with self.assertRaises(ValueError):
                    load_module().parse_routeros(body)

    def test_vendor_is_metadata_not_a_compatibility_allowlist(self):
        for vendor in ("Intel", "Broadcom", "MikroTik", "FS", "Cisco", "Unknown vendor"):
            with self.subTest(vendor=vendor):
                result = load_module().parse_routeros(
                    f"name: ether1\nsfp-vendor-name: {vendor}\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")
                self.assertEqual(result["module"]["vendor"], vendor)
                self.assertEqual(result["status"], "power-reported")
                self.assertFalse(result["routeros_support_verified"])

    def test_invalid_present_sensors_produce_field_warnings(self):
        for key in ("sfp-temperature", "sfp-supply-voltage", "sfp-tx-bias-current"):
            for bad_value in ("N/A", "", "NaN", "12wrongunit"):
                with self.subTest(key=key, value=bad_value):
                    result = load_module().parse_routeros(
                        f"name: e1\n{key}: {bad_value}\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")
                    self.assertEqual(result["sensors"], {})
                    self.assertTrue(any(key in message for message in result["warnings"]))
                    self.assertEqual(result["status"], "power-reported")
                    if bad_value:
                        self.assertNotIn(bad_value, " ".join(result["warnings"]))

    def test_routeros_multilane_type_is_explicitly_out_of_scope(self):
        for module_type in ("QSFP28", "QSFP+", "SFP-DD", "OSFP"):
            with self.subTest(module_type=module_type):
                with self.assertRaisesRegex(ValueError, "lane"):
                    load_module().parse_routeros(
                        f"name: e1\nsfp-type: {module_type}\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")

        with self.assertRaisesRegex(ValueError, "lane"):
            load_module().parse_routeros(
                "name: qsfp1\nsfp-type: QSFP28\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")

    def test_dsfp_dual_lane_identifier_rejected_in_both_formats(self):
        module = load_module()
        for module_type in ("DSFP", "dsfp"):
            for parser, body in (
                (module.parse_routeros, f"name: ether1\nsfp-type: {module_type}\nsfp-tx-power: 0dBm"),
                (module.parse_ethtool, f"Identifier : 0x1b ({module_type})\nLaser output power : 1 mW / 0 dBm"),
            ):
                with self.subTest(parser=parser.__name__, module_type=module_type):
                    with self.assertRaisesRegex(ValueError, "lane"):
                        parser(body)

    def test_single_lane_sfp56_is_not_rejected_as_multilane(self):
        module = load_module()
        ros = module.parse_routeros(
            "name: ether1\nsfp-type: SFP56\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")
        linux = module.parse_ethtool(
            "Identifier : 0x03 (SFP56)\nLaser output power : 1 mW / 0 dBm")
        self.assertEqual(ros["power_dbm"]["tx"], 0.0)
        self.assertEqual(linux["power_dbm"]["tx"], 0.0)
        self.assertFalse(ros["hardware_verified"])
        self.assertFalse(linux["hardware_verified"])

    def test_ambiguous_missing_unit_is_visible_in_warnings(self):
        result = load_module().parse_routeros("name: ether1\nsfp-rx-power: -2")
        self.assertIsNone(result["power_dbm"]["rx"])
        self.assertIn("dBm", " ".join(result["warnings"]))


class EthtoolTests(unittest.TestCase):
    def test_decoded_single_lane_ethtool_output(self):
        module = load_module()
        self.assertTrue(hasattr(module, "parse_ethtool"), "ethtool parser missing")
        result = module.parse_ethtool("""Identifier : 0x03 (SFP)
Vendor name : SYNTHETIC
Vendor PN : DEMO-SFP
Vendor SN : PRIVATE-SERIAL
Optical diagnostics support : Yes
Laser output power : 1.0000 mW / 0.00 dBm
Receiver signal average optical power : 0.0100 mW / -20.00 dBm
Module temperature : 38.00 degrees C / 100.40 degrees F
Module voltage : 3.3000 V
Laser bias current : 4.000 mA
Laser output power high alarm threshold : 10.00 mW / 10.00 dBm
""")
        self.assertEqual(result["source"], "linux-ethtool-text")
        self.assertEqual(result["power_dbm"], {"tx": 0.0, "rx": -20.0})
        self.assertEqual(result["sensors"], {"temperature_c": 38.0, "voltage_v": 3.3, "bias_ma": 4.0})
        self.assertEqual(result["module"]["vendor"], "SYNTHETIC")
        self.assertNotIn("PRIVATE-SERIAL", str(result))
        self.assertFalse(result["routeros_support_verified"])

    def test_interface_label_validation_rejects_controls_types_and_size(self):
        module = load_module()
        for parser, body in (
            (module.parse_ethtool, "Identifier : 0x03 (SFP)"),
            (module.parse_routeros, "name: ether1"),
        ):
            for label in (123, [], "eth\nSECRET", "eth\x1b[31m", "e" * 256):
                with self.subTest(parser=parser.__name__, label=repr(label)):
                    with self.assertRaisesRegex(ValueError, "label interface"):
                        parser(body, interface=label)
            report = parser(body, interface="   ")
            self.assertEqual(report["interface"], "ether1" if parser == module.parse_routeros else None)

    def test_interface_labels_require_unicode_scalars_without_line_separators(self):
        module = load_module()
        for parser, body in (
            (module.parse_ethtool, "Identifier : 0x03 (SFP)"),
            (module.parse_routeros, "name: ether1"),
        ):
            for label in ("eth\udcffSECRET", "eth\ud800SECRET", "eth\ud83d\ude00",
                          "eth\u0085SECRET", "eth\u2028SECRET", "eth\u2029SECRET"):
                with self.subTest(parser=parser.__name__, label=repr(label)):
                    with self.assertRaisesRegex(ValueError, "label interface") as caught:
                        parser(body, interface=label)
                    self.assertNotIn("SECRET", str(caught.exception))
        for label in ("é" * 127 + "a", "😀" * 63 + "abc"):
            with self.subTest(valid_label=label):
                self.assertEqual(len(label.encode("utf-8")), 255)
                for parser, body in (
                    (module.parse_ethtool, "Identifier : 0x03 (SFP)"),
                    (module.parse_routeros, "name: " + label),
                ):
                    self.assertEqual(parser(body, interface=label)["interface"], label)
                    with self.assertRaisesRegex(ValueError, "label interface"):
                        parser(body, interface=label + "a")

    def test_interface_label_is_optional_passthrough(self):
        module = load_module()
        body = "Identifier : 0x03 (SFP)\nVendor name : DEMO"
        self.assertIsNone(module.parse_ethtool(body)["interface"])
        self.assertEqual(module.parse_ethtool(body, interface="enp1s0")["interface"], "enp1s0")
        self.assertIsNone(module.parse_ethtool(body, interface="")["interface"])

    def test_identification_only_is_not_reported_not_zero(self):
        result = load_module().parse_ethtool("Identifier : 0x03 (SFP)\nVendor name : DEMO")
        self.assertEqual(result["status"], "not-reported")
        self.assertEqual(result["power_dbm"], {"tx": None, "rx": None})
        self.assertTrue(result["warnings"])

    def test_no_diagnostics_ignores_conflicting_stale_power(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nOptical diagnostics support : No\nLaser output power : 1 mW / 0 dBm")
        self.assertEqual(result["status"], "diagnostics-not-supported")
        self.assertIsNone(result["power_dbm"]["tx"])

    def test_rejects_multilane_snapshot_instead_of_averaging(self):
        with self.assertRaisesRegex(ValueError, "lane"):
            load_module().parse_ethtool(
                "Identifier : 0x11 (QSFP28)\nLaser output power (Channel 1) : 1 mW / 0 dBm")

    def test_invalid_sensor_is_omitted_not_null_and_controls_rejected(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nModule voltage : NaN V\nLaser output power : 1 mW / 0 dBm")
        self.assertNotIn("voltage_v", result["sensors"])
        with self.assertRaises(ValueError):
            load_module().parse_ethtool("Identifier : 0x03 (SFP)\nVendor name : BAD\x1b[31m")

    def test_rejects_duplicate_snapshot(self):
        with self.assertRaisesRegex(ValueError, "duplikat"):
            load_module().parse_ethtool("Identifier : 0x03 (SFP)\nIdentifier : 0x03 (SFP)")

    def test_thresholds_are_not_current_values(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nLaser output power high alarm threshold : 1 mW / 0 dBm")
        self.assertEqual(result["status"], "not-reported")

    def test_rejects_negative_or_inconsistent_mw_pairs(self):
        for pair in ("-1 mW / 0 dBm", "1 mW / -20 dBm", "0 mW / 0 dBm"):
            with self.subTest(pair=pair):
                result = load_module().parse_ethtool(f"Identifier : 0x03 (SFP)\nLaser output power : {pair}")
                self.assertIsNone(result["power_dbm"]["tx"])

    def test_rounded_mw_does_not_lose_valid_low_dbm(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nReceiver signal average optical power : 0.0000 mW / -50.00 dBm")
        self.assertEqual(result["power_dbm"]["rx"], -50.0)

    def test_vendor_containing_lane_is_not_misclassified(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nVendor name : PlanePhotonics\nLaser output power : 1 mW / 0 dBm")
        self.assertEqual(result["power_dbm"]["tx"], 0.0)
        self.assertEqual(result["module"]["vendor"], "PlanePhotonics")

    def test_temperature_requires_complete_correct_units(self):
        result = load_module().parse_ethtool(
            "Identifier : 0x03 (SFP)\nModule temperature : 38 degrees C / SECRET INVALID")
        self.assertNotIn("temperature_c", result["sensors"])

    def test_sfp_channel_fields_not_just_qsfp_identifier_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "lane"):
            load_module().parse_ethtool(
                "Identifier : 0x03 (SFP)\nLaser output power (Channel 1) : 1 mW / 0 dBm")

    def test_multilane_identifiers_never_mislabel_global_power_as_single_lane(self):
        for identifier in ("0x11 (QSFP28)", "0x0c (QSFP)", "0x1a (SFP-DD)",
                           "0x19 (OSFP)", "CMIS"):
            with self.subTest(identifier=identifier):
                with self.assertRaisesRegex(ValueError, "lane"):
                    load_module().parse_ethtool(
                        f"Identifier : {identifier}\nLaser output power : 1 mW / 0 dBm")


class CLITests(unittest.TestCase):
    def run_cli(self, *args, text=None):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *args],
                              input=text, capture_output=True, text=True, timeout=10)

    def test_routeros_stdin_json_report_without_private_fields(self):
        result = self.run_cli("--format", "routeros", "--input", "-",
                             text="name: ether1\nsfp-tx-power: 0dBm\nsfp-rx-power: -8dBm\nsfp-vendor-serial: PRIVATE-SERIAL")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["power_dbm"], {"tx": 0.0, "rx": -8.0})
        self.assertEqual(report["status"], "power-reported")
        self.assertNotIn("PRIVATE-SERIAL", result.stdout)

    def test_reads_file_without_modifying_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "monitor.txt"
            body = b"Identifier : 0x03 (SFP)\nLaser output power : 1.0000 mW / 0.00 dBm\n"
            path.write_bytes(body)
            result = self.run_cli("--format", "ethtool", "--input", str(path))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(path.read_bytes(), body)
            self.assertEqual(json.loads(result.stdout)["status"], "partial")

    def test_rejects_missing_args_and_unknown_options(self):
        for args in ((), ("--selftest",), ("--format", "unknown", "--input", "-")):
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, 2)

    def test_bad_input_has_concise_error_no_raw_data_or_traceback(self):
        for text in ("SECRET-DO-NOT-ECHO", "name: eth\x1b[31m", "name: a\nname: b"):
            with self.subTest(text=text):
                result = self.run_cli("--format", "routeros", "--input", "-", text=text)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn("Traceback", result.stderr)
                self.assertNotIn("SECRET-DO-NOT-ECHO", result.stderr)
                self.assertEqual(result.stdout, "")

    def test_invalid_utf8_and_oversized_file_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.txt"
            for data in (b"\xff", b"x" * 262145):
                with self.subTest(length=len(data)):
                    path.write_bytes(data)
                    result = self.run_cli("--format", "routeros", "--input", str(path))
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn("Traceback", result.stderr)

    def test_interface_flag_labels_report_and_guards_routeros_mismatch(self):
        result = self.run_cli("--format", "ethtool", "--input", "-", "--interface", "enp1s0",
                              text="Identifier : 0x03 (SFP)")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["interface"], "enp1s0")
        mismatch = self.run_cli("--format", "routeros", "--input", "-", "--interface", "ether2",
                                text="name: ether1\nsfp-tx-power: 0dBm\nsfp-rx-power: -1dBm")
        self.assertEqual(mismatch.returncode, 2)
        self.assertIn("cocok", mismatch.stderr)

    def test_review_boundary_errors_never_emit_report_or_raw_label(self):
        cases = (
            ("routeros", None, "sfp-tx-power: 0dBm\nsfp-rx-power: -1dBm"),
            ("routeros", None, "name: \nsfp-tx-power: 0dBm"),
            ("routeros", "SECRET-OTHER-PORT", "name: ether1"),
            ("ethtool", "eth\nSECRET", "Identifier : 0x03 (SFP)"),
            ("ethtool", "SECRET" * 50, "Identifier : 0x03 (SFP)"),
            ("ethtool", None, "Identifier : 0x1a (SFP-DD)"),
            ("ethtool", None, "Identifier : 0x1b (DSFP)"),
            ("routeros", None, "name: ether1\nsfp-type: DSFP"),
            ("ethtool", "eth\udcffSECRET", "Identifier : 0x03 (SFP)"),
            ("ethtool", "eth\u2028SECRET", "Identifier : 0x03 (SFP)"),
            ("ethtool", "eth\u2029SECRET", "Identifier : 0x03 (SFP)"),
        )
        for fmt, label, body in cases:
            with self.subTest(fmt=fmt, label=label):
                args = ["--format", fmt, "--input", "-"]
                if label is not None:
                    args.extend(["--interface", label])
                result = self.run_cli(*args, text=body)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertNotIn("SECRET", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_label_survives_early_no_diagnostics_result(self):
        result = self.run_cli("--format", "ethtool", "--input", "-", "--interface", "enp1s0",
                              text="Identifier : 0x03 (SFP)\nOptical diagnostics support : No")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["interface"], "enp1s0")
        self.assertEqual(report["status"], "diagnostics-not-supported")
        self.assertEqual(report["power_dbm"], {"tx": None, "rx": None})
        self.assertFalse(report["hardware_verified"])

    def test_missing_file_is_error_not_empty_report(self):
        result = self.run_cli("--format", "routeros", "--input", "/nonexistent/monitor.txt")
        self.assertEqual(result.returncode, 2)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
