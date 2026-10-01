#!/usr/bin/env python3
"""Stage branded release assets for the pinned x86 Ali Patch Code build.

Copies each workflow artifact into ``dist/`` under the
``ali-patch-code-x86-<artifact>`` name, then emits SHA256SUMS, a machine
readable manifest.json, and RELEASE_NOTES.md for the GitHub Release body.

Read-only with respect to inputs: artifacts are copied, never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

BRAND = "Ali Patch Code"
BRAND_SLUG = "ali-patch-code"
ARCH = "x86"

X86_ASSETS = [
    "mikrotik-{v}-patched.iso",
    "routeros-{v}-patched.npk",
    "all_packages-{v}-patched.zip",
    "netinstall-{v}-patched.zip",
    "netinstall64-{v}-patched.zip",
    "netinstall-{v}-patched.tar.gz",
]
for _image in ("chr", "install-image"):
    for _fmt in ("img", "qcow2", "vmdk", "vhd", "vhdx", "vdi"):
        X86_ASSETS.append(f"{_image}-{{v}}-patched.{_fmt}.zip")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="directory holding the workflow artifacts")
    parser.add_argument("--output", type=Path, required=True,
                        help="staging directory for branded assets")
    parser.add_argument("--version", required=True,
                        help="pinned RouterOS version, e.g. 7.23.3")
    parser.add_argument("--changelog", type=Path, required=True,
                        help="official CHANGELOG file to embed in release notes")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source: Path = args.source
    output: Path = args.output
    changelog: Path = args.changelog

    if not changelog.is_file():
        print(f"changelog not found: {changelog}", file=sys.stderr)
        return 2

    sources = [source / template.format(v=args.version) for template in X86_ASSETS]
    for src in sources:
        if not src.is_file():
            print(f"artifact not found: {src}", file=sys.stderr)
            return 3

    if output.exists() or output.is_symlink():
        print(f"output already exists; choose a new directory: {output}", file=sys.stderr)
        return 4
    output.mkdir(parents=True)

    staged = []
    checksum_lines = []
    for template in X86_ASSETS:
        name = template.format(v=args.version)
        src = source / name
        if not src.is_file():
            print(f"artifact not found: {src}", file=sys.stderr)
            return 3
        branded = f"{BRAND_SLUG}-{ARCH}-{name}"
        dest = output / branded
        shutil.copyfile(src, dest)
        digest = sha256_of(dest)
        staged.append({
            "source": name,
            "filename": branded,
            "size": dest.stat().st_size,
            "sha256": digest,
        })
        checksum_lines.append(f"{digest}  {branded}")

    (output / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n",
                                       encoding="utf-8")
    manifest = {
        "brand": BRAND,
        "routeros_version": args.version,
        "architecture": ARCH,
        "boot_tested": False,
        "assets": staged,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")

    notes = "\n".join([
        f"# {BRAND} — RouterOS {args.version} — {ARCH}",
        "",
        "Build dihasilkan ulang dari patch toolchain repo ini untuk versi yang",
        "dipin. Gambar hasil patch BELUM diuji boot pada perangkat atau VM;",
        "gunakan hanya untuk pengujian di laboratorium dengan rencana",
        "pemulihan. Produksi sebaiknya memakai RouterOS berlisensi resmi.",
        "",
        "## Checksum",
        "",
        "Lihat berkas SHA256SUMS pada rilis ini.",
        "",
        "## Changelog RouterOS {v}".format(v=args.version),
        "",
        changelog.read_text(encoding="utf-8", errors="replace").rstrip(),
        "",
    ])
    (output / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    print(f"staged {len(staged)} assets into {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
