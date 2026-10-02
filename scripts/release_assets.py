#!/usr/bin/env python3
"""Stage branded copies of workflow outputs; never modify firmware bytes."""
from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

BRAND = "Ali Patch Code"
BRAND_SLUG = "ali-patch-code"
ARCHITECTURES = ("x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc")
VALID_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
IMAGE_FORMATS = ("img", "qcow2", "vmdk", "vhd", "vhdx", "vdi")
HISTORICAL_STATUS = {
    "x86": "README lama melaporkan ROS/CHR bekerja; bukan bukti untuk 7.24.4.",
    "arm": "README lama melaporkan bootloop. Eksperimental, bukan untuk produksi.",
    "arm64": "README lama melaporkan CHR bekerja; hardware ARM64 belum terverifikasi.",
    "mipsbe": "README lama melaporkan bootloop pada sebagian perangkat.",
    "mmips": "README lama melaporkan bootloop. Eksperimental, bukan untuk produksi.",
    "smips": "README lama melaporkan bootloop. Eksperimental, bukan untuk produksi.",
    "ppc": "README lama menyatakan belum diuji.",
}


def expected_sources(version: str, arch: str) -> list[str]:
    """Exact output names from patch7.yml, not a permissive glob."""
    suffix = "" if arch == "x86" else f"-{arch}"
    names = [
        f"routeros-{version}{suffix}-patched.npk",
        f"all_packages{suffix}-{version}-patched.zip",
    ]
    if arch in ("x86", "arm64"):
        names.append(f"mikrotik-{version}{suffix}-patched.iso")
        names.extend(f"chr-{version}{suffix}-patched.{fmt}.zip"
                     for fmt in IMAGE_FORMATS)
    if arch == "x86":
        names.extend([
            f"netinstall-{version}-patched.zip",
            f"netinstall64-{version}-patched.zip",
            f"netinstall-{version}-patched.tar.gz",
        ])
        names.extend(f"install-image-{version}-patched.{fmt}.zip"
                     for fmt in IMAGE_FORMATS)
    return names


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    stage = commands.add_parser("stage", help="stage one architecture's outputs")
    stage.add_argument("--source", type=Path, required=True)
    stage.add_argument("--output", type=Path, required=True)
    stage.add_argument("--version", required=True)
    stage.add_argument("--arch", required=True)
    stage.add_argument("--changelog", type=Path, required=True)
    combine = commands.add_parser("combine", help="merge per-arch staging dirs")
    combine.add_argument("--dist", type=Path, required=True)
    combine.add_argument("--output", type=Path, required=True)
    combine.add_argument("--version", required=True)
    combine.add_argument("--changelog", type=Path, required=True)
    return parser.parse_args(argv)


def stage_assets(args: argparse.Namespace) -> int:
    if args.arch not in ARCHITECTURES:
        print(f"unsupported architecture: {args.arch}", file=sys.stderr)
        return 2
    if not VALID_VERSION.fullmatch(args.version):
        print(f"invalid version: {args.version!r}", file=sys.stderr)
        return 2
    if not args.changelog.is_file():
        print(f"changelog not found: {args.changelog}", file=sys.stderr)
        return 2
    sources = [args.source / name for name in expected_sources(args.version, args.arch)]
    for src in sources:
        if not src.is_file() or src.is_symlink():
            print(f"artifact not found or not a regular file: {src}", file=sys.stderr)
            return 3
    if args.output.exists() or args.output.is_symlink():
        print(f"output already exists; choose a new directory: {args.output}", file=sys.stderr)
        return 4
    changelog = args.changelog.read_text(encoding="utf-8", errors="replace").rstrip()
    args.output.mkdir(parents=True)
    staged = []
    checksum_lines = []
    for src in sources:
        branded = f"{BRAND_SLUG}-{args.arch}-{src.name}"
        dest = args.output / branded
        shutil.copyfile(src, dest)
        digest = sha256_of(dest)
        staged.append({"source": src.name, "filename": branded,
                       "size": dest.stat().st_size, "sha256": digest})
        checksum_lines.append(f"{digest}  {branded}")
    (args.output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    manifest = {"brand": BRAND, "routeros_version": args.version,
                "architecture": args.arch, "boot_tested": False, "assets": staged}
    (args.output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    notes = "\n".join([
        f"# {BRAND} — RouterOS {args.version} — {args.arch}", "",
        "Hasil patch BELUM diuji boot pada perangkat atau VM.",
        "Gunakan hanya di lab dengan rencana pemulihan; untuk produksi gunakan lisensi resmi.", "",
        HISTORICAL_STATUS[args.arch], "",
        "## Checksum", "", "Lihat SHA256SUMS pada rilis ini.", "",
        f"## Changelog RouterOS {args.version}", "", changelog, "",
    ])
    (args.output / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    print(f"staged {len(staged)} {args.arch} assets into {args.output}")
    return 0


COMBINE_METADATA = ("SHA256SUMS", "manifest.json", "RELEASE_NOTES.md")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
CHECKSUM_LINE = re.compile(r"^([0-9a-f]{64})  ([^/\\\s]+)$")


class CombineError(Exception):
    """Rejection with a concise message; users never see a traceback."""

    def __init__(self, message: str, code: int = 6):
        super().__init__(message)
        self.code = code


def branded_filename(arch: str, source_name: str) -> str:
    return f"{BRAND_SLUG}-{arch}-{source_name}"


def _reject_symlink_ancestors(path: Path, label: str) -> None:
    # Preserve '..' until every traversed component has been checked.
    probe = path if path.is_absolute() else Path.cwd() / path
    checked = Path(probe.anchor)
    for part in probe.parts[1:]:
        checked = checked / part
        if checked.is_symlink():
            raise CombineError(f"symlink not allowed in {label}: {checked}", 8)


def _expect_regular(path: Path, description: str) -> None:
    if path.is_symlink():
        raise CombineError(f"symlink not allowed: {path}", 8)
    if not path.is_file():
        raise CombineError(f"{description} not a regular file: {path}", 5)


def _validated_manifest(path: Path, arch: str, version: str) -> dict:
    where = f"manifest invalid: {path}"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise CombineError(f"{where}: unreadable or malformed JSON: {error}") from None
    if not isinstance(data, dict):
        raise CombineError(f"{where}: top level is not a JSON object")
    keys = {"brand", "routeros_version", "architecture", "boot_tested", "assets"}
    if set(data) != keys:
        raise CombineError(f"{where}: keys must be exactly {sorted(keys)}")
    if data["brand"] != BRAND:
        raise CombineError(f"{where}: brand must be {BRAND!r}")
    if data["routeros_version"] != version:
        raise CombineError(f"{where}: routeros_version must be {version!r}")
    if data["architecture"] != arch:
        raise CombineError(f"{where}: architecture must be {arch!r}")
    if data["boot_tested"] is not False:
        raise CombineError(f"{where}: boot_tested must be false")
    assets = data["assets"]
    if not isinstance(assets, list):
        raise CombineError(f"{where}: assets must be a list")
    expected = {branded_filename(arch, name): name
                for name in expected_sources(version, arch)}
    if len(assets) != len(expected):
        raise CombineError(
            f"{where}: {len(assets)} asset entries, expected {len(expected)}")
    seen: set[str] = set()
    for entry in assets:
        if not isinstance(entry, dict):
            raise CombineError(f"{where}: asset entry is not an object")
        if set(entry) != {"source", "filename", "size", "sha256"}:
            raise CombineError(f"{where}: asset entry keys must be exactly "
                               "['filename', 'sha256', 'size', 'source']")
        source, filename = entry["source"], entry["filename"]
        if not isinstance(source, str) or not isinstance(filename, str):
            raise CombineError(f"{where}: source and filename must be strings")
        if Path(filename).is_absolute() or filename != Path(filename).name:
            raise CombineError(f"{where}: unsafe filename {filename!r}")
        if filename not in expected or expected[filename] != source:
            raise CombineError(
                f"{where}: {filename!r} is not an expected asset of {arch}")
        size = entry["size"]
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:
            raise CombineError(f"{where}: size for {filename!r} must be a "
                               "nonnegative integer")
        digest = entry["sha256"]
        if not isinstance(digest, str) or not SHA256_HEX.fullmatch(digest):
            raise CombineError(f"{where}: sha256 for {filename!r} must be "
                               "lowercase 64-hex")
        if filename in seen:
            raise CombineError(f"{where}: duplicate asset entry {filename!r}")
        seen.add(filename)
    if seen != set(expected):
        raise CombineError(
            f"{where}: missing asset entries {sorted(set(expected) - seen)}")
    return {"brand": BRAND, "routeros_version": version, "architecture": arch,
            "boot_tested": False,
            "assets": [{key: entry[key] for key in ("source", "filename", "size", "sha256")}
                       for entry in sorted(assets, key=lambda item: item["filename"])]}


def _validated_checksums(path: Path, verified: dict[str, str]) -> None:
    where = f"checksum list mismatch: {path}"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        raise CombineError(f"{where}: unreadable: {error}") from None
    listed: dict[str, str] = {}
    for line in lines:
        match = CHECKSUM_LINE.fullmatch(line)
        if not match:
            raise CombineError(f"{where}: malformed line {line!r}")
        digest, name = match.groups()
        if digest == "0" * 64:
            raise CombineError(f"{where}: zero digest for {name!r}")
        if name in listed:
            raise CombineError(f"{where}: duplicate entry for {name!r}")
        listed[name] = digest
    if listed != verified:
        missing = sorted(set(verified) - set(listed))
        extra = sorted(set(listed) - set(verified))
        stale = sorted(name for name in listed
                       if name in verified and listed[name] != verified[name])
        raise CombineError(
            f"{where}: missing={missing} extra={extra} stale={stale}")


def _preflight_combine(args: argparse.Namespace) -> dict:
    """Validate every input for every architecture before anything is copied."""
    if not VALID_VERSION.fullmatch(args.version):
        raise CombineError(f"invalid version: {args.version!r}", 2)
    _reject_symlink_ancestors(args.changelog, "changelog")
    _expect_regular(args.changelog, "changelog")
    dist = args.dist
    _reject_symlink_ancestors(dist, "input root")
    if not dist.is_dir():
        raise CombineError(f"input root not a directory: {dist}", 5)
    input_root = dist.resolve()
    output = args.output
    _reject_symlink_ancestors(output, "output path")
    if output.exists() or output.is_symlink():
        raise CombineError(
            f"output already exists; choose a new directory: {output}", 4)
    resolved_output = output.resolve()
    if resolved_output == input_root or resolved_output in input_root.parents \
            or input_root in resolved_output.parents:
        raise CombineError(f"output must be separate from the input root: "
                           f"{output} vs {dist}", 2)
    if not output.parent.is_dir():
        raise CombineError(f"output parent directory not found: {output.parent}", 4)
    try:
        changelog_text = args.changelog.read_text(
            encoding="utf-8", errors="replace").rstrip()
    except OSError as error:
        raise CombineError(f"changelog unreadable: {error}") from None

    present = {entry.name for entry in dist.iterdir()}
    for arch in ARCHITECTURES:
        if arch not in present:
            raise CombineError(
                f"missing architecture staging directory: {dist / arch}", 5)
    for name in sorted(present - set(ARCHITECTURES)):
        raise CombineError(f"unexpected entry in input root: {dist / name}")

    manifests: list[dict] = []
    entries: list[dict] = []
    destinations: set[str] = set()
    for arch in ARCHITECTURES:
        arch_dir = dist / arch
        if arch_dir.is_symlink():
            raise CombineError(f"symlink not allowed: {arch_dir}", 8)
        expected_assets = {branded_filename(arch, name)
                           for name in expected_sources(args.version, arch)}
        expected_entries = expected_assets | set(COMBINE_METADATA)
        actual = {entry.name for entry in arch_dir.iterdir()}
        for metadata in COMBINE_METADATA:
            if metadata not in actual:
                raise CombineError(
                    f"missing metadata file: {arch_dir / metadata}", 5)
        for name in sorted(expected_assets - actual):
            raise CombineError(f"missing asset file: {arch_dir / name}", 5)
        for name in sorted(actual - expected_entries):
            raise CombineError(f"unexpected entry in {arch}: {arch_dir / name}")
        for metadata in COMBINE_METADATA:
            _expect_regular(arch_dir / metadata, f"{arch} {metadata}")
        try:
            (arch_dir / "RELEASE_NOTES.md").read_bytes()
        except OSError as error:
            raise CombineError(
                f"unreadable metadata file: {arch_dir / 'RELEASE_NOTES.md'}: "
                f"{error}") from None
        manifest = _validated_manifest(arch_dir / "manifest.json", arch, args.version)
        verified: dict[str, str] = {}
        for entry in manifest["assets"]:
            asset_path = arch_dir / entry["filename"]
            _expect_regular(asset_path, "asset")
            digest = sha256_of(asset_path)
            if digest != entry["sha256"] or asset_path.stat().st_size != entry["size"]:
                raise CombineError(f"asset integrity mismatch: {asset_path}", 7)
            if entry["filename"] in destinations:
                raise CombineError(
                    f"manifest invalid: {arch_dir / 'manifest.json'}: duplicate "
                    f"destination filename {entry['filename']!r}")
            destinations.add(entry["filename"])
            verified[entry["filename"]] = digest
            entries.append({"source": asset_path, "dest": entry["filename"],
                            "sha256": digest, "size": entry["size"]})
        _validated_checksums(arch_dir / "SHA256SUMS", verified)
        manifests.append(manifest)

    manifest = {"brand": BRAND, "routeros_version": args.version,
                "architectures": manifests, "boot_tested": False}
    notes = ["# " + BRAND + " — RouterOS " + args.version + " — semua arsitektur", "",
             "Hasil patch BELUM diuji boot pada perangkat atau VM.",
             "Gunakan hanya di lab dengan rencana pemulihan; "
             "untuk produksi gunakan lisensi resmi.", ""]
    for arch in ARCHITECTURES:
        notes += [f"## {arch}", "", HISTORICAL_STATUS[arch], ""]
    notes += ["## Checksum", "", "Lihat SHA256SUMS pada rilis ini.", "",
              f"## Changelog RouterOS {args.version}", "", changelog_text, ""]
    return {"output": output, "entries": sorted(entries, key=lambda entry: entry["dest"]),
            "manifest": manifest, "notes": "\n".join(notes)}


def _remove_staging(staging: Path, parent: Path) -> None:
    """Delete only the temporary directory combine itself created."""
    if (staging.parent == parent and staging.name.startswith(".ali-combine-")
            and staging.is_dir() and not staging.is_symlink()):
        shutil.rmtree(staging, ignore_errors=True)


def _materialize(plan: dict, staging: Path) -> None:
    """Copy verified bytes into the staging directory and re-verify them."""
    checksum_lines = []
    for entry in plan["entries"]:
        source = entry["source"]
        _reject_symlink_ancestors(source, "input asset")
        if source.is_symlink() or not source.is_file():
            raise CombineError(f"input changed during combine: {source}", 9)
        dest = staging / entry["dest"]
        shutil.copyfile(source, dest)
        digest = sha256_of(dest)
        if digest != entry["sha256"] or dest.stat().st_size != entry["size"]:
            raise OSError(
                f"copied bytes differ from verified input: {entry['dest']}")
        checksum_lines.append(f"{digest}  {entry['dest']}")
    (staging / "SHA256SUMS").write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8")
    (staging / "manifest.json").write_text(
        json.dumps(plan["manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    (staging / "RELEASE_NOTES.md").write_text(plan["notes"], encoding="utf-8")
    for line in checksum_lines:
        digest, name = line.split("  ")
        if sha256_of(staging / name) != digest:
            raise OSError(f"post-copy verification failed: {name}")


def _publish_output(staging: Path, output: Path) -> None:
    """Atomically expose a complete directory, never replacing any path."""
    _reject_symlink_ancestors(output, "output path")
    if output.exists() or output.is_symlink():
        raise CombineError(
            f"output already exists; choose a new directory: {output}", 4)
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        # macOS RENAME_EXCL fails even for an existing empty directory.
        result = rename(os.fsencode(staging), os.fsencode(output), 0x00000004)
    elif sys.platform.startswith("linux") and hasattr(libc, "renameat2"):
        rename = libc.renameat2
        rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                           ctypes.c_char_p, ctypes.c_uint)
        rename.restype = ctypes.c_int
        # Linux RENAME_NOREPLACE with AT_FDCWD for both paths.
        result = rename(-100, os.fsencode(staging), -100, os.fsencode(output), 1)
    else:
        raise OSError(errno.ENOTSUP, "atomic non-replacing rename is unavailable")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(output))


def combine_assets(args: argparse.Namespace) -> int:
    try:
        plan = _preflight_combine(args)
    except CombineError as error:
        print(error, file=sys.stderr)
        return error.code
    output = plan["output"]
    try:
        staging = Path(tempfile.mkdtemp(prefix=".ali-combine-", dir=output.parent))
    except OSError as error:
        print(f"combine failed: {error}", file=sys.stderr)
        return 1
    staging_parent = staging.parent
    try:
        _materialize(plan, staging)
        _publish_output(staging, output)
    except (OSError, CombineError) as error:
        _remove_staging(staging, staging_parent)
        print(f"combine failed: {error}", file=sys.stderr)
        return 1
    print(f"combined {len(ARCHITECTURES)} architectures into {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "combine":
            return combine_assets(args)
        return stage_assets(args)
    except OSError as error:
        print(f"release staging failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
