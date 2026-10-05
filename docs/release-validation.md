# Release validation gates

This is an authorized lab build process, not an official MikroTik licensing service.
A successful build, signature check, or unit test is **not** evidence of boot,
login, upgrade compatibility, or activation. Do not promise activation.

## Profiles and fail-closed scope

The manual `patch7.yml` workflow pins RouterOS `7.24.4`. Its required
`build_profile` choice defaults to `all`; the first build step rejects unknown
or empty values. API callers should explicitly send a supported profile.

- `all`: all seven architectures (`x86`, `arm`, `arm64`, `mipsbe`, `mmips`,
  `smips`, `ppc`) and their existing package/image sets. This is not an alias for
  whichever architectures happen to pass. Any architecture failure blocks the
  combined release; do not bypass coverage to obtain a green run.
- `chr-x86`: only `x86`, and only CHR images in six ZIP containers: `img`,
  `qcow2`, `vmdk`, `vhd`, `vhdx`, `vdi`. ISO, rEFInd, install-image, NetInstall,
  and standalone RouterOS/all-packages cache/download/patch steps are disabled.
  Version selection and CHANGELOG retrieval still run. This narrower scope is
  explicit, not evidence that the omitted architectures or installers work.

Both staging and combining receive `--profile`. Their inventories must match
that profile, with no missing required files or extra architecture directories.
`chr-x86` requires the six CHR ZIPs and an x86-only combined input. Manifests,
checksums, and release notes are metadata, not additional firmware formats.

After staging and before uploading, both profiles validate the x86 CHR VMDK
candidate with `scripts/validate_chr_image.py`, using the ZIP, `manifest.json`
and `SHA256SUMS` under `dist/x86`. This is an archive-integrity gate (hash, size,
expected nonempty ZIP member, CRC and image magic), not runtime, package coverage,
signature, boot or activation evidence.

The CHR internal system image and every NPK in downloaded all-packages archives
use `patch.py npk`. This preserves the [coverage contract](patch-coverage.md),
including failure before signing when a required system mapping has no match.
The standalone `npk.py sign` command is not a substitute for this validation.
Kernel/block/NetInstall operations do not independently provide the NPK-level
guarantee. Only x86 exports the ISO package collection; ARM64's all-packages ZIP
has one authoritative source, the separately downloaded and guarded package set,
so ZIP update semantics cannot retain old ISO-only members.

## Evidence must stay separate

Record sanitized evidence tied to the exact source commit, run ID and attempt,
profile, version, architecture, file name, size, and SHA-256. Never log key
values, passwords, tokens, or raw credential-helper output.

| Gate | What passing proves | What it does not prove |
| --- | --- | --- |
| Static/unit tests | Tested workflow selection and synthetic inventory/guard contracts | A real firmware build or GitHub Actions execution |
| Build and inventory | Required artifacts were produced for the chosen profile | Correct runtime behavior |
| Coverage | Required mappings matched the supported package representation | Every verifier was transformed, or activation works |
| Signature/checksum | The specific bytes verify against the intended test identity/digest | Vendor authenticity or successful boot |
| Boot | An identified image boots in the recorded VM configuration | Login, installation, upgrade, or activation |
| Login | The identified booted instance accepts the tested login | License activation |
| Activation | Only the exact observed device/version/test result | A guarantee for other images or devices |

A skipped test is not a pass. Existing release assets and historical VM reports
must not be attributed to a new source revision without matching provenance.

## Manual authenticated gates — not executed here

1. Obtain owner approval before pushing source, dispatching a remote build, or
   creating a draft. Review the exact commit and sanitized diff. Confirm suitable
   authorized lab key configuration without printing or silently changing it;
   legacy keys are not production keys.
2. In an authenticated GitHub session, dispatch the approved revision with
   `build_profile=chr-x86` and `create_draft_release=false` for the scoped build,
   or explicitly choose `all` for full coverage. Do not treat a CHR-only run as a
   full build. Capture run URL, commit, profile and attempt.
3. Require all selected jobs and strict inventory checks to succeed. Download
   artifacts from that run, verify checksums and expected names/ZIP members,
   retain sanitized coverage/signature results, and investigate failures rather
   than bypassing guards. An `all` run must include all seven architectures.
4. Use isolated disposable VMs with snapshots and non-production data. Record
   image hashes, hypervisor/version, BIOS/UEFI, controller/NIC and boot source.
   Test boot, login and any authorized activation separately. Test install/upgrade
   paths separately if making those claims; a CHR image cannot validate an ISO.
5. Only after separate approval, an authenticated run may opt into
   `create_draft_release=true`. The workflow creates an **untested draft
   prerelease**, not a published release or Latest. Titles identify CHR x86-only
   versus all architectures. Tags include version, run ID and attempt and target
   the built commit. Inspect the draft and evidence before any later manual
   publication decision. Publication is not performed by this change and remains
   pending runtime validation and explicit owner approval.

Never move an existing firmware tag or replace old release assets to conceal a
new build. A failed build or unproven activation remains reported as such.

## Recorded candidate audit (2026-10-05)

The existing Actions candidate from source `c636fa6`, run `37207497763`, was
checked separately from these local workflow changes. Its selected VMDK ZIP
passed complete member hashing, manifest/checksum comparison and CRC, but the
isolated QEMU test did **not** reach login within 240 seconds. Screenshot OCR
reported a services startup stall, timeout and reboot sequence. Visual image
confirmation was unavailable. At that initial checkpoint the matched old-image
control download exceeded the time budget; it was subsequently resumed and
verified. The old release reached the serial login prompt in the matched
240-second control. Activation was not attempted on the failed CI candidate.

A subsequent paired scratch experiment from the same pinned vendor input found
that replacing the license anchor in `nova/bin/loader` triggered the boot
regression in that pair. Retaining that anchor, while preserving actual
replacement counts and package coverage checks, reached login throughout the
240-second observation. A subsequent completed isolated activation trial
observed `free` becoming `p-unlimited`, retained through two guest reboots with
the same ID and a clean shutdown/new QEMU process. Cold-restart ID equality was
not evaluated; no immediate acceptance message was captured. Three earlier
console-helper failures remain recorded as incomplete, not license rejection.

This is still a diagnostic build, not yet the final production-patcher artifact.
See [the paired experiment](evidence/chr-7.24.4-loader-anchor-experiment-2026-10-05.json),
[activation evidence](evidence/chr-7.24.4-loader-preserved-activation-2026-10-05.json)
and HANDOFF §16. These QEMU results are not a VMware, other-architecture,
upgrade, bandwidth or long-duration compatibility conclusion.

Both published release bodies now warn that their unchanged historical assets
are not an activation fix. No source was pushed and no new firmware, draft, or
release was published. See [HANDOFF §15](HANDOFF.md#15-audit-rilis-perbaikan-pipeline-lokal-dan-uji-kandidat-nyata-2026-10-05)
and [sanitized evidence](evidence/release-audit-2026-10-05.json) for precise
hashes, tests, remote metadata comparisons and remaining limits.

## Local verification of the workflow change

Reference source before these uncommitted changes: `6071aea0a8059aa4378d56d0e41918ef6bd4bf3b`.
On the Windows working tree, using the project interpreter:

```text
venv/Scripts/python.exe -B -m unittest discover -s tests -p test_patch7_branding.py -v
```

Result: **24 tests passed, 0 skipped**. These are static workflow regressions,
including both profile selections, all non-CHR product gates, six CHR ZIP paths,
guarded NPK calls, ARM64 archive provenance, and draft/tag defaults. Early local
iterations had YAML-quoting errors and an incorrect expected step count; both
were corrected before this successful run.

Additional local checks: YAML parsed, all 17 workflow shell blocks passed
`bash -n` with LF byte input, and the profile-validation shell accepted `all` and
`chr-x86` and rejected empty/unknown values (four cases). Initial shell probes
were affected by Windows text-mode CRLF and environment forwarding; corrected
LF input and explicit shell assignments passed. Sensitive workflow assignments
were compared to the reference commit without printing their values and were
unchanged. `git diff --check` passed.

No firmware build, authenticated GitHub dispatch, remote draft, publication,
real-image signature verification, VM boot/login, upgrade, or activation test
was run for this workflow-only verification. The full repository suite was not
rerun by the workflow author; release-helper tests and broader platform-dependent
results must be reported separately by their runner.
