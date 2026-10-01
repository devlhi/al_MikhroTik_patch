#!/usr/bin/env python3
"""Interpretasi telemetri SFP read-only untuk lab Ali Patch Code.

Alat ini HANYA membaca output perintah RouterOS/Linux yang sudah dijalankan
user (paste text), lalu menafsirkannya. Alat ini BUKAN driver, BUKAN bagian
firmware RouterOS, dan tidak menambah dukungan hardware apa pun. Semua hasil
adalah interpretasi data yang diberikan hardware — tidak ada nilai yang
direkayasa. Fixtures sintetis pada tes bukan bukti kompatibilitas hardware.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys

MAX_TEXT_BYTES = 262144
_POWER_KEYS = ("sfp-tx-power", "sfp-rx-power")
_SENSOR_KEYS = ("sfp-temperature", "sfp-supply-voltage")
_POWER_RE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*dBm\s*$", re.IGNORECASE)
_UNIT_RES = {
    "sfp-temperature": (re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*C\s*$"), "temperature_c"),
    "sfp-supply-voltage": (re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*V\s*$"), "voltage_v"),
    "sfp-tx-bias-current": (re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*mA\s*$"), "bias_ma"),
}
_RECOGNIZED_KEYS = frozenset(
    ("name", "status", "sfp-module-present")
    + _POWER_KEYS
    + _SENSOR_KEYS
    + ("sfp-tx-bias-current",)
    + (
        "sfp-vendor-name",
        "sfp-vendor-part-number",
        "sfp-wavelength",
        "sfp-type",
        "sfp-connector-type",
        "eeprom-checksum",
    )
)


def _parse_lines(text: str) -> dict:
    if not isinstance(text, str):
        raise ValueError("input bukan teks")
    if not text.strip() or len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
        raise ValueError("teks kosong atau terlalu besar")
    if any((ord(ch) < 0x20 and ch not in "\n\r\t") or 0x7F <= ord(ch) <= 0x9F for ch in text):
        raise ValueError("input mengandung karakter kontrol")
    keys: dict[str, str] = {}
    for raw in text.lstrip("\ufeff").splitlines():
        key, sep, value = raw.strip().partition(":")
        key = key.strip()
        if not sep or key not in _RECOGNIZED_KEYS:
            continue  # Serial, MAC, raw EEPROM dan field lain tidak disalin.
        if key in keys:
            if key == "name":
                raise ValueError("hanya satu port per input; name duplikat")
            raise ValueError("field monitor duplikat; ambil satu snapshot baru")
        keys[key] = value.strip()
    if not keys:
        raise ValueError("output monitor tidak dikenali")
    return keys


def _measurement_or_none(value: str, unit_re: re.Pattern) -> float | None:
    if value.upper() in ("N/A", "NA", ""):
        return None
    match = unit_re.match(value)
    if not match:
        return None
    number = float(match.group(1))
    if not math.isfinite(number):
        return None
    return number


def _interface_label(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("label interface harus teks")
    try:
        label_bytes = value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("label interface harus Unicode yang valid untuk UTF-8") from None
    if len(label_bytes) > 255 or any(
            ord(ch) < 0x20 or 0x7F <= ord(ch) <= 0x9F or ch in "\u2028\u2029"
            for ch in value):
        raise ValueError("label interface terlalu panjang atau mengandung karakter kontrol/pemisah baris")
    return value.strip() or None


def parse_routeros(text: str, *, interface: str | None = None) -> dict:
    """Interpretasikan output `/interface ethernet monitor <port> once` satu port."""
    interface = _interface_label(interface)
    fields = _parse_lines(text)
    if not fields.get("name"):
        raise ValueError("input RouterOS harus memuat satu name port yang tidak kosong")
    if interface and interface != fields["name"]:
        raise ValueError("label interface tidak cocok dengan name port pada input")
    warnings: list[str] = []
    sfp_type = (fields.get("sfp-type") or "").upper()
    if any(token in sfp_type for token in ("QSFP", "SFP-DD", "DSFP", "OSFP")):
        raise ValueError("format multilane belum didukung; jangan gabungkan lane")
    if fields.get("sfp-module-present") == "no":
        return _result(
            fields,
            status="module-absent",
            power={"tx": None, "rx": None},
            sensors={},
            warnings=["sfp-module-present: no — power lama diabaikan"],
        )
    power: dict[str, float | None] = {}
    for key in _POWER_KEYS:
        value = _measurement_or_none(fields.get(key, "N/A"), _POWER_RE)
        if key in fields and value is None:
            warnings.append(f"{key} ada tapi nilainya bukan dBm yang valid")
        power[key.removeprefix("sfp-").removesuffix("-power")] = value
    sensors: dict[str, float] = {}
    for key, (unit_re, name) in _UNIT_RES.items():
        if key not in fields:
            continue
        value = _measurement_or_none(fields[key], unit_re)
        if value is not None:
            sensors[name] = value
        else:
            warnings.append(f"{key} ada tapi nilai/unit sensor tidak dikenali")
    if power["tx"] is None and power["rx"] is None:
        status = "not-reported"
        warnings.append("tidak ada power TX/RX yang dilaporkan perangkat")
    elif power["tx"] is None or power["rx"] is None:
        status = "partial"
        warnings.append("hanya salah satu arah power yang dilaporkan")
    else:
        status = "power-reported"
    return _result(fields, status=status, power=power, sensors=sensors, warnings=warnings)


_ETHTOOL_DBM_RE = re.compile(
    r"^\s*([+-]?\d+(?:\.\d+)?)\s*mW\s*/\s*([+-]?\d+(?:\.\d+)?)\s*dBm\s*$", re.IGNORECASE)
_ETHTOOL_KEYS = {
    "Identifier": ("identifier", None),
    "Vendor name": ("vendor", None),
    "Vendor PN": ("part_number", None),
    "Vendor OUI": ("vendor_oui", None),
    "Optical diagnostics support": ("diagnostics_support", None),
    "Laser output power": ("tx_power", _ETHTOOL_DBM_RE),
    "Receiver signal average optical power": ("rx_power", _ETHTOOL_DBM_RE),
    "Module temperature": ("temperature", re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*degrees C\s*/\s*[+-]?\d+(?:\.\d+)?\s*degrees F\s*$", re.IGNORECASE)),
    "Module voltage": ("voltage", re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*V\s*$", re.IGNORECASE)),
    "Laser bias current": ("bias", re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*mA\s*$", re.IGNORECASE)),
}


def parse_ethtool(text: str, *, interface: str | None = None) -> dict:
    """Interpretasikan output `ethtool -m <iface>` (mode decoded, satu lane)."""
    interface = _interface_label(interface)
    if not isinstance(text, str):
        raise ValueError("input bukan teks")
    if not text.strip() or len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
        raise ValueError("teks kosong atau terlalu besar")
    if any((ord(ch) < 0x20 and ch not in "\n\r\t") or 0x7F <= ord(ch) <= 0x9F for ch in text):
        raise ValueError("input mengandung karakter kontrol")
    values: dict[str, str | None] = {}
    for raw in text.lstrip("\ufeff").splitlines():
        line = raw.strip()
        if not line:
            continue
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key = key.strip()
        if re.search(r"\b(channel|lane)\s*\d+\b", key, re.IGNORECASE):
            raise ValueError("output multilane belum didukung; jangan gabungkan lane")
        if key == "Identifier" and any(
                token in value.upper() for token in ("QSFP", "CMIS", "SFP-DD", "DSFP", "OSFP")):
            raise ValueError("format multilane/CMIS membutuhkan decoder terpisah")
        if key not in _ETHTOOL_KEYS:
            continue
        if key in values:
            raise ValueError("field ethtool duplikat; ambil satu snapshot baru")
        values[key] = value.strip() or None
    if not values:
        raise ValueError("output ethtool tidak dikenali")
    diag = values.get("Optical diagnostics support")
    if diag is not None and diag.lower().startswith("no"):
        return _ethtool_result(
            values, status="diagnostics-not-supported",
            power={"tx": None, "rx": None}, sensors={},
            warnings=["modul tidak mendukung diagnostik optik (DDM/DOM)"], interface=interface)
    power: dict[str, float | None] = {"tx": None, "rx": None}
    sensors: dict[str, float] = {}
    warnings: list[str] = []
    for key, (field, unit_re) in _ETHTOOL_KEYS.items():
        value = values.get(key)
        if value is None or unit_re is None:
            continue
        match = unit_re.match(value)
        group = 2 if field in ("tx_power", "rx_power") else 1
        number = float(match.group(group)) if match else None
        if number is not None and not math.isfinite(number):
            number = None
        if number is not None and match and field in ("tx_power", "rx_power"):
            mw_text = match.group(1)
            mw = float(mw_text)
            decimals = len(mw_text.partition(".")[2])
            rounding = 0.5 * (10 ** -decimals)
            try:
                expected_mw = 10 ** (number / 10)
                if mw < 0 or not math.isfinite(mw) or abs(mw - expected_mw) > rounding + 0.002 * expected_mw:
                    number = None
            except OverflowError:
                number = None
        if field == "tx_power":
            power["tx"] = number
        elif field == "rx_power":
            power["rx"] = number
        elif field == "temperature" and number is not None:
            sensors["temperature_c"] = number
        elif field == "voltage" and number is not None:
            sensors["voltage_v"] = number
        elif field == "bias" and number is not None:
            sensors["bias_ma"] = number
        if number is None:
            warnings.append(f"{key} ada tapi formatnya tidak dikenali")
    if power["tx"] is None and power["rx"] is None:
        status = "not-reported"
        warnings.append("tidak ada power TX/RX yang dilaporkan driver")
    elif power["tx"] is None or power["rx"] is None:
        status = "partial"
        warnings.append("hanya salah satu arah power yang dilaporkan")
    else:
        status = "power-reported"
    return _ethtool_result(values, status=status, power=power, sensors=sensors,
                           warnings=warnings, interface=interface)


def _ethtool_result(values, status, power, sensors, warnings, *, interface=None) -> dict:
    module_meta = {
        "identifier": values.get("Identifier"),
        "vendor": values.get("Vendor name"),
        "part_number": values.get("Vendor PN"),
        "diagnostics_support": values.get("Optical diagnostics support"),
    }
    return {
        "schema_version": 1,
        "source": "linux-ethtool-text",
        "status": status,
        "interface": interface or None,
        "power_dbm": power,
        "sensors": sensors,
        "module": module_meta,
        "warnings": warnings,
        "hardware_verified": False,
        "routeros_support_verified": False,
    }


def _result(fields, status, power, sensors, warnings) -> dict:
    module_meta = {
        "vendor": fields.get("sfp-vendor-name"),
        "part_number": fields.get("sfp-vendor-part-number"),
        "wavelength_nm": fields.get("sfp-wavelength"),
        "sfp_type": fields.get("sfp-type"),
        "connector": fields.get("sfp-connector-type"),
        "eeprom_checksum": fields.get("eeprom-checksum"),
    }
    return {
        "schema_version": 1,
        "source": "routeros-monitor-text",
        "status": status,
        "interface": fields.get("name"),
        "power_dbm": power,
        "sensors": sensors,
        "module": module_meta,
        "warnings": warnings,
        "hardware_verified": False,
        "routeros_support_verified": False,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Ali Patch Code — interpretasi SFP offline, bukan driver/NPK.",
        allow_abbrev=False)
    parser.add_argument("--format", choices=("routeros", "ethtool"), required=True)
    parser.add_argument("--input", required=True, help="file UTF-8; '-' membaca stdin")
    parser.add_argument("--interface", help="label port manual; RouterOS harus cocok dengan name")
    args = parser.parse_args(argv)
    try:
        if args.input == "-":
            raw = sys.stdin.buffer.read(MAX_TEXT_BYTES + 1)
        else:
            fd = os.open(args.input, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0))
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("input harus file biasa")
                raw = stream.read(MAX_TEXT_BYTES + 1)
        if len(raw) > MAX_TEXT_BYTES:
            raise ValueError("input melebihi 256 KiB")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValueError("input harus UTF-8") from None
        parse = parse_routeros if args.format == "routeros" else parse_ethtool
        report = parse(text, interface=args.interface)
    except OSError:
        print("error: input tidak dapat dibaca", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    try:
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    except BrokenPipeError:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
