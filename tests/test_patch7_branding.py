"""Regression checks for the pinned multi-arch release workflow (no firmware build)."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALL_ARCHS = ["x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc"]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/patch7.yml").read_text())


class WorkflowTests(unittest.TestCase):
    def test_routeros_target_is_pinned_to_7_24_4(self):
        self.assertEqual(workflow()["env"].get("PINNED_VERSION"), "7.24.4")

    def test_version_resolution_uses_pin_not_upstream_latest(self):
        run = workflow()["jobs"]["patch"]["steps"][3]["run"]
        self.assertIn("LATEST_VERSION=$PINNED_VERSION", run)
        self.assertNotIn("NEWESTa7.stable", run)

    def test_matrix_covers_all_repo_architectures(self):
        archs = workflow()["jobs"]["patch"]["strategy"]["matrix"]["arch"]
        self.assertEqual(archs, ALL_ARCHS)

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
        self.assertIn("--output dist/${{ matrix.arch }}", staging["run"])

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
