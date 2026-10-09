"""Workflow regressions; optional real ISO packer tests use synthetic files only."""
import json
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALL_ARCHS = ["x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc", "tile"]


def workflow():
    config = yaml.safe_load((ROOT / ".github/workflows/patch7.yml").read_text(encoding="utf-8"))
    # Assertions must never print embedded key values, even on a failing test.
    config["env"] = {key: value for key, value in config["env"].items()
                     if key == "PINNED_VERSION"}
    return config


def condition_selected(condition, profile, arch, cache_hit="false", has_new_version="true"):
    condition = condition.replace("inputs.build_profile", repr(profile))
    condition = condition.replace("matrix.arch", repr(arch))
    condition = condition.replace("steps.get_latest.outputs.has_new_version", repr(has_new_version))
    condition = re.sub(r"steps\.cache_\w+\.outputs\.cache-hit", repr(cache_hit), condition)
    condition = condition.replace("&&", " and ").replace("||", " or ")
    if not re.fullmatch(r"[a-z0-9'()=!\s-]+|True", condition):
        raise ValueError("Unsupported test condition grammar")
    return eval(condition, {"__builtins__": {}}, {})


class WorkflowTests(unittest.TestCase):
    def test_routeros_target_is_pinned_to_7_24_4(self):
        self.assertEqual(workflow()["env"].get("PINNED_VERSION"), "7.24.5")

    def test_version_resolution_uses_pin_not_upstream_latest(self):
        run = next(s["run"] for s in workflow()["jobs"]["patch"]["steps"]
                   if s.get("id") == "get_latest")
        self.assertIn("LATEST_VERSION=$PINNED_VERSION", run)
        self.assertNotIn("NEWESTa7.stable", run)

    def test_profile_choice_defaults_to_all(self):
        config = workflow()
        trigger = config.get("on", config.get(True))
        profile = trigger["workflow_dispatch"]["inputs"]["build_profile"]
        self.assertEqual(profile["type"], "choice")
        self.assertIs(profile["required"], True)
        self.assertEqual(profile["default"], "all")
        self.assertEqual(profile["options"], ["all", "chr-x86", "x86-all"])

    def test_matrix_covers_all_repo_architectures(self):
        expression = workflow()["jobs"]["patch"]["strategy"]["matrix"]["arch"]
        match = re.fullmatch(
            r"\$\{\{ fromJSON\(\(inputs\.build_profile == 'chr-x86' "
            r"\|\| inputs\.build_profile == 'x86-all'\) && '([^']+)' "
            r"\|\| '([^']+)'\) \}\}", expression)
        self.assertIsNotNone(match, "Matrix must select only constant JSON arrays")
        self.assertEqual(json.loads(match[1]), ["x86"])
        self.assertEqual(json.loads(match[2]), ALL_ARCHS)

    def test_architecture_suffix_allowlist_matches_full_matrix_and_fails_closed(self):
        run = next(s["run"] for s in workflow()["jobs"]["patch"]["steps"]
                   if s.get("id") == "get_latest")
        self.assertEqual(re.findall(r'matrix\.arch \}\}" == "([a-z0-9]+)"', run), ALL_ARCHS)
        self.assertIn('elif [ "${{ matrix.arch }}" == "tile" ]; then\n  ARCH=\'-tile\'', run)
        self.assertIn("else\n  printf '%s\\n' 'Unsupported architecture' >&2\n  exit 1\nfi", run)

    def test_tile_selects_only_generic_package_products(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        for cache_hit in ("true", "false"):
            selected = [s for s in steps if condition_selected(
                s.get("if", "True"), "all", "tile", cache_hit)]
            products = [s for s in selected if s["name"].startswith(("Cache ", "Get ", "Patch "))]
            self.assertEqual(len(products), 2 if cache_hit == "true" else 3)
            self.assertTrue(all(s["name"].split()[1].startswith("routeros-") for s in products))
            patch = next(s for s in products if s["name"].startswith("Patch "))
            self.assertIn('patch.py npk routeros-$LATEST_VERSION$ARCH-patched.npk', patch["run"])
            self.assertNotIn("--runtime-policy", patch["run"])
            self.assertNotIn("--terminal-banner", patch["run"])

    def test_release_requires_successful_entire_matrix(self):
        release = workflow()["jobs"]["release"]
        self.assertEqual(release["needs"], "patch")
        self.assertEqual(release["if"], "success() && inputs.create_draft_release == true")
        self.assertNotIn("always()", release["if"])

    def test_profile_validation_precedes_build_and_rejects_unknown_values(self):
        first = workflow()["jobs"]["patch"]["steps"][0]
        self.assertEqual(first["env"]["BUILD_PROFILE"], "${{ inputs.build_profile }}")
        self.assertIn('case "$BUILD_PROFILE" in', first["run"])
        self.assertIn('all|chr-x86|x86-all) ;;', first["run"])
        self.assertRegex(first["run"], r'\*\).*exit 1')

    def test_non_chr_product_steps_enable_full_product_profiles(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        product_steps = [s for s in steps if s["name"].startswith(("Cache ", "Get ", "Patch "))]
        self.assertEqual(len(product_steps), 17)
        for step in product_steps:
            with self.subTest(step=step["name"]):
                if step["name"].split()[1].startswith("chr-"):
                    self.assertNotIn("build_profile", step["if"])
                    self.assertIn("(matrix.arch == 'x86' || matrix.arch == 'arm64')", step["if"])
                else:
                    self.assertTrue(step["if"].startswith("(inputs.build_profile == 'all' || "
                                                           "inputs.build_profile == 'x86-all') && "))
                self.assertIn("steps.get_latest.outputs.has_new_version == 'true'", step["if"])

    def test_chr_profile_runs_only_chr_and_shared_steps(self):
        # Evaluate only the documented condition grammar; no arbitrary workflow code.
        steps = workflow()["jobs"]["patch"]["steps"]
        shared = {
            "Validate build profile", "Checkout", "Setup Python", "Install dependencies",
            "Select pinned RouterOS version", "Stage branded release assets", "Upload branded artifacts",
        }
        for profile, archs in (("all", ALL_ARCHS), ("chr-x86", ["x86"]), ("x86-all", ["x86"])):
            for arch in archs:
                for cache_hit in ("true", "false"):
                    selected = []
                    for step in steps:
                        if condition_selected(step.get("if", "True"), profile, arch, cache_hit):
                            selected.append(step["name"])
                    with self.subTest(profile=profile, arch=arch, cache_hit=cache_hit):
                        self.assertTrue(shared.issubset(selected))
                        validator = "Validate all six CHR x86 archives (build only)"
                        self.assertEqual(validator in selected, arch == "x86")
                        products = [name for name in selected if name not in shared and name != validator]
                        self.assertTrue(products)
                        if profile == "chr-x86":
                            self.assertEqual(len(products), 2 if cache_hit == "true" else 3)
                            self.assertTrue(all(name.split()[1].startswith("chr-") for name in products))
                        else:
                            self.assertTrue(any(name.startswith("Patch routeros-") for name in products)
                                            if arch != "x86" else
                                            any(name.startswith("Patch install-image-") for name in products))

    def test_x86_all_preserves_every_full_x86_gate(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        for cache_hit in ("true", "false"):
            for has_new in ("true", "false"):
                selected = {}
                for profile in ("all", "x86-all"):
                    selected[profile] = [s["name"] for s in steps if condition_selected(
                        s.get("if", "True"), profile, "x86", cache_hit, has_new)]
                self.assertEqual(selected["all"], selected["x86-all"])
                if has_new == "true":
                    products = [name.split()[1] for name in selected["x86-all"]
                                if name.startswith("Patch ")]
                    self.assertEqual(products, [
                        "mikrotik-${{", "install-image-${{", "chr-${{", "netinstall"])
                    self.assertEqual(any(name.startswith("Get refind")
                                         for name in selected["x86-all"]), cache_hit == "false")
                else:
                    self.assertFalse(any(name.startswith(("Cache ", "Get ", "Patch ", "Upload "))
                                         for name in selected["x86-all"]))

    def test_chr_build_uses_strict_npk_guard_and_six_zipped_formats(self):
        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s["name"].startswith("Patch chr-"))
        run = step["run"]
        self.assertIn("sudo -E python3 patch.py npk chr/routeros/var/pdb/system/image", run)
        formats = re.findall(r"sudo zip chr-\$LATEST_VERSION\$ARCH-patched\.([a-z0-9]+)\.zip "
                             r"chr-\$LATEST_VERSION\$ARCH-patched\.\1", run)
        self.assertCountEqual(formats, ["img", "qcow2", "vmdk", "vhd", "vhdx", "vdi"])
        for forbidden in ("npk.py sign", "|| true", "continue-on-error", "refind", "install-image"):
            self.assertNotIn(forbidden, run)

    def test_chr_runtime_policy_is_scoped_to_x86_exact_version_and_internal_npk(self):
        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s["name"].startswith("Patch chr-"))
        # Keep the policy at this call site, not in a global option/environment.
        # The else branch deliberately preserves the generic path for ARM64 and
        # other versions if the workflow pin is changed in a future release.
        expected = '''sudo mount /dev/nbd0p2 chr/routeros/
if [ "${{ matrix.arch }}" == "x86" ] && [ "$LATEST_VERSION" == "7.24.5" ]; then
  sudo -E python3 patch.py npk --runtime-policy chr-x86-7.24.5 --terminal-banner chr-x86-7.24.4-ali-media-patch chr/routeros/var/pdb/system/image
else
  sudo -E python3 patch.py npk chr/routeros/var/pdb/system/image
fi
sudo umount /dev/nbd0p2'''
        self.assertIn(expected, step["run"])

    def test_runtime_policy_is_scoped_to_chr_and_x86_installer_commands(self):
        config = workflow()
        flagged = []
        for job_name, job in config["jobs"].items():
            for step in job["steps"]:
                for line in step.get("run", "").splitlines():
                    if "--runtime-policy" in line:
                        flagged.append((job_name, step["name"], line.strip()))
        self.assertEqual(len(flagged), 4)
        self.assertEqual([name.split()[1].split('-${{')[0] for _, name, _ in flagged],
                         ['mikrotik', 'mikrotik', 'install-image', 'chr'])
        self.assertEqual(flagged[-1], (
            "patch", "Patch chr-${{ env.LATEST_VERSION }}${{ env.ARCH }}.img",
            "sudo -E python3 patch.py npk --runtime-policy chr-x86-7.24.5 "
            "--terminal-banner chr-x86-7.24.4-ali-media-patch chr/routeros/var/pdb/system/image",
        ))
        # Also reject policy injection through env or elsewhere outside run blocks.
        serialized = yaml.safe_dump(config)
        self.assertEqual(serialized.count("--runtime-policy"), 4)
        self.assertEqual(serialized.count("x86-installer-7.24.5"), 3)
        self.assertEqual(serialized.count("chr-x86-7.24.5"), 1)
        self.assertEqual(serialized.count("--terminal-banner"), 1)
        self.assertEqual(serialized.count("chr-x86-7.24.4-ali-media-patch"), 1)
        run = next(s['run'] for s in config['jobs']['patch']['steps']
                   if s['name'].startswith('Patch chr-'))
        self.assertLess(run.index('--terminal-banner'), run.index('qemu-img convert'))

    def test_all_profiles_select_the_same_x86_chr_policy_step(self):
        config = workflow()
        step = next(s for s in config["jobs"]["patch"]["steps"]
                    if s["name"].startswith("Patch chr-"))
        self.assertEqual(step["if"], "steps.get_latest.outputs.has_new_version == 'true' "
                         "&& (matrix.arch == 'x86' || matrix.arch == 'arm64')")
        self.assertNotIn("build_profile", step["run"])
        selector = next(s["run"] for s in config["jobs"]["patch"]["steps"]
                        if s.get("id") == "get_latest")
        self.assertIn('echo "LATEST_VERSION=$LATEST_VERSION" >> "$GITHUB_ENV"', selector)
        self.assertEqual(re.findall(r"^LATEST_VERSION=(.*)$", selector, re.MULTILINE),
                         ["$PINNED_VERSION"])
        # Matrix/profile selection is checked above; no profile can bypass
        # this shared CHR step or resolve a version from an upstream latest feed.
        self.assertEqual(config["env"]["PINNED_VERSION"], "7.24.5")

    def test_no_guard_bypass_or_failure_suppression(self):
        for job in workflow()["jobs"].values():
            self.assertNotIn("continue-on-error", job)
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)
                run = step.get("run", "")
                for forbidden in ("npk.py sign", "|| true", "--skip-coverage", "--no-coverage"):
                    self.assertNotIn(forbidden, run)

    def test_all_package_members_use_guarded_npk_path(self):
        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s["name"].startswith("Patch routeros-"))
        run = step["run"]
        self.assertIn('for file in $NPK_FILES; do\n  sudo -E python3 patch.py npk "$file"\ndone', run)
        self.assertIn('patch.py npk routeros-$LATEST_VERSION$ARCH-patched.npk', run)
        self.assertIn('cd all_packages$ARCH-$LATEST_VERSION/\nsudo zip ../all_packages$ARCH-$LATEST_VERSION-patched.zip *.npk', run)

    def test_arm64_package_archive_has_one_authoritative_source(self):
        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s["name"].startswith("Patch mikrotik-"))
        run = step["run"]
        export = run[run.index('# Only x86 exports ISO packages.'):]
        self.assertIn('if [ "${{ matrix.arch }}" == "x86" ]; then', export)
        self.assertIn('sudo zip ../all_packages$ARCH-$LATEST_VERSION-patched.zip *', export)
        self.assertEqual(export.count('sudo zip '), 1)
        self.assertLess(export.index('sudo zip '), export.index('\nfi'))
        self.assertIn('\nfi\nsudo rm -rf new_iso/', export)

    def test_matrix_does_not_cancel_other_architectures(self):
        strategy = workflow()["jobs"]["patch"]["strategy"]
        self.assertIs(strategy.get("fail-fast"), False)

    @staticmethod
    def x86_iso_command():
        run = next(s["run"] for s in workflow()["jobs"]["patch"]["steps"]
                   if s["name"].startswith("Patch mikrotik-"))
        # Read the actual x86 packer invocation rather than a duplicate test command.
        command = re.search(r"^  sudo (xorriso -as mkisofs .*?new_iso/)$", run,
                            re.MULTILINE | re.DOTALL)
        if command is None:
            raise ValueError("x86 ISO command must use xorriso mkisofs emulation")
        return shlex.split(command[1].replace("\\\n", " "))

    def test_x86_iso_load_sizes_are_explicit_and_scoped_to_boot_entries(self):
        args = self.x86_iso_command()
        self.assertEqual(args[:3], ["xorriso", "-as", "mkisofs"])
        split = args.index("-eltorito-alt-boot")
        bios, efi = args[:split], args[split + 1:]
        self.assertEqual(bios[bios.index("-b") + 1], "isolinux/isolinux.bin")
        self.assertEqual(bios[bios.index("-c") + 1], "isolinux/boot.cat")
        self.assertEqual(bios[bios.index("-boot-load-size") + 1], "4")
        self.assertIn("-boot-info-table", bios)
        self.assertEqual(efi[efi.index("-e") + 1], "efiboot.img")
        self.assertLess(efi.index("-e"), efi.index("-boot-load-size"))
        self.assertEqual(efi[efi.index("-boot-load-size") + 1], "0")
        self.assertEqual(args.count("-boot-load-size"), 2)
        self.assertIn("-no-emul-boot", bios)
        self.assertIn("-no-emul-boot", efi)
        self.assertNotIn("-boot-info-table", efi)
        dependencies = next(s["run"] for s in workflow()["jobs"]["patch"]["steps"]
                            if "apt-get install" in s.get("run", ""))
        self.assertIn("xorriso", dependencies)

    @unittest.skipUnless(shutil.which("xorriso"), "xorriso not available")
    def test_real_x86_iso_catalog_keeps_bios_four_and_full_efi_image(self):
        # No firmware, signing or FAT tooling: catalog semantics depend on image
        # size, not filesystem contents. 34 MiB => 69632 sectors, which formerly
        # wrapped to 4096 in genisoimage's uint16 count. Include either side of
        # the 32 MiB boundary so the fix cannot depend on overflow or one size.
        for image_size in (1024 * 1024, 32 * 1024 * 1024, 34 * 1024 * 1024):
            with self.subTest(image_size=image_size), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                tree = root / "new_iso"
                (tree / "isolinux").mkdir(parents=True)
                (tree / "isolinux/isolinux.bin").write_bytes(bytes(4096))
                with (tree / "efiboot.img").open("wb") as image:
                    image.truncate(image_size)
                iso = root / "test.iso"
                args = self.x86_iso_command()
                args[args.index("-o") + 1] = str(iso)
                args[args.index("-V") + 1] = "Synthetic ISO regression"
                args[-1] = str(tree)
                subprocess.run(args, check=True, capture_output=True, timeout=60)
                with iso.open("rb") as stream:
                    # Locate El Torito via ISO9660 descriptors, never a fixed
                    # catalog LBA or an offset copied from a vendor ISO.
                    catalog_lba = None
                    for lba in range(16, 80):
                        stream.seek(lba * 2048)
                        descriptor = stream.read(2048)
                        self.assertEqual(descriptor[1:7], b"CD001\x01")
                        if descriptor[0] == 0 and descriptor[7:39].rstrip(b"\0") == b"EL TORITO SPECIFICATION":
                            self.assertIsNone(catalog_lba, "duplicate boot descriptor")
                            catalog_lba = struct.unpack_from("<I", descriptor, 71)[0]
                        if descriptor[0] == 255:
                            break
                    self.assertIsNotNone(catalog_lba, "missing El Torito descriptor")
                    stream.seek(catalog_lba * 2048)
                    catalog = stream.read(2048)
                self.assertEqual(catalog[:2], b"\x01\x00")  # validation: BIOS
                self.assertEqual(catalog[30:32], b"\x55\xaa")
                self.assertEqual(sum(struct.unpack("<16H", catalog[:32])) & 0xffff, 0)
                bios = catalog[32:64]
                self.assertEqual(bios[:2], b"\x88\x00")  # bootable, no emulation
                self.assertEqual(struct.unpack_from("<H", bios, 6)[0], 4)
                section = catalog[64:96]
                self.assertEqual(section[:2], b"\x91\xef")  # last section, EFI
                self.assertEqual(struct.unpack_from("<H", section, 2)[0], 1)
                efi = catalog[96:128]
                self.assertEqual(efi[:2], b"\x88\x00")
                expected_efi_sectors = (image_size // 512) if (image_size // 512) <= 0xffff else 0
                self.assertEqual(struct.unpack_from("<H", efi, 6)[0], expected_efi_sectors)
                # Verify that the whole EFI file remains in the ISO and the
                # boot catalog points to its full byte-identical extent.
                extracted = root / "efi-readback.img"
                subprocess.run(["xorriso", "-osirrox", "on", "-indev", str(iso),
                                "-extract", "/efiboot.img", str(extracted)],
                               check=True, capture_output=True, timeout=60)
                self.assertEqual(extracted.stat().st_size, image_size)
                self.assertEqual(extracted.read_bytes(), (tree / "efiboot.img").read_bytes())
                with iso.open("rb") as stream:
                    stream.seek(struct.unpack_from("<I", efi, 8)[0] * 2048)
                    self.assertEqual(stream.read(image_size), extracted.read_bytes())

    def test_dependencies_include_squashfs_tools(self):
        run = next(s["run"] for s in workflow()["jobs"]["patch"]["steps"]
                   if "apt-get install" in s.get("run", ""))
        self.assertIn("squashfs-tools", run)

    def test_staging_runs_per_architecture(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        staging = next(s for s in steps if s.get("id") == "stage_release")
        self.assertIn("release_assets.py stage", staging["run"])
        self.assertIn('--arch "${{ matrix.arch }}"', staging["run"])
        self.assertIn('--profile "${{ inputs.build_profile }}"', staging["run"])
        self.assertIn('--changelog CHANGELOG', staging["run"])
        self.assertIn("--output dist/${{ matrix.arch }}", staging["run"])

    def test_chr_integrity_validation_runs_after_stage_before_upload(self):
        import shlex

        steps = workflow()["jobs"]["patch"]["steps"]
        staging = next(s for s in steps if s.get("id") == "stage_release")
        validation = next(s for s in steps if s.get("id") == "validate_chr_image")
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(validation["if"],
                         "steps.get_latest.outputs.has_new_version == 'true' && matrix.arch == 'x86'")
        self.assertLess(steps.index(staging), steps.index(validation))
        self.assertLess(steps.index(validation), steps.index(upload))
        self.assertEqual(shlex.split(validation["run"].replace("\\\n", " ")), [
            "python3", "scripts/validate_chr_image.py",
            "--directory", "dist/x86", "--version", "$LATEST_VERSION",
            "--manifest", "dist/x86/manifest.json", "--checksums", "dist/x86/SHA256SUMS",
            "--qemu-img", "qemu-img",
        ])

    def test_profile_and_changelog_are_separate_cli_arguments(self):
        import shlex

        for job_name, step_id in (("patch", "stage_release"), ("release", "combine_release")):
            step = next(s for s in workflow()["jobs"][job_name]["steps"] if s.get("id") == step_id)
            command = step["run"][step["run"].index("python3 scripts/release_assets.py"):]
            command = command.replace("${{ inputs.build_profile }}", "chr-x86")
            command = command.replace("${{ matrix.arch }}", "x86")
            tokens = shlex.split(command.replace("\\\n", " "))
            with self.subTest(job=job_name):
                self.assertEqual(tokens[tokens.index("--profile") + 1:],
                                 ["chr-x86", "--changelog", "CHANGELOG"])

    def test_release_job_uses_shared_pin_not_previous_job_environment(self):
        release = workflow()["jobs"]["release"]
        self.assertNotIn("env.LATEST_VERSION", yaml.safe_dump(release))
        self.assertIn("env.PINNED_VERSION", yaml.safe_dump(release))

    def test_staged_artifacts_feed_opt_in_combined_draft_release(self):
        config = workflow()
        trigger = config.get("on", config.get(True))
        options = trigger["workflow_dispatch"] or {}
        self.assertIn("create_draft_release", options.get("inputs", {}))
        self.assertIs(options["inputs"]["create_draft_release"]["default"], False)
        steps = config["jobs"]["patch"]["steps"]
        staging = next(s for s in steps if s.get("id") == "stage_release")
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["name"],
                         "ali-patch-code-${{ matrix.arch }}-${{ env.LATEST_VERSION }}")
        self.assertEqual(upload["with"]["path"], "dist/${{ matrix.arch }}")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertLess(steps.index(staging), steps.index(upload))
        self.assertEqual(config["permissions"]["contents"], "read")
        release = config["jobs"]["release"]
        self.assertEqual(release["needs"], "patch")
        self.assertIn("inputs.create_draft_release", release["if"])
        download = next(s for s in release["steps"]
                        if s.get("uses", "").startswith("actions/download-artifact@"))
        self.assertEqual(download["with"]["pattern"],
                         "ali-patch-code-*-${{ env.PINNED_VERSION }}")
        self.assertEqual(download["with"]["path"], "dist-download")
        self.assertIs(download["with"]["merge-multiple"], False)
        combine = next(s for s in release["steps"] if s.get("id") == "combine_release")
        self.assertIn("release_assets.py combine", combine["run"])
        self.assertIn('--profile "${{ inputs.build_profile }}"', combine["run"])
        self.assertIn("mkdir release-input", combine["run"])
        self.assertIn('mv "$dir" "release-input/$arch"', combine["run"])
        self.assertNotIn("mkdir dist", combine["run"])
        self.assertIn("--dist release-input", combine["run"])
        self.assertIn("--output dist", combine["run"])
        self.assertIn('"$PINNED_VERSION"', combine["run"])
        publish = next(s for s in release["steps"]
                       if s.get("uses", "").startswith("softprops/action-gh-release@"))
        self.assertIs(publish["with"]["draft"], True)
        self.assertIs(publish["with"]["prerelease"], True)
        self.assertEqual(str(publish["with"]["make_latest"]).lower(), "false")
        self.assertIn("Ali Patch Code", publish["with"]["name"])
        self.assertIn("semua arsitektur", publish["with"]["name"])
        self.assertIn("inputs.build_profile == 'chr-x86'", publish["with"]["name"])
        self.assertIn("CHR x86 only, six formats", publish["with"]["name"])
        self.assertIn("inputs.build_profile == 'x86-all'", publish["with"]["name"])
        self.assertIn("x86 only, full product set (18 artifacts)", publish["with"]["name"])
        self.assertIn("untested", publish["with"]["name"])
        self.assertIn("github.run_id", publish["with"]["tag_name"])
        self.assertEqual(publish["with"]["body_path"], "dist/RELEASE_NOTES.md")
        self.assertEqual(publish["with"]["files"], "dist/*")
        self.assertLess(release["steps"].index(combine), release["steps"].index(publish))
        commands = "\n".join(s.get("run", "") for s in steps)
        self.assertNotIn("git push", commands)
        self.assertNotIn("latest7.txt",
                         commands.replace("# Manual rebuilds must not be skipped because latest7.txt matches.", ""))

    def test_release_reruns_resolve_to_distinct_tags(self):
        config = workflow()
        publish = next(s for s in config["jobs"]["release"]["steps"]
                       if s.get("uses", "").startswith("softprops/action-gh-release@"))
        tag_template = publish["with"]["tag_name"]
        run_id = "123456789"
        tags = [
            tag_template.replace("${{ env.PINNED_VERSION }}", config["env"]["PINNED_VERSION"])
            .replace("${{ github.run_id }}", run_id)
            .replace("${{ github.run_attempt }}", str(attempt))
            for attempt in (1, 2)
        ]
        self.assertNotEqual(tags[0], tags[1], "Reruns must not reuse an existing release tag")
        self.assertEqual(tags, [
            f"ali-patch-code-7.24.5-run{run_id}-attempt1",
            f"ali-patch-code-7.24.5-run{run_id}-attempt2",
        ])

    def test_release_tag_targets_exact_built_commit(self):
        publish = next(s for s in workflow()["jobs"]["release"]["steps"]
                       if s.get("uses", "").startswith("softprops/action-gh-release@"))
        self.assertEqual(publish["with"].get("target_commitish"), "${{ github.sha }}")

    def test_non_x86_package_urls_match_architecture(self):
        import shlex

        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s.get("name", "").startswith("Get routeros-"))
        self.assertIn("matrix.arch != 'x86'", step["if"])
        for arch in ALL_ARCHS[1:]:
            with self.subTest(arch=arch):
                suffix = "-" + arch
                run = (step["run"].replace("$LATEST_VERSION", "7.24.5")
                       .replace("$ARCH", suffix))
                commands = [shlex.split(line) for line in run.splitlines() if line.strip()]
                self.assertEqual(len(commands), 2)
                downloads = {}
                for tokens in commands:
                    self.assertEqual(tokens[:2], ["sudo", "curl"])
                    self.assertEqual(tokens.count("--output"), 1)
                    output = tokens[tokens.index("--output") + 1]
                    self.assertNotIn(output, downloads)
                    downloads[output] = tokens[-1]
                base = "https://download.mikrotik.com/routeros/7.24.5/"
                self.assertEqual(downloads, {
                    f"routeros-7.24.5{suffix}.npk": base + f"routeros-7.24.5{suffix}.npk",
                    f"all_packages{suffix}-7.24.5.zip": base + f"all_packages-{arch}-7.24.5.zip",
                })

    def test_x86_package_outputs_use_standalone_policy_and_patched_iso_archive(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        step = next(s for s in steps if s.get("name", "").startswith("Patch mikrotik-"))
        run = step['run']
        self.assertIn('if [ "${{ matrix.arch }}" == "x86" ]; then\n  sudo -E python3 -B - new_iso', run)
        self.assertIn('https://download.mikrotik.com/routeros/$LATEST_VERSION/routeros-$LATEST_VERSION.npk', run)
        self.assertIn('python3 -B patch.py npk routeros-$LATEST_VERSION.npk -O routeros-$LATEST_VERSION-patched.npk --runtime-policy x86-installer-7.24.5', run)
        export = run[run.index('# Only x86 exports ISO packages.'):]
        self.assertIn("-iname '*.npk' -exec cp -t all_packages_iso$ARCH-$LATEST_VERSION/ {} +", export)
        self.assertIn('sudo zip ../all_packages$ARCH-$LATEST_VERSION-patched.zip *', export)
        self.assertNotIn('patch.py', export)
        self.assertNotIn('--runtime-policy', export)

    def test_refind_download_uses_canonical_sourceforge_mirror_with_retries(self):
        step = next(s for s in workflow()["jobs"]["patch"]["steps"]
                    if s.get("name", "").startswith("Get refind"))
        run = step["run"]
        self.assertIn("https://downloads.sourceforge.net/project/refind/0.14.2/refind-bin-0.14.2.zip", run)
        self.assertNotIn("nchc.dl.sourceforge.net", run)

    def test_all_remote_downloads_fail_closed_and_retry_transient_errors(self):
        import shlex

        commands = []
        for job_name, job in workflow()["jobs"].items():
            for step in job["steps"]:
                # Join shell continuations before checking individual commands.
                run = step.get("run", "").replace("\\\n", " ")
                for line in run.splitlines():
                    tokens = shlex.split(line, comments=True)
                    if tokens and tokens[0] == "sudo":
                        tokens = tokens[1:]
                    if tokens and tokens[0] == "curl":
                        commands.append((job_name, step.get("name"), tokens))

        self.assertEqual(len(commands), 12)
        self.assertEqual({job for job, _, _ in commands}, {"patch", "release"})
        for job, step, tokens in commands:
            with self.subTest(job=job, step=step, output=tokens[-2:]):
                for flag in ("--fail", "--show-error", "--location", "--retry-all-errors"):
                    self.assertEqual(tokens.count(flag), 1)
                for flag, value in (("--retry", "5"), ("--retry-delay", "5"),
                                    ("--connect-timeout", "20"), ("--max-time", "600")):
                    self.assertEqual(tokens.count(flag), 1)
                    self.assertEqual(tokens[tokens.index(flag) + 1], value)
                self.assertEqual(tokens.count("--output"), 1)
                output = tokens[tokens.index("--output") + 1]
                self.assertTrue(output and not output.startswith("-"))
                self.assertNotIn("-o", tokens)


def installer_selector_sources():
    steps = workflow()['jobs']['patch']['steps']
    return [re.search(r"<<'PY'\n(.*?)\nPY", step['run'], re.DOTALL).group(1)
            for step in steps if step['name'].startswith(('Patch mikrotik-', 'Patch install-image-'))]


class InstallerSelectorTests(unittest.TestCase):
    ADDONS = {'calea', 'container', 'dude', 'gps', 'iot', 'openflow',
              'rose-storage', 'tr069-client', 'ups', 'user-manager', 'wireless'}
    PIN = 'd97831be323d1b2b0236f344fb9d275c3ed72b26432670753a8ea30bdd647394'

    def run_selector(self, context='new_iso', mutation=None, version='7.24.5', fail=False):
        # Execute exact workflow Python, replacing ONLY parsing, hashes, subprocess
        # with inert synthetic doubles; no firmware, credentials or signing.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / context
            root.mkdir()
            ids = types.SimpleNamespace(NAME_INFO=1, ARCHITECTURE=2, SIGNATURE=3)
            packages = {}
            names = self.ADDONS | {'system'}
            if context == 'install-image':
                names = names - {'user-manager'}
            for index, name in enumerate(sorted(names)):
                path = root / ('ROUTEROS.NPK' if name == 'system' else f'{index}.npk')
                path.write_bytes(b'SYNTHETIC, NOT FIRMWARE')
                info = types.SimpleNamespace(name=name, version='7.24.5.final')
                parts = [types.SimpleNamespace(id=1, data=info),
                         types.SimpleNamespace(id=2, data=b'i386'),
                         types.SimpleNamespace(id=3, data=b'signature'),
                         types.SimpleNamespace(id=2, data=b'I')]
                class Package(list):
                    _packages = []
                    _has_pkg = False
                packages[str(path)] = Package(parts)
            if mutation:
                mutation(root, packages)
            def part(package, part_id):
                matches = [p for p in package if p.id == part_id]
                if len(matches) != 1:
                    raise ValueError('missing or duplicate NPK part')
                return matches[0]
            npk = types.ModuleType('npk')
            npk.NpkPartID = ids
            npk.NovaPackage = types.SimpleNamespace(load=lambda path: packages[path])
            patch = types.ModuleType('patch')
            patch._part = part
            calls = []
            def run(command, check):
                calls.append(command)
                self.assertIs(check, True)
                if fail is True or (fail == 'system' and '--runtime-policy' in command):
                    import subprocess
                    raise subprocess.CalledProcessError(1, command)
            with mock.patch.dict(sys.modules, {'npk': npk, 'patch': patch}), \
                    mock.patch.object(sys, 'argv', ['-', str(root), version]), \
                    mock.patch('hashlib.sha256', return_value=types.SimpleNamespace(hexdigest=lambda: self.PIN)), \
                    mock.patch('subprocess.run', side_effect=run):
                try:
                    exec(compile(installer_selector_sources()[0], '<workflow-selector>', 'exec'), {})
                except Exception as error:
                    return calls, error
            return calls, None

    def test_both_workflow_selectors_are_identical_and_read_only(self):
        sources = installer_selector_sources()
        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0], sources[1])
        self.assertIn('package._packages or package._has_pkg', sources[0])
        self.assertIn('_part(package, NpkPartID.NAME_INFO)', sources[0])
        self.assertNotIn('package[NpkPartID', sources[0])
        self.assertNotIn('assert ', sources[0])
        self.assertNotIn('save(', sources[0])

    def test_exact_iso_and_fat_inventory_select_only_system_policy(self):
        for context, count in (('new_iso', 12), ('install-image', 11)):
            with self.subTest(context=context):
                calls, error = self.run_selector(context)
                self.assertIsNone(error)
                self.assertEqual(len(calls), count)
                flagged = [c for c in calls if '--runtime-policy' in c]
                self.assertEqual(len(flagged), 1)
                self.assertTrue(flagged[0][4].endswith('ROUTEROS.NPK'))
                self.assertEqual(flagged[0][-2:], ['--runtime-policy', 'x86-installer-7.24.5'])
                self.assertTrue(all(c[:4] == [sys.executable, '-B', 'patch.py', 'npk'] for c in calls))
                self.assertTrue(all(len(c) == 5 for c in calls if c not in flagged))

    def test_unknown_missing_duplicate_and_multipackage_fail_before_any_patch(self):
        def mutate_name(name):
            return lambda root, packages: setattr(next(iter(packages.values()))[0].data, 'name', name)
        def missing(root, packages):
            next(root.glob('*.NPK')).unlink()
        def duplicate_info(root, packages):
            pkg = next(iter(packages.values()))
            pkg.append(pkg[0])
        def multipackage(root, packages):
            next(iter(packages.values()))._packages = [object()]
        def feature_marker(root, packages):
            next(iter(packages.values()))._has_pkg = True
        def wrong_version(root, packages):
            next(iter(packages.values()))[0].data.version = '7.24.4.final'
        def wrong_arch(root, packages):
            next(iter(packages.values()))[1].data = b'arm'
        def duplicate_arch(root, packages):
            next(iter(packages.values())).append(types.SimpleNamespace(id=2, data=b'i386'))
        for mutation in (mutate_name('unknown'), mutate_name('system'), missing,
                         duplicate_info, multipackage, feature_marker, wrong_version,
                         wrong_arch, duplicate_arch):
            with self.subTest(mutation=mutation):
                calls, error = self.run_selector(mutation=mutation)
                self.assertIsInstance(error, ValueError)
                self.assertEqual(calls, [])

    def test_wrong_context_or_version_and_unqualified_system_fail_closed(self):
        for context, version in (('other', '7.24.5'), ('new_iso', '7.24.4')):
            calls, error = self.run_selector(context=context, version=version)
            self.assertIsInstance(error, ValueError)
            self.assertEqual(calls, [])
        with mock.patch.object(self, 'PIN', '0' * 64):
            calls, error = self.run_selector()
            self.assertIsInstance(error, ValueError)
            self.assertEqual(calls, [])

    def test_full_fat_shell_rejects_bad_inputs_before_any_boot_or_npk_write(self):
        import os
        import shlex
        import shutil
        import subprocess
        bash = shutil.which('bash')
        if bash is None:
            self.skipTest('requires bash for full-step ordering regression')
        step = next(s for s in workflow()['jobs']['patch']['steps']
                    if s['name'].startswith('Patch install-image-'))
        # All sudo operations are inert except the selector, whose exact stdin
        # runs with synthetic parser/hash/subprocess doubles. No mounts or writes
        # to firmware occur; attempted boot/NPK writes are recorded, not executed.
        runner_source = '''import hashlib, json, os, sys, types
from pathlib import Path
log = Path('attempts.log')
def record(text):
    with log.open('a') as f:
        f.write(text + '\\n')
scenario = os.environ['SELECTOR_SCENARIO']
ids = types.SimpleNamespace(NAME_INFO=1, ARCHITECTURE=2, SIGNATURE=3)
class Package(list):
    _packages = []
    _has_pkg = False
def load(path):
    name = Path(path).stem
    info = types.SimpleNamespace(name=name, version='7.24.5.final')
    if scenario == 'metadata' and name == 'calea':
        info.version = '7.24.4.final'
    return Package([types.SimpleNamespace(id=1, data=info),
                    types.SimpleNamespace(id=2, data=b'i386'),
                    types.SimpleNamespace(id=3, data=b'signature'),
                    types.SimpleNamespace(id=2, data=b'I')])
def part(package, ident):
    matches = [p for p in package if p.id == ident]
    if len(matches) != 1:
        raise ValueError('missing or duplicate part')
    return matches[0]
npk = types.ModuleType('npk')
npk.NovaPackage = types.SimpleNamespace(load=load)
npk.NpkPartID = ids
patch = types.ModuleType('patch')
patch._part = part
sys.modules.update(npk=npk, patch=patch)
pin = '0' * 64 if scenario == 'wire' else 'd97831be323d1b2b0236f344fb9d275c3ed72b26432670753a8ea30bdd647394'
hashlib.sha256 = lambda data: types.SimpleNamespace(hexdigest=lambda: pin)
import subprocess
subprocess.run = lambda command, check: record('NPK ' + json.dumps(command))
sys.argv = ['-', 'install-image', os.environ['LATEST_VERSION']]
record('selector-start')
exec(compile(sys.stdin.read(), '<full-step-selector>', 'exec'), {})
record('selector-done')
'''
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runner = root / 'inert-selector.py'
            runner.write_text(runner_source)
            image = root / 'install-image'
            image.mkdir()
            harness = '''set -e
sudo() {
  printf 'sudo %s\\n' "$*" >> attempts.log
  if [ "$1" = "-E" ] && [ "$2" = "python3" ] && [ "$3" = "-B" ] && [ "$4" = "-" ]; then
    ''' + shlex.quote(Path(sys.executable).as_posix()) + (' -O' if sys.flags.optimize else '') + ' -B ' + shlex.quote(runner.as_posix()) + '''
  fi
}
'''
            for scenario in ('incomplete', 'metadata', 'wire', 'version', 'valid'):
                with self.subTest(scenario=scenario):
                    for path in image.iterdir():
                        path.unlink()
                    names = {'calea'} if scenario == 'incomplete' else (self.ADDONS - {'user-manager'}) | {'system'}
                    for name in names:
                        (image / f'{name}.npk').write_bytes(b'SYNTHETIC NOT FIRMWARE')
                    (root / 'attempts.log').write_text('')
                    env = {**os.environ, 'SELECTOR_SCENARIO': scenario,
                           'LATEST_VERSION': '7.24.4' if scenario == 'version' else '7.24.5',
                           'ARCH': '', 'PYTHONDONTWRITEBYTECODE': '1'}
                    result = subprocess.run([bash], input=(harness + step['run']).encode(),
                                            cwd=root, env=env, capture_output=True, timeout=30)
                    attempts = (root / 'attempts.log').read_text().splitlines()
                    writes = [line for line in attempts if line.startswith(('NPK ', 'sudo cp '))
                              or 'patch.py kernel' in line]
                    if scenario == 'valid':
                        self.assertEqual(result.returncode, 0, result.stderr.decode())
                        self.assertEqual(sum(line.startswith('NPK ') for line in writes), 11)
                        self.assertTrue(any('BOOTX64.EFI' in line for line in writes))
                        self.assertTrue(any('patch.py kernel' in line for line in writes))
                        done = attempts.index('selector-done')
                        self.assertTrue(all(attempts.index(line) > done for line in writes
                                            if not line.startswith('NPK ')))
                    else:
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn('selector-start', attempts)
                        self.assertEqual(writes, [], 'rejection must precede all firmware write attempts')

    def test_patch_subprocess_failure_propagates_without_retry_or_generic_fallback(self):
        import subprocess
        calls, error = self.run_selector(fail='system')
        self.assertIsInstance(error, subprocess.CalledProcessError)
        self.assertTrue(any('--runtime-policy' in c for c in calls))
        self.assertFalse(any(len(c) == 5 and c[4].endswith('ROUTEROS.NPK') for c in calls))


if __name__ == "__main__":
    unittest.main()
