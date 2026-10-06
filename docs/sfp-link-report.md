# Offline SFP link report — bounded external complement

`scripts/sfp_link_report.py` combines **two user-imported, single-lane text
captures** using the existing `parse_routeros` and `parse_ethtool` functions.
The existing parser remains unchanged. Python 3.10+ and the standard library are
sufficient; no dependencies, hardware queries, network access or SSH are used.

This is helpful offline analysis, **not a NIC driver/firmware fix, NPK, native
RouterOS feature, compatibility test, fiber tester or OTDR**. For the existing
single-endpoint tool and hardware-support boundaries, see [SFP power](sfp-power.md).

## Usage

Use already collected, sanitized UTF-8 text files: RouterOS single-port
`/interface ethernet monitor <port> once` output or decoded single-lane Linux
`ethtool -m <interface>` output. Each endpoint may use a different format.
This tool does not execute either command. Supply the actual capture time,
not the file modification time or the time you imported it.

Example (shell line continuations shown for Bash; use one line in other shells):

```sh
python -B scripts/sfp_link_report.py \
  --a-input endpoint-a.txt --a-format routeros \
  --a-captured-at 2026-10-04T12:00:00+00:00 \
  --a-nic-model 'User-reported NIC A' --a-driver 'User-reported driver A' \
  --b-input endpoint-b.txt --b-format ethtool --b-interface eth2 \
  --b-captured-at 2026-10-04T12:00:05Z \
  --b-nic-model 'User-reported NIC B' --b-driver 'User-reported driver B' \
  --max-skew-seconds 5 --confirm-optical-pairing
```

Required: both input paths, both formats, both timezone-aware ISO timestamps,
and the maximum skew. Timestamps must contain date, `T`, hours/minutes/seconds,
optional 1–6 fractional digits, and `Z` or `+/-HH:MM`. Naive timestamps, invalid
dates/offsets and unknown timezone `-00:00` are rejected. Skew is a finite number
of seconds from 0 through 86400; equality at the boundary is accepted.

`--confirm-optical-pairing` is the user's explicit assertion that **A TX reaches
B RX and B TX reaches A RX**, with appropriate optics in both directions.
Without this flag, the metadata and power report is still produced, but both
loss estimates are unavailable. A filename or identical wavelength does not
establish a pair. BiDi can use complementary wavelengths: the tool neither
requires equality nor pretends to verify wavelength compatibility. Confirm
pairing from your topology and module specifications, not from this report.

Optional `--a-stale` / `--b-stale` explicitly mark known stale/cached telemetry.
Capture skew checks whether the captures are sufficiently contemporaneous,
**not their absolute age against the current clock**. Historical paired captures
are useful and allowed. The tool cannot detect cached hardware readings or
verify the accuracy of manually supplied capture times.

NIC model/driver are optional manual identity labels (unknown becomes `null`).
They are marked `source: user-supplied`, `autodetected: false`; neither module
vendor nor an imported source is used to infer the NIC/driver. Optional interface
labels must match the RouterOS `name` field. Identity labels must be nonempty,
at most 160 UTF-8 bytes, and free of control characters/line separators.

## Meaning and unavailable results

Two explicit directional records are emitted:

- A → B: `A TX dBm - B RX dBm`
- B → A: `B TX dBm - A RX dBm`

Power is in **dBm**, the difference `estimated_path_loss_db` is in **dB**.
There is no subtraction of a port's local TX and local RX. For example,
A TX = 0 dBm, B RX = -5 dBm yields 5 dB estimated path loss. A RX = -8 dBm,
B TX = -2 dBm yields 6 dB in the reverse direction. Zero is valid, not missing.

This estimate includes connectors, splices and other optical components,
as well as DOM calibration/measurement error. It is **not fiber-only
attenuation**, a dB/km measurement, optical budget certification or OTDR.
Negative results remain negative and produce a warning to check pairing,
timing and calibration; they are never silently clamped to zero.

Each direction has `status: estimated` or `unavailable`, a nullable estimate,
`reasons`, and `warnings`. Missing/nonfinite/invalid-unit power blocks the
respective direction. Absent module/DOM, unsupported diagnostics, a known stale
endpoint or an explicitly bad/unrecognized EEPROM checksum blocks both
directions. Capture skew beyond the supplied limit also blocks both. Input
power remains reported as source telemetry when a separate quality guard blocks
its use; absent-module/unsupported-DOM values are discarded by the shared parser.

RouterOS `eeprom-checksum` comes from the shared parser. The wrapper also accepts
one explicit `EEPROM checksum: ...` or `eeprom-checksum: ...` annotation in
ethtool text, because the shared ethtool parser does not extract it. Supplied
checksum values must be `good`, `ok` or `valid` (case-insensitive) to permit use;
other/empty values block estimation. Missing checksum means **unknown**, not
bad and not verified. No checksum is computed from decoded text. Duplicate
annotations/fields and unsupported multilane/CMIS formats are input errors.

JSON preserves each endpoint's parser `source`, allowlisted module metadata,
power, parser status/warnings, and user-supplied identity/capture time. Top-level
and endpoint `hardware_verified` and `native_routeros_support` remain **false**;
`wavelength_pairing_verified` also remains false even after user confirmation.
`schema_version` is 1. CLI exit 0 means a report was produced (including unavailable
estimates); exit 2 means malformed arguments/input or an I/O failure.

## Input and privacy boundaries

- Only regular files, up to 256 KiB per endpoint; bounded reads and UTF-8 validation.
- No stdin, binary/raw EEPROM, directories, symlinks or Windows reparse points
  (including parent path components). Inputs should be stable files in a trusted
  local directory, not paths concurrently modified by another process.
- Shared parsers enforce recognized single-port fields, duplicates, controls and
  unit checks; ethtool's reported mW and dBm must also be consistent.
- Raw captures, file paths, module serials, MAC addresses, vendor OUI and license
  fields are not copied into the report. This is an allowlisted report, not a
  general-purpose redactor: **do not place secrets, serials, MACs or license data
  inside user identity labels or vendor/part-number fields**. Sanitize before import.
- No hardware verification, NIC autodetection, driver update or firmware modification
  occurs. Unavailable DOM is not by itself proof of a broken module or NIC.

## Synthetic tests

From the repository root:

```sh
python -B -m unittest discover -s tests -p 'test_sfp_link_report.py' -v
python -B -m unittest discover -s tests -p 'test_sfp_diagnostics.py' -v
```

Fixtures are synthetic CLI imports covering mixed formats, both explicit
directions, zero power/loss, unit distinctions, negative loss, missing/nonfinite
power, absent/unsupported DOM, checksum guards, confirmation/false capability
flags, capture skew/timezones/stale flags, manual identity, privacy, file bounds,
symlink paths and invalid schemas/arguments. Symlink tests skip only if the host
cannot create links. Tests do not demonstrate hardware or RouterOS support.
