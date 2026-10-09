"""Exercise the release staging CLI with synthetic bytes, never firmware."""
from contextlib import redirect_stderr
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/release_assets.py"
VERSION = "7.24.5"
ALL_ARCHS = ["x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc", "tile"]
METADATA_FILES = ("SHA256SUMS", "manifest.json", "RELEASE_NOTES.md")
TOTAL_ASSETS = 39
PYTHON = [sys.executable, *(["-O"] if sys.flags.optimize else []), "-B"]


def suffix(arch):
    return "" if arch == "x86" else f"-{arch}"


def expected_sources(arch, profile="all"):
    if profile == "chr-x86":
        return [f"chr-{VERSION}-patched.{fmt}.zip"
                for fmt in ("img", "qcow2", "vmdk", "vhd", "vhdx", "vdi")]
    s = suffix(arch)
    if arch == "x86":
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
    names = [
        f"routeros-{VERSION}{s}-patched.npk",
        f"all_packages{s}-{VERSION}-patched.zip",
    ]
    if arch == "arm64":
        names.insert(0, f"mikrotik-{VERSION}{s}-patched.iso")
        for fmt in ("img", "qcow2", "vmdk", "vhd", "vhdx", "vdi"):
            names.append(f"chr-{VERSION}{s}-patched.{fmt}.zip")
    return names


def branded_name(arch, source_name):
    return f"ali-patch-code-{arch}-{source_name}"


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get("TMPDIR"))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "build"
        self.source.mkdir()
        self.changelog = self.source / "CHANGELOG"
        self.changelog.write_text("Synthetic changelog for tests only.\n")

    def make_sources(self, arch, profile="all"):
        payloads = {}
        for name in expected_sources(arch, profile):
            data = f"SYNTHETIC TEST FIXTURE, NOT FIRMWARE: {arch} {name}\n".encode()
            (self.source / name).write_bytes(data)
            payloads[name] = data
        return payloads

    def stage(self, arch, output=None, version=VERSION, profile=None):
        output = output or self.root / "dist" / arch
        return subprocess.run(
            [*PYTHON, str(SCRIPT), "stage",
             "--source", str(self.source), "--output", str(output),
             "--version", version, "--arch", arch,
             "--changelog", str(self.changelog)]
            + (["--profile", profile] if profile is not None else []),
            text=True, capture_output=True, timeout=30,
        ), output

    def combine(self, dist, output=None, profile=None):
        output = output if output is not None else self.root / "merged"
        before = self.snapshot(self.root)
        result = subprocess.run(
            [*PYTHON, str(SCRIPT), "combine",
             "--dist", str(dist), "--output", str(output),
             "--version", VERSION, "--changelog", str(self.changelog)]
            + (["--profile", profile] if profile is not None else []),
            text=True, capture_output=True, timeout=30,
        )
        if result.returncode:
            self.assertEqual(self.snapshot(self.root), before,
                             "failure must preserve inputs, output and siblings")
        return result, output

    def snapshot(self, root):
        """Recursive byte-for-byte snapshot, including symlinks and dirs."""
        state = {}
        for path in sorted(root.rglob("*")):
            rel = str(path.relative_to(root))
            if path.is_symlink():
                state[rel] = ("link", os.readlink(path))
            elif path.is_dir():
                state[rel] = ("dir", None)
            else:
                state[rel] = ("file", path.read_bytes())
        return state

    def assert_rejected_without_side_effects(self, dist, output, result, message):
        self.assertNotEqual(result.returncode, 0, result.stderr)
        self.assertIn(message, result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertFalse(output.exists(), "rejected combine must not create the output")


class StageTests(Base):
    def test_rejects_existing_output_without_overwriting(self):
        self.make_sources("x86")
        output = self.root / "dist" / "x86"
        output.mkdir(parents=True)
        marker = output / "keep.txt"
        marker.write_text("keep")
        result, _ = self.stage("x86", output=output)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(output.iterdir()), [marker])

    def test_missing_asset_leaves_no_partial_release(self):
        self.make_sources("mipsbe")
        (self.source / expected_sources("mipsbe")[-1]).unlink()
        result, output = self.stage("mipsbe")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists(), "Incomplete release must not be staged")

    def test_stages_per_arch_assets_with_brand_and_preserves_bytes(self):
        for arch in ALL_ARCHS:
            with self.subTest(arch=arch):
                payloads = self.make_sources(arch)
                result, output = self.stage(arch)
                self.assertEqual(result.returncode, 0, result.stderr)
                manifest = json.loads((output / "manifest.json").read_text())
                self.assertEqual(manifest["brand"], "Ali Patch Code")
                self.assertEqual(manifest["routeros_version"], VERSION)
                self.assertEqual(manifest["architecture"], arch)
                self.assertIs(manifest["boot_tested"], False)
                self.assertEqual(len(manifest["assets"]), len(payloads))
                checksums = (output / "SHA256SUMS").read_text().splitlines()
                for name, payload in payloads.items():
                    branded = branded_name(arch, name)
                    self.assertEqual((output / branded).read_bytes(), payload)
                    self.assertEqual((self.source / name).read_bytes(), payload)
                    digest = hashlib.sha256(payload).hexdigest()
                    self.assertIn(f"{digest}  {branded}", checksums)
                    entry = next(a for a in manifest["assets"]
                                 if a["filename"] == branded)
                    self.assertEqual(entry["sha256"], digest)
                    self.assertEqual(entry["size"], len(payload))
                body = (output / "RELEASE_NOTES.md").read_text()
                self.assertIn(f"Ali Patch Code — RouterOS {VERSION} — {arch}", body)
                self.assertIn("BELUM diuji boot", body)

    def test_invalid_version_is_rejected_before_creating_output(self):
        self.make_sources("arm")
        for bad in ["latest", "7.23", "../../outside", "7.24.4\nBAD=1", "7.24.4;id"]:
            with self.subTest(version=bad):
                output = self.root / "dist-bad"
                result, out = self.stage("arm", output=output, version=bad)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("invalid version", result.stderr)
                self.assertFalse(out.exists())

    def test_rejects_unknown_architecture(self):
        self.make_sources("x86")
        result, _ = self.stage("riscv")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported architecture", result.stderr)

    def test_tile_has_only_two_package_assets_and_explicit_unverified_status(self):
        self.make_sources("tile")
        result, output = self.stage("tile")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads((output / "manifest.json").read_text())
        self.assertEqual({asset["filename"] for asset in manifest["assets"]}, {
            branded_name("tile", f"routeros-{VERSION}-tile-patched.npk"),
            branded_name("tile", f"all_packages-tile-{VERSION}-patched.zip"),
        })
        self.assertIs(manifest["boot_tested"], False)
        notes = (output / "RELEASE_NOTES.md").read_text()
        self.assertIn("matcher, build, boot dan aktivasi belum terverifikasi", notes)
        self.assertIn("Bukan dukungan siap pakai", notes)

    def test_tile_is_rejected_from_both_x86_scoped_profiles(self):
        self.make_sources("tile")
        for profile in ("chr-x86", "x86-all"):
            with self.subTest(profile=profile):
                result, output = self.stage("tile", profile=profile)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported architecture", result.stderr)
                self.assertFalse(output.exists())

    def test_status_table_distinguishes_architectures(self):
        self.make_sources("x86")
        self.make_sources("mmips")
        _, x86_out = self.stage("x86")
        _, mmips_out = self.stage("mmips")
        x86_notes = (x86_out / "RELEASE_NOTES.md").read_text()
        mmips_notes = (mmips_out / "RELEASE_NOTES.md").read_text()
        self.assertIn("bootloop", mmips_notes.lower())
        self.assertIn("mmips", mmips_notes)
        self.assertNotIn("bootloop", x86_notes.lower())


class CombineTests(Base):
    def stage_all(self):
        for arch in ALL_ARCHS:
            self.make_sources(arch)
            result, output = self.stage(arch)
            assert result.returncode == 0, result.stderr

    def case_input(self, label):
        dist = self.root / f"case-{label}"
        shutil.copytree(self.root / "dist", dist)
        return dist

    def rewrite_manifest(self, dist, arch, mutate):
        path = dist / arch / "manifest.json"
        manifest = json.loads(path.read_text())
        mutate(manifest)
        path.write_text(json.dumps(manifest, indent=2))

    # --- success contract -------------------------------------------------

    def test_combine_merges_all_architectures_into_separate_output(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        before = self.snapshot(dist)
        result, _ = self.combine(dist, output=merged)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(dist), before,
                         "input root must stay byte-for-byte unchanged")
        entries = sorted(p.name for p in merged.iterdir())
        self.assertEqual(len(entries), TOTAL_ASSETS + len(METADATA_FILES))
        self.assertTrue(all(p.is_file() for p in merged.iterdir()),
                        "output must be flat, no directories")
        expected_entries = {branded_name(arch, name)
                            for arch in ALL_ARCHS for name in expected_sources(arch)}
        self.assertEqual({n for n in entries if n not in METADATA_FILES},
                         expected_entries)
        merged_sums = (merged / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(merged_sums), TOTAL_ASSETS)
        for line in merged_sums:
            digest, name = line.split("  ")
            self.assertTrue(name.startswith("ali-patch-code-"))
            actual = hashlib.sha256((merged / name).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, f"regenerated checksum wrong for {name}")
        manifest = json.loads((merged / "manifest.json").read_text())
        self.assertEqual(manifest["brand"], "Ali Patch Code")
        self.assertEqual(manifest["routeros_version"], VERSION)
        self.assertEqual([a["architecture"] for a in manifest["architectures"]],
                         ALL_ARCHS)
        self.assertIs(manifest["boot_tested"], False)
        body = (merged / "RELEASE_NOTES.md").read_text()
        for arch in ALL_ARCHS:
            self.assertIn(f"## {arch}", body)
        self.assertIn("BELUM diuji boot", body)
        self.assertIn("bootloop", body.lower())
        self.assertIn(self.changelog.read_text(), body)

    def test_combine_output_is_deterministic_when_metadata_order_changes(self):
        self.stage_all()
        dist = self.root / "dist"
        before = self.snapshot(dist)
        result, first = self.combine(dist, output=self.root / "first")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(dist), before)
        for arch in ALL_ARCHS:
            self.rewrite_manifest(dist, arch, lambda m: m["assets"].reverse())
            sums = dist / arch / "SHA256SUMS"
            sums.write_text("\n".join(reversed(sums.read_text().splitlines())) + "\n")
        reordered = self.snapshot(dist)
        result, second = self.combine(dist, output=self.root / "second")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.snapshot(dist), reordered)
        self.assertEqual(self.snapshot(first), self.snapshot(second),
                         "valid list permutations must not change combined bytes")
        lines = (second / "SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(lines), TOTAL_ASSETS)
        self.assertEqual([line.split("  ")[1] for line in lines],
                         sorted(line.split("  ")[1] for line in lines))

    def test_atomic_publication_refuses_existing_paths(self):
        spec = importlib.util.spec_from_file_location("release_assets_publish", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        publish = getattr(module, "_publish_output", None)
        self.assertTrue(callable(publish), "an atomic non-replacing publication is required")
        assert callable(publish)
        staging = self.root / ".ali-combine-owned"
        staging.mkdir()
        (staging / "marker").write_bytes(b"SYNTHETIC OUTPUT, NOT FIRMWARE")
        for kind in ("empty-dir", "nonempty-dir", "file", "dangling-link"):
            with self.subTest(kind=kind):
                output = self.root / kind
                if kind in ("empty-dir", "nonempty-dir"):
                    output.mkdir()
                    if kind == "nonempty-dir":
                        (output / "keep").write_text("keep")
                elif kind == "file":
                    output.write_text("keep")
                else:
                    output.symlink_to(self.root / "absent")
                before = self.snapshot(self.root)
                with self.assertRaises((module.CombineError, OSError)):
                    publish(staging, output)
                self.assertEqual(self.snapshot(self.root), before)
        publish(staging, self.root / "new-output")
        self.assertFalse(staging.exists())
        self.assertEqual((self.root / "new-output" / "marker").read_bytes(),
                         b"SYNTHETIC OUTPUT, NOT FIRMWARE")

    def test_combine_refuses_to_reuse_existing_output(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        merged.mkdir()
        marker = merged / "keep.txt"
        marker.write_text("keep")
        before = self.snapshot(dist)
        result, _ = self.combine(dist, output=merged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output already exists", result.stderr)
        self.assertEqual(marker.read_text(), "keep")
        self.assertEqual(self.snapshot(dist), before)

    # --- destructive-failure regressions ----------------------------------

    def test_combine_rejects_corrupt_asset_before_copying_anything(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        asset = dist / "ppc" / branded_name("ppc", expected_sources("ppc")[0])
        asset.write_bytes(b"CORRUPT SYNTHETIC FIXTURE")
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "asset integrity mismatch")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_fails_when_an_architecture_directory_is_missing(self):
        for arch in ALL_ARCHS[:-1]:
            self.make_sources(arch)
            result, _ = self.stage(arch)
            assert result.returncode == 0, result.stderr
        dist = self.root / "dist"
        merged = self.root / "merged"
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "missing architecture")
        self.assertEqual(sorted(p.name for p in dist.iterdir()), sorted(ALL_ARCHS[:-1]))

    def test_combine_rejects_either_missing_tile_asset_without_partial_output(self):
        self.stage_all()
        for index, source in enumerate(expected_sources("tile")):
            with self.subTest(source=source):
                dist = self.case_input(f"tile-missing-{index}")
                (dist / "tile" / branded_name("tile", source)).unlink()
                result, output = self.combine(dist)
                self.assert_rejected_without_side_effects(dist, output, result, "missing")
                self.assertIn("tile", result.stderr)

    def test_combine_rejects_late_ppc_missing_metadata_before_any_change(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        for metadata in METADATA_FILES:
            with self.subTest(metadata=metadata):
                dist = self.case_input(metadata)
                (dist / "ppc" / metadata).unlink()
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(dist, out, result, "missing")
                self.assertIn("ppc", result.stderr)
                self.assertEqual(self.snapshot(dist), before,
                                 "late failure must not touch earlier architectures")

    def test_combine_rejects_unmanifested_extra_file(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        (dist / "ppc" / "smuggled.npk").write_bytes(
            b"SYNTHETIC UNMANIFESTED FIXTURE, NOT FIRMWARE\n")
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result, "unexpected")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_extra_entry_in_input_root(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        (dist / "README.txt").write_text("unexpected root entry")
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "unexpected entry in input root")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_copy_failure_preserves_input_and_cleans_staging(self):
        self.stage_all()
        dist = self.root / "dist"
        publish = self.root / "publish"
        publish.mkdir()
        output = publish / "dist"
        before = self.snapshot(dist)
        spec = importlib.util.spec_from_file_location("release_assets_combine", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.parse_args([
            "combine", "--dist", str(dist), "--output", str(output),
            "--version", VERSION, "--changelog", str(self.changelog)])
        real_copyfile = shutil.copyfile
        calls = []

        def failing_copyfile(src, dst):
            if len(calls) >= 3:
                raise OSError(28, "simulated disk full, synthetic test failure")
            calls.append((src, dst))
            return real_copyfile(src, dst)

        stderr = io.StringIO()
        with mock.patch("shutil.copyfile", side_effect=failing_copyfile):
            with redirect_stderr(stderr):
                code = module.combine_assets(args)
        self.assertNotEqual(code, 0)
        self.assertIn("combine failed", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertEqual(self.snapshot(dist), before,
                         "copy-time failure must leave the input unchanged")
        self.assertFalse(output.exists(), "failed combine must expose no output")
        self.assertEqual(list(publish.iterdir()), [],
                         "owned staging temp must be cleaned up")

    def test_combine_copy_failure_cleans_relative_output_temp(self):
        self.stage_all()
        dist = self.root / "dist"
        publish = self.root / "publish"
        publish.mkdir()
        before = self.snapshot(self.root)
        spec = importlib.util.spec_from_file_location("release_assets_relative", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cwd = Path.cwd()
        os.chdir(self.root)
        try:
            args = module.parse_args([
                "combine", "--dist", "dist", "--output", "publish/merged",
                "--version", VERSION, "--changelog", "build/CHANGELOG"])
            stderr = io.StringIO()
            with mock.patch("shutil.copyfile", side_effect=OSError("simulated disk full")):
                with redirect_stderr(stderr):
                    code = module.combine_assets(args)
            self.assertNotEqual(code, 0)
            self.assertIn("combine failed", stderr.getvalue())
        finally:
            os.chdir(cwd)
        self.assertEqual(self.snapshot(self.root), before)
        self.assertEqual(list(publish.iterdir()), [], "relative paths must clean their temp")

    def test_combine_rechecks_copied_bytes_before_exposure(self):
        self.stage_all()
        dist = self.root / "dist"
        spec = importlib.util.spec_from_file_location("release_assets_corruption", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        real_copyfile = shutil.copyfile
        for corruption in ("immediate", "later"):
            with self.subTest(corruption=corruption):
                output = self.root / "merged"
                before = self.snapshot(self.root)
                copied = []

                def corrupting_copyfile(src, dst):
                    real_copyfile(src, dst)
                    copied.append(Path(dst))
                    if len(copied) == (1 if corruption == "immediate" else 3):
                        copied[0].write_bytes(b"SIMULATED DISK CORRUPTION, NOT FIRMWARE")

                stderr = io.StringIO()
                with mock.patch("shutil.copyfile", side_effect=corrupting_copyfile):
                    with redirect_stderr(stderr):
                        code = module.main([
                            "combine", "--dist", str(dist), "--output", str(output),
                            "--version", VERSION, "--changelog", str(self.changelog)])
                self.assertNotEqual(code, 0)
                self.assertIn("combine failed", stderr.getvalue())
                self.assertNotIn("Traceback", stderr.getvalue())
                self.assertEqual(self.snapshot(self.root), before)

    def test_combine_rejects_input_symlink_introduced_after_preflight(self):
        self.stage_all()
        dist = self.root / "dist"
        spec = importlib.util.spec_from_file_location("release_assets_copy_link", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.parse_args([
            "combine", "--dist", str(dist), "--output", str(self.root / "merged"),
            "--version", VERSION, "--changelog", str(self.changelog)])
        plan = module._preflight_combine(args)
        asset = plan["entries"][0]["source"]
        outside = self.root / "outside"
        outside.write_bytes(asset.read_bytes())
        asset.unlink()
        asset.symlink_to(outside)
        staging = self.root / ".ali-combine-owned"
        staging.mkdir()
        before = self.snapshot(self.root)
        with self.assertRaises((module.CombineError, OSError)):
            module._materialize(plan, staging)
        self.assertEqual(self.snapshot(self.root), before)

    def test_combine_rejects_arch_symlink_introduced_after_preflight(self):
        self.stage_all()
        dist = self.root / "dist"
        spec = importlib.util.spec_from_file_location("release_assets_arch_link", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        args = module.parse_args([
            "combine", "--dist", str(dist), "--output", str(self.root / "merged"),
            "--version", VERSION, "--changelog", str(self.changelog)])
        plan = module._preflight_combine(args)
        arch_dir = plan["entries"][0]["source"].parent
        outside = self.root / "outside-arch"
        arch_dir.rename(outside)
        arch_dir.symlink_to(outside, target_is_directory=True)
        staging = self.root / ".ali-combine-owned"
        staging.mkdir()
        before = self.snapshot(self.root)
        with self.assertRaises((module.CombineError, OSError)):
            module._materialize(plan, staging)
        self.assertEqual(self.snapshot(self.root), before)

    def test_atomic_publication_rejects_symlinked_ancestor(self):
        spec = importlib.util.spec_from_file_location("release_assets_publish_link", SCRIPT)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        staging = self.root / ".ali-combine-owned"
        staging.mkdir()
        (staging / "marker").write_bytes(b"SYNTHETIC OUTPUT, NOT FIRMWARE")
        parent = self.root / "real-parent"
        parent.mkdir()
        link = self.root / "parent-link"
        link.symlink_to(parent, target_is_directory=True)
        before = self.snapshot(self.root)
        with self.assertRaises((module.CombineError, OSError)):
            module._publish_output(staging, link / "new-output")
        self.assertEqual(self.snapshot(self.root), before)

    # --- symlink and path-traversal security ------------------------------

    def test_combine_rejects_absolute_filename_in_manifest(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        evil = self.root / "outside.bin"
        data = (dist / "arm" / branded_name("arm", expected_sources("arm")[0])).read_bytes()
        evil.write_bytes(data)

        def mutate(manifest):
            manifest["assets"][0]["filename"] = str(evil)

        self.rewrite_manifest(dist, "arm", mutate)
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "manifest invalid")
        self.assertEqual(self.snapshot(dist), before)
        self.assertEqual(evil.read_bytes(), data)

    def test_combine_rejects_parent_relative_filename_in_manifest(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"

        escaped = self.root / "escaped.npk"
        data = (dist / "arm" / branded_name("arm", expected_sources("arm")[0])).read_bytes()
        escaped.write_bytes(data)

        def mutate(manifest):
            manifest["assets"][0]["filename"] = "../../escaped.npk"

        self.rewrite_manifest(dist, "arm", mutate)
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "manifest invalid")
        self.assertEqual(self.snapshot(dist), before)
        self.assertEqual(escaped.read_bytes(), data)

    def test_combine_rejects_symlinked_asset(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        outside = self.root / "outside.bin"
        asset = dist / "arm" / branded_name("arm", expected_sources("arm")[0])
        outside.write_bytes(asset.read_bytes())
        asset.unlink()
        os.symlink(outside, asset)
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result, "symlink")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_symlinked_metadata(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        for metadata in METADATA_FILES:
            with self.subTest(metadata=metadata):
                dist = self.case_input(metadata)
                target = self.root / metadata
                path = dist / "ppc" / metadata
                target.write_bytes(path.read_bytes())
                path.unlink()
                path.symlink_to(target)
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(dist, out, result, "symlink")
                self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_symlinked_architecture_directory(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        real = self.root / "ppc-real"
        (dist / "ppc").rename(real)
        os.symlink(real, dist / "ppc")
        before = self.snapshot(real)
        result, out = self.combine(dist, output=merged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(self.snapshot(real), before)

    def test_combine_rejects_symlinked_input_root(self):
        self.stage_all()
        real = self.root / "input-real"
        (self.root / "dist").rename(real)
        dist = self.root / "dist"
        os.symlink("input-real", dist)
        merged = self.root / "merged"
        before = self.snapshot(real)
        result, out = self.combine(dist, output=merged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertFalse(out.exists())
        self.assertEqual(self.snapshot(real), before)

    def test_combine_rejects_symlinked_output(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        os.symlink(dist, merged)
        before = self.snapshot(dist)
        result, _ = self.combine(dist, output=merged)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stderr)
        self.assertTrue(merged.is_symlink(),
                        "combine must not replace or follow a symlinked output")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_output_nested_inside_input(self):
        self.stage_all()
        dist = self.root / "dist"
        result, out = self.combine(dist, output=dist / "nested" / "merged")
        self.assert_rejected_without_side_effects(dist, out, result, "separate")

    def test_combine_rejects_output_equal_to_input(self):
        self.stage_all()
        dist = self.root / "dist"
        before = self.snapshot(dist)
        result, _ = self.combine(dist, output=dist)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("output", result.stderr)
        self.assertEqual(self.snapshot(dist), before)

    # --- manifest schema and identity --------------------------------------

    def test_combine_rejects_empty_or_incomplete_manifest(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        pristine = (dist / "arm" / "manifest.json").read_text()
        cases = [
            ("empty", lambda m: m.__setitem__("assets", [])),
            ("incomplete", lambda m: m.__setitem__("assets", m["assets"][:-1])),
            ("duplicate", lambda m: m["assets"].append(dict(m["assets"][0]))),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                dist = self.case_input(label)
                self.rewrite_manifest(dist, "arm", mutate)
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(
                    dist, out, result, "manifest invalid")
                self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_manifest_with_wrong_identity(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        pristine = (dist / "arm" / "manifest.json").read_text()
        cases = [
            ("brand", "Evil Patch"),
            ("routeros_version", "9.9.9"),
            ("architecture", "x86"),
            ("boot_tested", True),
        ]
        for key, value in cases:
            with self.subTest(field=key):
                dist = self.case_input(key)
                self.rewrite_manifest(
                    dist, "arm", lambda m, k=key, v=value: m.__setitem__(k, v))
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(
                    dist, out, result, "manifest invalid")
                self.assertEqual(self.snapshot(dist), before)

    def test_combine_reports_invalid_identity_types_concisely(self):
        self.stage_all()
        for field in ("brand", "routeros_version", "architecture"):
            with self.subTest(field=field):
                dist = self.case_input(field)
                self.rewrite_manifest(
                    dist, "ppc", lambda m: m.__setitem__(field, ["NOT FIRMWARE"] * 100))
                result, out = self.combine(dist)
                self.assert_rejected_without_side_effects(dist, out, result,
                                                          "manifest invalid")
                self.assertLess(len(result.stderr), 600, "do not dump malformed field data")

    def test_combine_rejects_manifest_with_bad_field_types(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        pristine = (dist / "arm" / "manifest.json").read_text()
        cases = [
            ("size-string", lambda e: e.__setitem__("size", "12")),
            ("size-bool", lambda e: e.__setitem__("size", True)),
            ("size-negative", lambda e: e.__setitem__("size", -1)),
            ("size-zero", lambda e: e.__setitem__("size", 0)),
            ("sha-uppercase", lambda e: e.__setitem__("sha256", e["sha256"].upper())),
            ("sha-short", lambda e: e.__setitem__("sha256", "abc")),
            ("filename-not-str", lambda e: e.__setitem__("filename", 7)),
            ("extra-entry-key", lambda e: e.__setitem__("evil", True)),
            ("assets-not-list", lambda m: m.__setitem__("assets", {})),
            ("entry-not-dict", lambda m: m.__setitem__("assets", ["nope"])),
        ]
        for label, mutate in cases:
            with self.subTest(case=label):
                dist = self.case_input(label)
                self.rewrite_manifest(
                    dist, "arm",
                    lambda m, f=mutate: f(m["assets"][0])
                    if label.startswith(("size", "sha", "filename", "extra"))
                    else f(m))
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(
                    dist, out, result, "manifest invalid")
                self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_malformed_manifest_json_concisely(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        (dist / "smips" / "manifest.json").write_text("{not valid json")
        before = self.snapshot(dist)
        result, out = self.combine(dist, output=merged)
        self.assert_rejected_without_side_effects(dist, out, result,
                                                  "manifest invalid")
        self.assertEqual(self.snapshot(dist), before)

    def test_combine_rejects_non_dict_or_missing_manifest_schema(self):
        self.stage_all()
        for label, content in (
            ("list", "[]"), ("null", "null"), ("object", "{}"),
        ):
            with self.subTest(case=label):
                dist = self.case_input(label)
                (dist / "ppc" / "manifest.json").write_text(content)
                result, out = self.combine(dist)
                self.assert_rejected_without_side_effects(dist, out, result,
                                                          "manifest invalid")

    def test_combine_rejects_unparseable_manifest_without_traceback(self):
        self.stage_all()
        for label, content in (
            ("deep-json", "[" * 1200 + "0" + "]" * 1200),
            ("huge-integer", '{"size":' + "1" * 5000 + "}"),
            ("deep-identity", '{"brand":' + "[" * 1200 + "0" + "]" * 1200
             + ',"routeros_version":"7.24.4","architecture":"ppc",'
               '"boot_tested":false,"assets":[]}'),
        ):
            with self.subTest(case=label):
                dist = self.case_input(label)
                (dist / "ppc" / "manifest.json").write_text(content)
                result, out = self.combine(dist)
                self.assert_rejected_without_side_effects(dist, out, result,
                                                          "manifest invalid")

    def test_combine_rejects_noncorresponding_manifest_source(self):
        self.stage_all()
        for label, source in (("wrong", "wrong.npk"), ("non-string", None)):
            with self.subTest(case=label):
                dist = self.case_input(label)
                self.rewrite_manifest(
                    dist, "ppc", lambda m: m["assets"][0].__setitem__("source", source))
                result, out = self.combine(dist)
                self.assert_rejected_without_side_effects(dist, out, result,
                                                          "manifest invalid")

    def test_combine_rejects_cross_arch_destination_collision(self):
        self.stage_all()
        dist = self.root / "dist"
        collision = branded_name("x86", expected_sources("x86")[0])
        self.rewrite_manifest(
            dist, "ppc", lambda m: m["assets"][0].__setitem__("filename", collision))
        result, out = self.combine(dist)
        self.assert_rejected_without_side_effects(dist, out, result, "manifest invalid")

    def test_combine_rejects_unexpected_arch_subdirectory(self):
        self.stage_all()
        dist = self.root / "dist"
        (dist / "ppc" / "nested").mkdir()
        result, out = self.combine(dist)
        self.assert_rejected_without_side_effects(dist, out, result, "unexpected")

    def test_combine_rejects_symlinked_output_ancestor(self):
        self.stage_all()
        dist = self.root / "dist"
        parent = self.root / "publish"
        parent.mkdir()
        link = self.root / "publish-link"
        link.symlink_to(parent, target_is_directory=True)
        result, out = self.combine(dist, output=link / "merged")
        self.assert_rejected_without_side_effects(dist, out, result, "symlink")
        self.assertEqual(list(parent.iterdir()), [])

    def test_combine_rejects_symlinked_input_ancestor(self):
        self.stage_all()
        dist = self.root / "dist"
        link = self.root / "input-link"
        link.symlink_to(self.root, target_is_directory=True)
        result, out = self.combine(link / "dist")
        self.assert_rejected_without_side_effects(dist, out, result, "symlink")

    def test_combine_rejects_symlinked_changelog(self):
        self.stage_all()
        target = self.root / "real-changelog"
        self.changelog.rename(target)
        self.changelog.symlink_to(target)
        dist = self.root / "dist"
        result, out = self.combine(dist)
        self.assert_rejected_without_side_effects(dist, out, result, "symlink")

    def test_combine_rejects_nonregular_metadata_or_changelog(self):
        self.stage_all()
        dist = self.root / "dist"
        for metadata in METADATA_FILES:
            with self.subTest(metadata=metadata):
                case = self.case_input(metadata)
                path = case / "ppc" / metadata
                path.unlink()
                path.mkdir()
                result, out = self.combine(case)
                self.assert_rejected_without_side_effects(case, out, result,
                                                          "regular file")
        self.changelog.unlink()
        self.changelog.mkdir()
        result, out = self.combine(dist)
        self.assert_rejected_without_side_effects(dist, out, result, "regular file")

    def test_combine_rejects_symlinked_changelog_ancestor(self):
        self.stage_all()
        link = self.root / "changelog-link"
        link.symlink_to(self.source, target_is_directory=True)
        self.changelog = link / "CHANGELOG"
        dist = self.root / "dist"
        result, out = self.combine(dist)
        self.assert_rejected_without_side_effects(dist, out, result, "symlink")

    def test_combine_rejects_symlink_hidden_by_parent_path_component(self):
        self.stage_all()
        directory = self.root / "ordinary-directory"
        directory.mkdir()
        link = self.root / "path-link"
        link.symlink_to(directory, target_is_directory=True)
        result, out = self.combine(link / ".." / "dist")
        self.assert_rejected_without_side_effects(link / ".." / "dist", out,
                                                  result, "symlink")

    @unittest.skipUnless(os.name == "posix", "requires POSIX read permissions")
    @unittest.skipIf(hasattr(os, "geteuid") and os.geteuid() == 0,
                     "root bypasses POSIX read permissions")
    def test_combine_preflights_metadata_readability(self):
        self.stage_all()
        for metadata in METADATA_FILES:
            with self.subTest(metadata=metadata):
                dist = self.case_input(metadata)
                path = dist / "ppc" / metadata
                before = self.snapshot(self.root)
                mode = path.stat().st_mode
                path.chmod(0)
                try:
                    out = self.root / "merged"
                    result = subprocess.run(
                        [*PYTHON, str(SCRIPT), "combine",
                         "--dist", str(dist), "--output", str(out),
                         "--version", VERSION, "--changelog", str(self.changelog)],
                        text=True, capture_output=True, timeout=30,
                    )
                finally:
                    path.chmod(mode)
                self.assertEqual(self.snapshot(self.root), before)
                self.assert_rejected_without_side_effects(dist, out, result,
                                                          "unreadable")

    # --- input checksum list ------------------------------------------------

    def test_combine_rejects_incorrect_input_checksum_list(self):
        self.stage_all()
        dist = self.root / "dist"
        merged = self.root / "merged"
        sums = dist / "arm" / "SHA256SUMS"
        pristine = sums.read_text()
        lines = pristine.splitlines()
        stale = lines[:]
        stale[0] = ("f" * 64) + stale[0][64:]
        zero = lines[:]
        zero[0] = ("0" * 64) + zero[0][64:]
        cases = [
            ("stale-digest", "\n".join(stale) + "\n"),
            ("zero-digest", "\n".join(zero) + "\n"),
            ("missing-entry", "\n".join(lines[:-1]) + "\n"),
            ("duplicate-entry", "\n".join(lines + lines[:1]) + "\n"),
            ("empty-list", ""),
        ]
        for label, content in cases:
            with self.subTest(case=label):
                dist = self.case_input(label)
                sums = dist / "arm" / "SHA256SUMS"
                sums.write_text(content)
                before = self.snapshot(dist)
                result, out = self.combine(dist, output=merged)
                self.assert_rejected_without_side_effects(
                    dist, out, result, "checksum list mismatch")
                self.assertEqual(self.snapshot(dist), before)


def load_release_module():
    spec = importlib.util.spec_from_file_location("release_assets_profiles", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ProfileTests(Base):
    def stage_x86_all(self):
        payloads = self.make_sources("x86")
        result, output = self.stage("x86", profile="x86-all")
        self.assertEqual(result.returncode, 0, result.stderr)
        return output.parent, payloads

    def test_x86_all_exact_legacy_inventory_bytes_and_scoped_metadata(self):
        module = load_release_module()
        self.assertEqual(module.profile_architectures("x86-all"), ("x86",))
        self.assertEqual(module.expected_sources(VERSION, "x86", "x86-all"),
                         module.expected_sources(VERSION, "x86", "all"))
        self.assertCountEqual(module.expected_sources(VERSION, "x86", "x86-all"),
                              expected_sources("x86"))
        dist, payloads = self.stage_x86_all()
        self.assertEqual(len(payloads), 18)
        # Unrelated source products must not leak into this staged release.
        self.make_sources("arm64")
        result, output = self.combine(dist, profile="x86-all")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = {branded_name("x86", name) for name in payloads}
        for directory in (dist / "x86", output):
            self.assertEqual({p.name for p in directory.iterdir()}, expected | set(METADATA_FILES))
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(manifest["profile"], "x86-all")
            self.assertIs(manifest["boot_tested"], False)
            architectures = manifest.get("architectures", [manifest])
            self.assertEqual([m["architecture"] for m in architectures], ["x86"])
            self.assertEqual(architectures[0]["profile"], "x86-all")
            self.assertIs(architectures[0]["boot_tested"], False)
            self.assertEqual(len(architectures[0]["assets"]), 18)
            notes = (directory / "RELEASE_NOTES.md").read_text(encoding="utf-8")
            self.assertIn("x86 only, full product set (18 artifacts)", notes)
            self.assertNotIn("semua arsitektur", notes)
            self.assertNotIn("CHR x86 experimental", notes)
            for name, data in payloads.items():
                self.assertEqual((directory / branded_name("x86", name)).read_bytes(), data)
            checksums = (directory / "SHA256SUMS").read_text().splitlines()
            self.assertEqual(len(checksums), 18)
            for line in checksums:
                digest, name = line.split("  ")
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest)

    def test_x86_all_rejects_every_incompatible_architecture(self):
        module = load_release_module()
        self.make_sources("x86")
        for arch in [*ALL_ARCHS[1:], "unknown"]:
            with self.subTest(arch=arch):
                with self.assertRaises(ValueError):
                    module.expected_sources(VERSION, arch, "x86-all")
                result, output = self.stage(arch, profile="x86-all")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("unsupported architecture", result.stderr)
                self.assertFalse(output.exists())
                self.assertFalse(list(self.root.rglob(".ali-combine-*")))

    def test_x86_all_combine_rejects_scope_inventory_and_manifest_mismatches(self):
        dist, _ = self.stage_x86_all()
        asset = branded_name("x86", expected_sources("x86")[0])
        for label in ("wrong-arch", "extra-arch", "extra-asset", "missing-asset",
                      *METADATA_FILES, "profile-missing", "profile-all", "profile-chr",
                      "manifest-arch", "zero-size", "boot-tested"):
            with self.subTest(case=label):
                case = self.root / ("case-" + label)
                shutil.copytree(dist, case)
                if label == "wrong-arch":
                    (case / "x86").rename(case / "arm64")
                elif label == "extra-arch":
                    (case / "arm64").mkdir()
                elif label == "extra-asset":
                    (case / "x86" / "unexpected.npk").write_bytes(b"NOT FIRMWARE")
                elif label in ("missing-asset", *METADATA_FILES):
                    (case / "x86" / (asset if label == "missing-asset" else label)).unlink()
                else:
                    path = case / "x86" / "manifest.json"
                    manifest = json.loads(path.read_text())
                    if label == "profile-missing":
                        del manifest["profile"]
                    elif label.startswith("profile-"):
                        manifest["profile"] = "all" if label == "profile-all" else "chr-x86"
                    elif label == "manifest-arch":
                        manifest["architecture"] = "arm64"
                    elif label == "zero-size":
                        manifest["assets"][0]["size"] = 0
                    else:
                        manifest["boot_tested"] = True
                    path.write_text(json.dumps(manifest))
                result, output = self.combine(case, profile="x86-all")
                self.assertNotEqual(result.returncode, 0, result.stderr)
                self.assertFalse(output.exists())

    def test_x86_all_and_legacy_all_manifests_are_not_interchangeable(self):
        module = load_release_module()
        dist, _ = self.stage_x86_all()
        path = dist / "x86" / "manifest.json"
        for profile in ("all", "chr-x86"):
            with self.subTest(profile=profile), self.assertRaises(module.CombineError):
                module._validated_manifest(path, "x86", VERSION, profile)
        result, output = self.stage("x86", output=self.root / "legacy" / "x86")
        self.assertEqual(result.returncode, 0, result.stderr)
        result, merged = self.combine(output.parent, profile="x86-all")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("profile must be", result.stderr)
        self.assertFalse(merged.exists())

    def stage_chr(self):
        self.make_sources("x86", "chr-x86")
        result, output = self.stage("x86", profile="chr-x86")
        self.assertEqual(result.returncode, 0, result.stderr)
        return output.parent

    def test_chr_profile_contains_only_six_images_and_scoped_metadata(self):
        dist = self.stage_chr()
        expected = {branded_name("x86", name)
                    for name in expected_sources("x86", "chr-x86")}
        self.assertEqual(len(expected), 6)
        result, output = self.combine(dist, profile="chr-x86")
        self.assertEqual(result.returncode, 0, result.stderr)
        for directory in (dist / "x86", output):
            self.assertEqual({p.name for p in directory.iterdir()},
                             expected | set(METADATA_FILES))
            manifest = json.loads((directory / "manifest.json").read_text())
            self.assertEqual(manifest["profile"], "chr-x86")
            self.assertIs(manifest["boot_tested"], False)
            architectures = manifest.get("architectures", [manifest])
            self.assertEqual([m["architecture"] for m in architectures], ["x86"])
            self.assertEqual(architectures[0]["profile"], "chr-x86")
            notes = (directory / "RELEASE_NOTES.md").read_text(encoding="utf-8")
            self.assertIn("CHR x86 experimental", notes)
            self.assertNotIn("semua arsitektur", notes)
            for line in (directory / "SHA256SUMS").read_text().splitlines():
                digest, name = line.split("  ")
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), digest)

    def test_default_all_remains_strict_and_schema_compatible(self):
        module = load_release_module()
        self.assertEqual(module.expected_sources(VERSION, "x86"),
                         module.expected_sources(VERSION, "x86", "all"))
        self.make_sources("x86")
        result, output = self.stage("x86")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("profile", json.loads((output / "manifest.json").read_text()))
        result, _ = self.combine(output.parent)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing architecture", result.stderr)
        result, _ = self.combine(output.parent, profile="chr-x86")
        self.assertNotEqual(result.returncode, 0)

    def test_profile_api_without_namespace_profile(self):
        module = load_release_module()
        self.make_sources("x86", "chr-x86")
        args = module.parse_args([
            "stage", "--source", str(self.source), "--output", str(self.root / "dist" / "x86"),
            "--version", VERSION, "--arch", "x86", "--changelog", str(self.changelog)])
        del args.profile
        self.assertEqual(module.stage_assets(args, profile="chr-x86"), 0)
        combine_args = module.parse_args([
            "combine", "--dist", str(args.output.parent), "--output", str(self.root / "merged"),
            "--version", VERSION, "--changelog", str(self.changelog)])
        del combine_args.profile
        self.assertEqual(module.combine_assets(combine_args, profile="chr-x86"), 0)
        self.assertEqual(module.expected_sources(VERSION, "x86", "chr-x86"),
                         expected_sources("x86", "chr-x86"))

    def test_invalid_profile_and_architecture_fail_before_output(self):
        self.make_sources("x86", "chr-x86")
        for arch, profile in (("x86", "unknown"), ("arm64", "chr-x86")):
            result, output = self.stage(arch, profile=profile)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
        dist = self.root / "empty-dist"
        dist.mkdir()
        for profile in ("unknown", "chr-x86"):
            result, output = self.combine(dist, profile=profile)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
        module = load_release_module()
        with self.assertRaises(ValueError):
            module.expected_sources(VERSION, "arm", "chr-x86")
        with self.assertRaises(ValueError):
            module.expected_sources(VERSION, "x86", "unknown")

    def test_stage_rejects_missing_and_empty_assets_for_all_profiles(self):
        for profile in ("all", "chr-x86", "x86-all"):
            for kind in ("missing", "empty"):
                with self.subTest(profile=profile, kind=kind):
                    self.make_sources("x86", profile)
                    source = self.source / expected_sources("x86", profile)[-1]
                    source.unlink() if kind == "missing" else source.write_bytes(b"")
                    result, output = self.stage("x86", profile=profile)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())
                    self.assertFalse(list(self.root.rglob(".ali-combine-*")))

    def test_chr_combine_rejects_missing_extra_and_wrong_arch_inputs(self):
        dist = self.stage_chr()
        asset = branded_name("x86", expected_sources("x86", "chr-x86")[0])
        cases = ["missing-arch", "extra-arch", "extra-asset", "missing-asset", *METADATA_FILES]
        for label in cases:
            with self.subTest(case=label):
                case = self.root / ("case-" + label)
                shutil.copytree(dist, case)
                if label == "missing-arch":
                    (case / "x86").rename(case / "arm")
                elif label == "extra-arch":
                    (case / "arm").mkdir()
                elif label == "extra-asset":
                    (case / "x86" / "netinstall.zip").write_bytes(b"NOT FIRMWARE")
                else:
                    (case / "x86" / (asset if label == "missing-asset" else label)).unlink()
                result, output = self.combine(case, profile="chr-x86")
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())

    def test_chr_combine_rejects_profile_arch_and_positive_size_mismatches(self):
        dist = self.stage_chr()
        for label in ("profile-missing", "profile-all", "arch", "zero-size", "empty-body"):
            with self.subTest(case=label):
                case = self.root / label
                shutil.copytree(dist, case)
                path = case / "x86" / "manifest.json"
                manifest = json.loads(path.read_text())
                if label == "profile-missing":
                    del manifest["profile"]
                elif label == "profile-all":
                    manifest["profile"] = "all"
                elif label == "arch":
                    manifest["architecture"] = "arm"
                else:
                    manifest["assets"][0]["size"] = 0
                    if label == "empty-body":
                        entry = manifest["assets"][0]
                        (case / "x86" / entry["filename"]).write_bytes(b"")
                        entry["sha256"] = hashlib.sha256(b"").hexdigest()
                        (case / "x86" / "SHA256SUMS").write_text("\n".join(
                            f"{e['sha256']}  {e['filename']}" for e in manifest["assets"]) + "\n")
                path.write_text(json.dumps(manifest))
                result, output = self.combine(case, profile="chr-x86")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("manifest invalid", result.stderr)
                self.assertFalse(output.exists())

    def test_all_rejects_profile_field_even_with_complete_legacy_inventory(self):
        module = load_release_module()
        self.make_sources("x86")
        result, output = self.stage("x86")
        self.assertEqual(result.returncode, 0, result.stderr)
        path = output / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["profile"] = "chr-x86"
        path.write_text(json.dumps(manifest))
        with self.assertRaises(module.CombineError):
            module._validated_manifest(path, "x86", VERSION)

    def test_stage_copy_and_metadata_failures_clean_owned_temporary_output(self):
        module = load_release_module()
        self.make_sources("x86", "chr-x86")
        parent = self.root / "publish"
        parent.mkdir()
        output = parent / "release"
        argv = ["stage", "--source", str(self.source), "--output", str(output),
                "--version", VERSION, "--arch", "x86", "--profile", "chr-x86",
                "--changelog", str(self.changelog)]
        real_copy = shutil.copyfile
        real_write = Path.write_text
        for kind in ("copy", "metadata", "hash", "unsupported"):
            with self.subTest(kind=kind):
                before = self.snapshot(self.root)
                calls = []
                def fail_copy(src, dest):
                    calls.append(dest)
                    if len(calls) == 2:
                        raise OSError("synthetic copy failure")
                    return real_copy(src, dest)
                def fail_write(path, *args, **kwargs):
                    if path.name == "manifest.json":
                        raise OSError("synthetic metadata failure")
                    return real_write(path, *args, **kwargs)
                def fail_hash(path):
                    if path.parent.name.startswith(".ali-combine-"):
                        raise OSError("synthetic hash failure")
                    return hashlib.sha256(path.read_bytes()).hexdigest()
                target, replacement = {
                    "copy": ("shutil.copyfile", fail_copy),
                    "metadata": ("pathlib.Path.write_text", fail_write),
                    "hash": (None, fail_hash),
                    "unsupported": (None, None),
                }[kind]
                context = (mock.patch(target, side_effect=replacement, autospec=True) if target else
                           mock.patch.object(module, "sha256_of", side_effect=replacement)
                           if kind == "hash" else mock.patch.object(sys, "platform", "unsupported"))
                with context, redirect_stderr(io.StringIO()):
                    code = module.main(argv)
                self.assertNotEqual(code, 0)
                self.assertEqual(self.snapshot(self.root), before)

    def test_unsupported_combine_cleans_staging_without_loading_libc(self):
        module = load_release_module()
        dist = self.stage_chr()
        before = self.snapshot(self.root)
        with mock.patch.object(sys, "platform", "unsupported"), \
                mock.patch.object(module.ctypes, "CDLL") as libc, redirect_stderr(io.StringIO()):
            code = module.main([
                "combine", "--dist", str(dist), "--output", str(self.root / "merged"),
                "--version", VERSION, "--profile", "chr-x86", "--changelog", str(self.changelog)])
        self.assertNotEqual(code, 0)
        libc.assert_not_called()
        self.assertEqual(self.snapshot(self.root), before)

    @unittest.skipUnless(sys.platform == "win32", "requires native Windows rename semantics")
    def test_windows_publication_refuses_destination_created_after_precheck(self):
        module = load_release_module()
        real_rename = os.rename
        for kind in ("empty-dir", "file", "nonempty-dir", "dangling-link"):
            with self.subTest(kind=kind):
                staging = self.root / (".ali-combine-" + kind)
                staging.mkdir()
                (staging / "asset").write_bytes(b"SYNTHETIC")
                output = self.root / kind
                def race(src, dst):
                    if kind == "file":
                        output.write_bytes(b"KEEP")
                    elif kind == "dangling-link":
                        output.symlink_to(self.root / "absent", target_is_directory=True)
                    else:
                        output.mkdir()
                        if kind == "nonempty-dir":
                            (output / "keep").write_bytes(b"KEEP")
                    before = self.snapshot(self.root)
                    try:
                        return real_rename(src, dst)
                    finally:
                        self.assertEqual(self.snapshot(self.root), before)
                with mock.patch.object(os, "rename", side_effect=race), \
                        mock.patch.object(module.ctypes, "CDLL") as libc:
                    with self.assertRaises(OSError):
                        module._publish_output(staging, output)
                libc.assert_not_called()
                self.assertTrue(staging.is_dir())


if __name__ == "__main__":
    unittest.main()
