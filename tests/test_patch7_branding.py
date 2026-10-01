"""Regression checks for the pinned x86 release workflow (no firmware build)."""
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def workflow():
    return yaml.safe_load((ROOT / ".github/workflows/patch7.yml").read_text())


class WorkflowTests(unittest.TestCase):
    def test_routeros_target_is_pinned_to_7_23_3(self):
        self.assertEqual(workflow()["env"].get("PINNED_VERSION"), "7.23.3")

    def test_version_resolution_uses_pin_not_upstream_latest(self):
        run = workflow()["jobs"]["patch"]["steps"][3]["run"]
        self.assertIn("LATEST_VERSION=$PINNED_VERSION", run)
        self.assertNotIn("NEWESTa7.stable", run)

    def test_matrix_is_x86_only(self):
        archs = workflow()["jobs"]["patch"]["strategy"]["matrix"]["arch"]
        self.assertEqual(archs, ["x86"])

    def test_release_job_uses_shared_pin_not_previous_job_environment(self):
        release = workflow()["jobs"]["release"]
        self.assertNotIn("env.LATEST_VERSION", yaml.safe_dump(release))
        self.assertIn("env.PINNED_VERSION", yaml.safe_dump(release))

    def test_staged_artifact_is_used_by_opt_in_draft_release(self):
        config = workflow()
        trigger = config.get("on", config.get(True))
        options = trigger["workflow_dispatch"] or {}
        self.assertIn("create_draft_release", options.get("inputs", {}))
        self.assertIs(options["inputs"]["create_draft_release"]["default"], False)
        steps = config["jobs"]["patch"]["steps"]
        staging = next(s for s in steps if s.get("id") == "stage_release")
        self.assertIn("scripts/release_assets.py", staging["run"])
        self.assertIn('--version "$LATEST_VERSION"', staging["run"])
        upload = next(s for s in steps if s.get("uses", "").startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["path"], "dist/")
        self.assertEqual(upload["with"]["if-no-files-found"], "error")
        self.assertLess(steps.index(staging), steps.index(upload))
        self.assertEqual(config["permissions"]["contents"], "read")
        release = config["jobs"]["release"]
        self.assertEqual(release["needs"], "patch")
        self.assertIn("inputs.create_draft_release", release["if"])
        publish = next(s for s in release["steps"] if s.get("uses", "").startswith("softprops/action-gh-release@"))
        self.assertIs(publish["with"]["draft"], True)
        self.assertIs(publish["with"]["prerelease"], True)
        self.assertEqual(str(publish["with"]["make_latest"]).lower(), "false")
        self.assertIn("Ali Patch Code", publish["with"]["name"])
        self.assertIn("github.run_id", publish["with"]["tag_name"])
        self.assertEqual(publish["with"]["body_path"], "dist/RELEASE_NOTES.md")
        self.assertEqual(publish["with"]["files"], "dist/*")
        commands = "\n".join(s.get("run", "") for s in steps)
        self.assertNotIn("git push", commands)
        self.assertNotIn("latest7.txt", commands.replace("# Manual rebuilds must not be skipped because latest7.txt matches.", ""))


if __name__ == "__main__":
    unittest.main()
