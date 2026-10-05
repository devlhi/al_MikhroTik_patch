# RouterOS x86 7.24.4 — static NIC/SFP driver findings

Inspection timestamp: 2026-10-05 (execution environment UTC; supplied conversation date was 2026-10-04).
Reference source HEAD: `bb010811bd1443334ed32b0d3168ef09b77bc111`, branch `main`, initially 0/0 against cached upstream. No remote refresh, commit, push, build, activation, or target execution.

## Scope and provenance

Read `HANDOFF.md` and `sfp-power.md`. Per this task's explicit exception, **HANDOFF and existing source were not edited**. Existing/concurrent changes were left alone. This document and [sanitized JSON evidence](evidence/sfp-x86-driver-inspection-2026-10-05.json) are the only repository files created by this inspection.

Input was the prior extracted tree `/home/djundev/.cache/mikpatch-audit/final-production-7m5_vbt0/vendor-root`. The attribution to RouterOS 7.24.4 comes from the supplied prior extraction context, not fresh signature verification. The adjacent `vendor.sfs` appears byte-for-byte inside `vendor.npk` at offset 4096; the complete extraction chain was not independently repeated.

- `vendor.npk`: 20,837,260 bytes; SHA-256 `46de2e3d61a6f5cdb7142f5cb62e3f2e4a28e283ef4fa17984b5511882031a94`.
- `vendor.sfs`: SHA-256 `6b359af14a08bd43be5edfdf8f887ff84dd89c501b2a59bf768db70d6373740c`.
- Extracted `boot/EFI/BOOT/BOOTX64.EFI`: SHA-256 `1531663f6127a5a17120fd293b43c8a6bc60ec0726952ccfa1648dc74e921aa1`.
- Its XZ stream at offset 14764 yields a 25,909,528-byte x86-64 ELF, SHA-256 `66bf5cfbaf3a7af934400c19b97d5f368cdb4e392fd245bba7d23d06ba971f56`. Actual banner: Linux `5.6.3-64`, build 2026-09-16. Kernel has no `.symtab`.

Methods: configured WSL Python `/home/djundev/.cache/mikpatch-audit/venv/bin/python`, stdlib ELF parsing, `readelf`, installed Capstone, narrow strings searches, relocation/callback inspection and hashes. No firmware binaries were executed or changed. No keys, credentials, EEPROM dump, or activation output was collected.

## Main decision

**Do not implement the proposed boot append `ixgbe.allow_unsupported_sfp=1,1,1,1` as a demonstrated fix.** The parameter exists in this exact module, but delivery through the RouterOS boot/module loader is unproven, four entries do not address every adapter, and the inspected generic vendor-check tail already warns and continues without checking that flag. This has no demonstrated connection to exposing optical telemetry in native RouterOS monitor/Winbox.

No firmware patch is justified by this bounded inspection. This is not a finding that every SFP is accepted, nor that no future targeted patch is possible.

## Actual ixgbe parameter and code path

`bndl/extra-nic/lib/modules/5.6.3-64/drivers/net/ixgbe.ko` is a **loadable module**, version `5.19.9`, vermagic `5.6.3-64 SMP mod_unload`.

- `.modinfo` explicitly declares `parmtype=allow_unsupported_sfp:array of int`. Description limits the documented intent to unsupported/untested SFP+ on 82599, default disabled.
- Relocated `__param` entry uses `param_array_ops`; array element ops resolve to `param_ops_int`. Descriptor: maximum **33** elements, 4 bytes each, permission **0**, initial stored elements `-1`; count in `.bss+0x18`, elements in `.data+0x1020`. Permission 0 does not establish a writable sysfs parameter.
- `ixgbe_check_options` at `.text+0x24e71` loads a board index from adapter `+0x2e24`. At `0x2575d–0x257a8`, it compares that index against supplied count, validates the indexed integer, writes a boolean at adapter `+0x26d1`, or clears it if unspecified. Four values are not a universal switch; runtime board/port ordering is untested.
- In actual `ixgbe_identify_sfp_module_generic` (`.text+0x19963`), the vendor-check tail `0x19c95–0x19cee` checks capabilities and recognized type values, then calls `ewarn` with the Intel untested-optics warning and jumps to the common return. **There is no allow-flag test in this tail.** Earlier read/type failure branches remain. The analogous inspected QSFP tail also warns and continues.
- This is disassembled behavior, not an upstream-source assumption. It does not establish who changed it, universal compatibility, or success of every path. Do not describe the original parameter proposal as syntactically nonexistent: its schema is real, its usefulness/delivery is not demonstrated.

## Module inventory and EEPROM evidence

298 `.ko` files were inventoried and hashed. All requested families were present. `ixgbe`, `i40e`, `ice`, `igb` reside in `bndl/extra-nic`; Broadcom and Mellanox below reside in the system module tree. Presence is not hardware compatibility.

The actual ethtool ops table setters/pointers and relocation targets were recovered. Slots `+0x160/+0x168` are strongly identified as module-info/module-EEPROM by the actual code's module-layout results and calls into named EEPROM readers. An upstream header comparison fetch was HTTP 429; no assertion of identical upstream/vendor ABI relies on it. Some static function names were stripped, so missing symbol names alone were not treated as missing functionality.

| Family | Actual module version | Observed static evidence / boundary |
|---|---|---|
| ixgbe | 5.19.9 | Table targets `.text+0x100d9/+0xfc27`; info path returns type/length pairs 1/256 or 2/512 and contains explicit unsupported A2 address-change error. Acceptance flag is separate from telemetry. |
| i40e | 2.27.8 | Table targets `+0x1337c/+0x1329b`; calls `i40e_aq_get_phy_register_ext`. Actual paths include NVM-update-required/no-module/A2 address-swap diagnostics and layout decisions. No `allow_unsupported_sfp` parameter in its metadata. |
| ice | 1.13.7 | Table targets `+0x49bec/+0x49a53`; calls `ice_aq_sff_eeprom`, layout selection and unrecognized-SFF-type warning. Unsupported-module/Rx-Tx-disabled strings also exist; not a full control-flow audit. |
| igb | 5.14.16 | `e1000_read_sfp_data_byte` exists and has callers, but **both candidate module-info/module-EEPROM slots are zero with no relocations** in the selected ops table. Internal module identification is not equivalent to a native ethtool DDM interface. Runtime alternate table/patching not excluded. |
| bnx2x | 1.713.36-0 | Table targets `+0x3949c/+0x39649`; calls `bnx2x_read_sfp_module_eeprom`, explicit interface-down guard and A0/A2 read paths; diag-type and SFF-8472 checks. |
| bnxt_en | 1.10.1 | Table targets `+0xff42/+0x102ee`; info code compares a field against `0x10201` (consistent with HWRM >= `0x10202` requirement), chooses 256/512-byte layouts; reader separates at 256-byte boundary. Field naming/source mapping not independently reconstructed. |
| mlx4_core / mlx4_en | 4.0-0 / 4.0-0 | `mlx4_en` table targets `+0x400a/+0x3f2a` call `mlx4_get_module_info` imported from core. Model/generation and firmware capability untested. |
| mlx5_core | 5.0-0 | Table targets `+0x21a0d/+0x21984` call `mlx5_query_module_eeprom`, select module types, handle unrecognized cable/error. No all-ConnectX claim. |

VF/virtual modules `ixgbevf`, `iavf`, `igbvf`, `virtio_net`, and `vmxnet3` were also present. That does not grant a guest access to physical module EEPROM.

## Builtins, command line and userland

- No `modules.builtin*` manifest was found. The decoded kernel `__param` table contains many valid named builtin parameters, **none for the investigated NIC families**. Together with their `.ko` files this supports the loadable-module path; it is not proof of complete absence of every related builtin code fragment.
- Kernel strings/export-name material include command-line logging, `saved_command_line`, `param_set_int`, `do_init_module` and unknown-parameter messages. Generic kernel strings do not prove RouterOS forwards `ixgbe.*` command-line options to its loader.
- Actual `nova/bin/moduler`/`modprobed` contain driver names and `modules.dep.`; their binaries hash identically. At `moduler` VA `0x805f753`, a call resolves to imported `finit_module`, with flags 0 and a string-pointer argument. **The origin/contents of that string for ixgbe were not traced.** No `/proc/cmdline` or `allow_unsupported_sfp` literal was found in these binaries. Broader ELF scanning did find `/proc/cmdline` in `sys2`, `romon`, and `kexec`; those hits do not establish option forwarding.
- `nova/bin/net` is an actual 32-bit ELF with `ioctl` import, SIOCETHTOOL failure strings, and 12 inspected `0x8946` call-site windows. Thus generic ethtool ioctl use is evidenced, not just assumed from Linux.
- Those windows show several ordinary link/settings commands. A complete `ETHTOOL_GMODULEINFO` (`0x42`) / `ETHTOOL_GMODULEEEPROM` (`0x43`) to native SFP-monitor dataflow was **not established**. Calls through wrappers, dynamic command construction, alternate/private ioctls, and other components are not excluded by negative searches.
- No ethtool-named regular file was found. This does not mean the kernel API is absent or that RouterOS must execute an external `ethtool` program.

## Exact blockers and next evidence

1. Identify a **specific failing pair**, starting with one 82599/X520 SFP+ card if the ixgbe proposal is to be evaluated: full card/OEM, PCI vendor/device/subsystem IDs, revision, NVM firmware, port index, transceiver vendor/part/revision/coding, speed, single-lane DOM/DDM specification, optical/DAC/copper type. Redact serials/MACs.
2. Capture RouterOS 7.24.4 resource/PCI inventory, ethernet monitor for that port, and sanitized module/link errors. Distinguish absent module, rejected module, link failure, identification-only and missing DDM. Current inspection has **no failing hardware observation** to fix.
3. On the same hardware in an approved lab, capture read-only Linux `lspci -nnk`, `ethtool -i`, and `ethtool -m`, with stderr/exit status. No EEPROM writes, NIC flashing, or automatic unbind/reboot.
4. For a loader change, first trace actual ixgbe selection through custom `moduler` to the exact `finit_module` argument. Prove parameter acceptance and per-board mapping on a disposable authorized target; do not assume standard Linux modprobe config/cmdline behavior.
5. For native power fields, trace RouterOS monitor's EEPROM retrieval/decoder path. The driver-side code is not enough. For igb, confirm whether the missing table callbacks cause the real failure before considering a driver extension; matched ABI/source/toolchain and hardware access would be required.
6. VM cases are separate: emulated NIC, SR-IOV VF, and full PCI PF passthrough. Need exact hypervisor/guest type and who owns the physical NIC. Virtual link visibility is not optical sensor access. No physical/VM/CCR parity or universal-module claim is supported.

## Validation and limitations

- All **582 regular non-symlink files** hashed in the vendor-root baseline remained content-identical at the final check; all 298 module hashes matched. Symlink/metadata integrity was not claimed by this content check.
- JSON persists provenance hashes, module metadata and PCI aliases, selected symbols/strings, relocation records, disassembly, decoded parameters, userland windows, conclusions and validation. Offsets in module disassembly are section-relative; userland windows use ELF virtual addresses.
- Readelf corroborated ixgbe sections, metadata and symbols. `modinfo`, `objdump`, `strings`, and pyelftools were unavailable; no packages installed. Python/Capstone handled static inspection.
- Initial WSL path-conversion error and a summary-command syntax error were corrected. External header fetch failed HTTP 429. No external source fetched successfully is needed for the positive binary observations.
- No firmware build, boot, physical/owner-VM test, throughput/DDM accuracy/hotplug/rollback test, activation or unit suite ran. Unit tests would not establish hardware support. No unsupported parameter was injected.
