#!/usr/bin/env python3
"""Offline, single-lane two-endpoint DOM analysis; not a NIC/firmware fix."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import stat
import sys

try:
    from .sfp_diagnostics import MAX_TEXT_BYTES, parse_ethtool, parse_routeros
except ImportError:  # Direct script execution.
    from sfp_diagnostics import MAX_TEXT_BYTES, parse_ethtool, parse_routeros

_TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})\Z"
)


def _timestamp(value: str) -> datetime:
    if not _TIMESTAMP.fullmatch(value):
        raise ValueError("capture timestamp must be ISO 8601 with seconds and timezone")
    if value[-6:-5] in ("+", "-"):
        if int(value[-5:-3]) > 23 or int(value[-2:]) > 59:
            raise ValueError("invalid capture timestamp timezone")
        if value.endswith("-00:00"):
            raise ValueError("unknown timezone -00:00 is not accepted")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError("invalid capture timestamp") from None


def _skew(value: str) -> float:
    try:
        number = float(value)
    except ValueError:
        raise ValueError("max skew must be finite seconds between 0 and 86400") from None
    if not math.isfinite(number) or not 0 <= number <= 86400:
        raise ValueError("max skew must be finite seconds between 0 and 86400")
    return number


def _label(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip() or len(value.encode("utf-8")) > 160 or any(
        ord(ch) < 32 or 127 <= ord(ch) <= 159 or ch in "\u2028\u2029" for ch in value
    ):
        raise ValueError("identity metadata must be nonempty, at most 160 UTF-8 bytes, without controls")
    return value.strip()


def _read_text(filename: str) -> str:
    """Bounded read, refusing links/reparse points (including parent components)."""
    path = Path(os.path.abspath(filename))
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError("input must not use symlinks or reparse points")
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("input must be a regular text file")
    if before.st_size > MAX_TEXT_BYTES:
        raise ValueError("input exceeds 256 KiB")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0)
                 | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened):
            raise ValueError("input changed or is not a regular file")
        raw = stream.read(MAX_TEXT_BYTES + 1)
    if len(raw) > MAX_TEXT_BYTES:
        raise ValueError("input exceeds 256 KiB")
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("input must be UTF-8 text") from None


def _endpoint(args, side: str) -> dict:
    def arg(name):
        return getattr(args, side + "_" + name)

    captured = _timestamp(arg("captured_at"))
    nic = {"model": _label(arg("nic_model")), "driver": _label(arg("driver")),
           "source": "user-supplied", "autodetected": False}
    interface = _label(arg("interface"))
    parse = parse_routeros if arg("format") == "routeros" else parse_ethtool
    text = _read_text(arg("input"))
    result = parse(text, interface=interface)
    if arg("format") == "ethtool":
        # The shared ethtool parser omits checksum annotations. Accept only an
        # explicit single annotation, without changing its power interpretation.
        checksums = []
        for line in text.splitlines():
            key, sep, value = line.strip().partition(":")
            if sep and key.strip().lower() in ("eeprom checksum", "eeprom-checksum"):
                checksums.append(value.strip())
        if len(checksums) > 1:
            raise ValueError("duplicate EEPROM checksum annotation")
        if checksums:
            result["module"]["eeprom_checksum"] = checksums[0]
    reasons = []
    if arg("stale"):
        reasons.append("capture marked stale by user")
    if result["status"] in ("module-absent", "diagnostics-not-supported", "not-reported"):
        reasons.append(result["status"])
    checksum = result["module"].get("eeprom_checksum")
    # Missing checksum is unknown, not a claim of validity. If supplied, fail closed.
    if checksum is not None and checksum.strip().lower() not in ("good", "ok", "valid"):
        reasons.append("EEPROM checksum bad or unrecognized")
    return {
        "source": result["source"],
        "captured_at": captured.isoformat(),
        "capture_time_source": "user-supplied",
        "interface": result["interface"],
        "nic": nic,
        "module": result["module"],
        "power_dbm": result["power_dbm"],
        "status": result["status"],
        "warnings": result["warnings"],
        "unavailable_reasons": reasons,
        "hardware_verified": False,
        "native_routeros_support": False,
    }


def _report(a: dict, b: dict, max_skew: float, confirmed: bool) -> dict:
    skew = abs((datetime.fromisoformat(a["captured_at"])
                - datetime.fromisoformat(b["captured_at"])).total_seconds())
    shared = []
    if not confirmed:
        shared.append("optical direction pairing not explicitly confirmed")
    if skew > max_skew:
        shared.append("captures stale relative to each other: maximum skew exceeded")
    directions = []
    for tx_name, tx, rx_name, rx in (("A", a, "B", b), ("B", b, "A", a)):
        reasons = list(shared)
        for name, endpoint in ((tx_name, tx), (rx_name, rx)):
            reasons.extend(f"{name}: {reason}" for reason in endpoint["unavailable_reasons"])
        tx_power, rx_power = tx["power_dbm"]["tx"], rx["power_dbm"]["rx"]
        for name, kind, power in ((tx_name, "TX", tx_power), (rx_name, "RX", rx_power)):
            if power is None or not math.isfinite(power):
                reasons.append(f"{name} {kind}: missing, nonfinite or invalid dBm/DOM reading")
        loss = None
        warnings = []
        if not reasons:
            loss = tx_power - rx_power
            if not math.isfinite(loss):
                loss = None
                reasons.append("nonfinite path-loss result")
            elif loss < 0:
                warnings.append("negative estimated loss; check pairing, timing and DOM calibration; not clamped")
        directions.append({
            "tx_endpoint": tx_name, "rx_endpoint": rx_name,
            "formula": f"{tx_name} TX dBm - {rx_name} RX dBm",
            "status": "unavailable" if reasons else "estimated",
            "estimated_path_loss_db": loss, "reasons": reasons, "warnings": warnings,
        })
    return {
        "schema_version": 1,
        "scope": "offline two-endpoint single-lane DOM estimate, not a NIC/driver/firmware fix",
        "source": "user-imported-text",
        "hardware_verified": False,
        "native_routeros_support": False,
        "optical_pairing_confirmed_by_user": confirmed,
        "wavelength_pairing_verified": False,
        "capture_skew_seconds": skew,
        "max_skew_seconds": max_skew,
        "endpoints": {"A": a, "B": b},
        "directions": directions,
        "limitations": [
            "Path loss includes connectors, splices and other optical components; not fiber-only attenuation or OTDR.",
            "DOM accuracy/calibration and user-supplied timestamps are not independently verified.",
            "Skew compares capture times, not age against the current clock; historical paired captures are allowed.",
            "Equal wavelengths do not establish pairing; BiDi may use complementary wavelengths.",
        ],
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Offline SFP link report; not hardware support or a firmware fix.", allow_abbrev=False)
    for side in ("a", "b"):
        parser.add_argument(f"--{side}-input", required=True, help="regular UTF-8 file, at most 256 KiB; no links/stdin")
        parser.add_argument(f"--{side}-format", required=True, choices=("routeros", "ethtool"))
        parser.add_argument(f"--{side}-captured-at", required=True, help="user-supplied ISO timestamp with timezone")
        parser.add_argument(f"--{side}-interface", help="optional port label; must match RouterOS name")
        parser.add_argument(f"--{side}-nic-model", help="manual identity only, not autodetected")
        parser.add_argument(f"--{side}-driver", help="manual identity only, not autodetected")
        parser.add_argument(f"--{side}-stale", action="store_true", help="mark known stale/cached telemetry unavailable")
    parser.add_argument("--max-skew-seconds", required=True, help="maximum capture separation, 0..86400 seconds")
    parser.add_argument("--confirm-optical-pairing", action="store_true",
                        help="user confirms A TX reaches B RX and B TX reaches A RX, including BiDi compatibility")
    args = parser.parse_args(argv)
    try:
        maximum = _skew(args.max_skew_seconds)
        a, b = _endpoint(args, "a"), _endpoint(args, "b")
        report = _report(a, b, maximum, args.confirm_optical_pairing)
        print(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False))
    except OSError:
        print("error: input/output unavailable", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
