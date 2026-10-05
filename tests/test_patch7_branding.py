"""Regression checks for the pinned multi-arch release workflow (no firmware build)."""
import json
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALL_ARCHS = ["x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc"]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/patch7.yml").read_text(encoding="utf-8"))


class WorkflowTests(unittest.TestCase):
    def test_routeros_target_is_pinned_to_7_24_4(self):
        self.assertEqual(workflow()["env"].get("PINNED_VERSION"), "7.24.4")

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
        self.assertEqual(profile["options"], ["all", "chr-x86"])

    def test_matrix_covers_all_repo_architectures(self):
        expression = workflow()["jobs"]["patch"]["strategy"]["matrix"]["arch"]
        match = re.fullmatch(
            r"\$\{\{ fromJSON\(inputs\.build_profile == 'chr-x86' && '([^']+)' "
            r"\|\| '([^']+)'\) \}\}", expression)
        self.assertIsNotNone(match, "Matrix must select only constant JSON arrays")
        self.assertEqual(json.loads(match[1]), ["x86"])
        self.assertEqual(json.loads(match[2]), ALL_ARCHS)

    def test_profile_validation_precedes_build_and_rejects_unknown_values(self):
        first = workflow()["jobs"]["patch"]["steps"][0]
        self.assertEqual(first["env"]["BUILD_PROFILE"], "${{ inputs.build_profile }}")
        self.assertIn('case "$BUILD_PROFILE" in', first["run"])
        self.assertIn('all|chr-x86) ;;', first["run"])
        self.assertRegex(first["run"], r'\*\).*exit 1')

    def test_all_non_chr_product_steps_are_all_profile_only(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        product_steps = [s for s in steps if s["name"].startswith(("Cache ", "Get ", "Patch "))]
        self.assertEqual(len(product_steps), 17)
        for step in product_steps:
            with self.subTest(step=step["name"]):
                if step["name"].split()[1].startswith("chr-"):
                    self.assertNotIn("build_profile", step["if"])
                    self.assertIn("(matrix.arch == 'x86' || matrix.arch == 'arm64')", step["if"])
                else:
                    self.assertTrue(step["if"].startswith("inputs.build_profile == 'all' && "))
                self.assertIn("steps.get_latest.outputs.has_new_version == 'true'", step["if"])

    def test_chr_profile_runs_only_chr_and_shared_steps(self):
        # Evaluate only the documented condition grammar; no arbitrary workflow code.
        steps = workflow()["jobs"]["patch"]["steps"]
        shared = {
            "Validate build profile", "Checkout", "Setup Python", "Install dependencies",
            "Select pinned RouterOS version", "Stage branded release assets", "Upload branded artifacts",
        }
        for profile, archs in (("all", ALL_ARCHS), ("chr-x86", ["x86"])):
            for arch in archs:
                for cache_hit in ("true", "false"):
                    selected = []
                    for step in steps:
                        condition = step.get("if", "True")
                        condition = condition.replace("inputs.build_profile", repr(profile))
                        condition = condition.replace("matrix.arch", repr(arch))
                        condition = condition.replace("steps.get_latest.outputs.has_new_version", "'true'")
                        condition = re.sub(r"steps\.cache_\w+\.outputs\.cache-hit", repr(cache_hit), condition)
                        condition = condition.replace("&&", " and ").replace("||", " or ")
                        self.assertRegex(condition, r"^[a-z0-9'()=!\s-]+$|^True$")
                        if eval(condition, {"__builtins__": {}}, {}):
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
if [ "${{ matrix.arch }}" == "x86" ] && [ "$LATEST_VERSION" == "7.24.4" ]; then
  sudo -E python3 patch.py npk --runtime-policy chr-x86-7.24.4 --terminal-banner chr-x86-7.24.4-ali-media-patch chr/routeros/var/pdb/system/image
else
  sudo -E python3 patch.py npk chr/routeros/var/pdb/system/image
fi
sudo umount /dev/nbd0p2'''
        self.assertIn(expected, step["run"])

    def test_runtime_policy_occurs_only_on_chr_internal_npk_command(self):
        config = workflow()
        flagged = []
        for job_name, job in config["jobs"].items():
            for step in job["steps"]:
                for line in step.get("run", "").splitlines():
                    if "--runtime-policy" in line:
                        flagged.append((job_name, step["name"], line.strip()))
        self.assertEqual(flagged, [(
            "patch", "Patch chr-${{ env.LATEST_VERSION }}${{ env.ARCH }}.img",
            "sudo -E python3 patch.py npk --runtime-policy chr-x86-7.24.4 "
            "--terminal-banner chr-x86-7.24.4-ali-media-patch chr/routeros/var/pdb/system/image",
        )])
        # Also reject policy injection through env or elsewhere outside run blocks.
        serialized = yaml.safe_dump(config)
        self.assertEqual(serialized.count("--runtime-policy"), 1)
        self.assertEqual(serialized.count("chr-x86-7.24.4"), 2)
        self.assertEqual(serialized.count("--terminal-banner"), 1)
        self.assertEqual(serialized.count("chr-x86-7.24.4-ali-media-patch"), 1)
        run = next(s['run'] for s in config['jobs']['patch']['steps']
                   if s['name'].startswith('Patch chr-'))
        self.assertLess(run.index('--terminal-banner'), run.index('qemu-img convert'))

    def test_both_profiles_select_the_same_x86_chr_policy_step(self):
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
        # Matrix/profile selection is checked above; neither profile can bypass
        # this shared CHR step or resolve a version from an upstream latest feed.
        self.assertEqual(config["env"]["PINNED_VERSION"], "7.24.4")

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
        self.assertIn('sudo zip ../all_packages$ARCH-$LATEST_VERSION-patched.zip *.npk', export)
        self.assertEqual(export.count('sudo zip '), 1)
        self.assertLess(export.index('sudo zip '), export.index('\nfi'))
        self.assertIn('\nfi\nsudo rm -rf new_iso/', export)

    def test_matrix_does_not_cancel_other_architectures(self):
        strategy = workflow()["jobs"]["patch"]["strategy"]
        self.assertIs(strategy.get("fail-fast"), False)

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
            f"ali-patch-code-7.24.4-run{run_id}-attempt1",
            f"ali-patch-code-7.24.4-run{run_id}-attempt2",
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
                run = (step["run"].replace("$LATEST_VERSION", "7.24.4")
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
                base = "https://download.mikrotik.com/routeros/7.24.4/"
                self.assertEqual(downloads, {
                    f"routeros-7.24.4{suffix}.npk": base + f"routeros-7.24.4{suffix}.npk",
                    f"all_packages{suffix}-7.24.4.zip": base + f"all_packages-{arch}-7.24.4.zip",
                })

    def test_x86_package_outputs_are_derived_from_iso(self):
        steps = workflow()["jobs"]["patch"]["steps"]
        step = next(s for s in steps if s.get("name", "").startswith("Patch mikrotik-"))
        self.assertIn("matrix.arch == 'x86'", step["if"])
        self.assertIn("sudo cp new_iso/routeros-$LATEST_VERSION*.npk routeros-$LATEST_VERSION$ARCH-patched.npk", step["run"])
        self.assertIn("sudo cp new_iso/*.npk all_packages_iso$ARCH-$LATEST_VERSION/", step["run"])
        self.assertIn("cd all_packages_iso$ARCH-$LATEST_VERSION/", step["run"])
        self.assertIn("sudo zip ../all_packages$ARCH-$LATEST_VERSION-patched.zip *.npk", step["run"])

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

        self.assertEqual(len(commands), 11)
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


if __name__ == "__main__":
    unittest.main()
