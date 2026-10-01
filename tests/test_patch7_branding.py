"""Regression checks for the pinned multi-arch release workflow (no firmware build)."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ALL_ARCHS = ["x86", "arm", "arm64", "mipsbe", "mmips", "smips", "ppc"]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/patch7.yml").read_text())


class WorkflowTests(unittest.TestCase):
    def test_routeros_target_is_pinned_to_7_23_3(self):
        self.assertEqual(workflow()["env"].get("PINNED_VERSION"), "7.23.3")

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
            f"ali-patch-code-7.23.3-run{run_id}-attempt1",
            f"ali-patch-code-7.23.3-run{run_id}-attempt2",
        ])

    def test_release_tag_targets_exact_built_commit(self):
        publish = next(s for s in workflow()["jobs"]["release"]["steps"]
                       if s.get("uses", "").startswith("softprops/action-gh-release@"))
        self.assertEqual(publish["with"].get("target_commitish"), "${{ github.sha }}")


if __name__ == "__main__":
    unittest.main()
