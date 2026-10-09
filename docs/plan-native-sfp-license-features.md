# Rencana terpadu — License "Features" cleanup + SFP DOM native x86

Disusun 2026-10-08 atas permintaan pemilik ("buat dulu plannya, kumpulkan dulu
semuanya"). Dokumen kerja; status bukti rinci ada di
[evidence §33](evidence/sfp-x86-userland-ethtool-trace-2026-10-07.json) dan
[HANDOFF §33](HANDOFF.md). Semua pekerjaan lab-first; firmware hanya ke mesin
pemilik setelah gate lab lulus; commit/push menunggu izin pemilik; Software
ID/serial/MAC tidak dicatat di repo.

## Ringkasan bukti yang sudah terkumpul

1. `nova/bin/net` RouterOS 7.23.1 & 7.24.4 (x86) dan 7.24.4 (arm/ELF32) tidak
   pernah memanggil ioctl EEPROM modul (GMODULEINFO/GMODULEEEPROM); DOM board
   MikroTik disuplai driver lewat kanal privat.
2. Kanal privat ditemukan: keluarga ioctl SIOCDEVPRIVATE 0x89F0–0x89FE,
   dipakai `net` identik di x86 dan arm; handler-nya hanya ada di driver biner
   MikroTik (tidak dalam GPL dump).
3. Sumber GPL 7.24.4 (mirror tikoci; tautan box resmi mati): pohon vanilla
   5.6.3 + patch MikroTik (antara lain: `allow_unsupported_sfp=1` default di
   ixgbe). Patch tidak memuat feed DOM.
4. Screenshot pemilik: lisensi hasil generator repo ini menampilkan
   **License Level 6 + Features "extra channel"**; screenshot teman (build
   "AASHS", 7.24.2): **Level 6 + Features kosong**, updater tetap normal,
   changelog ditandatangani pembuatnya, container tanpa hard reset.
4b. Info baru dari teman (video): DOM di build-nya **baru terbaca di CLI**
   (`interface/ethernet/monitor` lengkap: vendor/serial/wavelength/tx-rx
   power), **belum muncul di tab Status Winbox** — dia sendiri menyebutnya
   kekurangan. Ini indikasi kuat plumbing-nya parsial (mis. gate/caps atau
   set property khusus objek-interface belum menyala), konsisten dengan
   hipotesis feed level driver.
5. Field Features bersumber dari **payload lisensi yang generator kita buat**
   (byte index 7; `lic_gen_ros` men-set 22, warisan proyek komunitas). String
   "extra channel" dirakit dinamis (tidak literal di keyman/net/console .mem).

## Workstream A — hilangkan "extra channel" dari License Features

Tujuan: tampilan License sama dengan punya teman (Features kosong), Level 6
tetap, updater tetap jalan. Perubahan di **generator lisensi kita** — bukan
firmware.

- **A1 Statik (reverse label):** *sebagian selesai 2026-10-08.* Kata
  **`extra-channels`** ditemukan di kamus console `1073741824.mem` (baris
  kata wireless). Hipotesis kerja terbentuk: byte payload index 7 = `(bit
  fitur << 4) | level` — nilai lama 22 = 0x16 → level 6 + bit fitur 1 =
  "extra-channels"; build teman yang tampil kosong konsisten dengan 0x06.
  Satu-satunya pasangan nibble di keyman (0x8050ee5) ternyata loop hex-dump,
  bukan parse fitur — lokasi parse persis belum ketemu; konfirmasi final
  dialihkan ke A3 empiris.
- **A2 Generator:** *selesai 2026-10-08.* `lic_gen_ros` kini menerima
  `feature_bits` (default 1 → byte tetap 0x16, keluaran lama byte-identik);
  `license_util.generate_ros(..., feature_bits=...)` memvalidasi 0–15;
  `parse` ROS kini menerima byte level/fitur apa pun (versi tetap wajib 7)
  dan melaporkan `License Level` (nibble rendah) + `Feature Bits` (nibble
  tinggi). Regresi: test_license_util 18/18 (3 tes baru), CLI 28/28,
  server 25/25, frontend 12/12 — semua hijau, 0 skip. **Catatan:** ini
  divergence pertama `license.py` dari baseline komunitas (dipilih default
  yang mengawetkan byte lama).
- **A3 Lab (matriks nilai):** *SELESAI 2026-10-08 — fb0 TERKONFIRMASI.*
  Harness macOS penuh dibangun (media installer ter-patch via pipeline
  produksi pada volume case-sensitive → QEMU TCG → serial driver dengan
  penanganan CR/ANSI/EULA/wizard/password). Hasil verifikasi pasca-reboot
  pada firmware patched 7.24.4: lisensi `feature_bits=0` → **`nlevel: 6`,
  `features:` KOSONG** — sasaran tercapai, identik tampilan punya teman.
  Rincian + batas di JSON bukti §33 (addendum A3). Kontrol fb1 (0x16 →
  "extra-channels") opsional tersisa. Langkah A4: ekspos `feature_bits` di
  CLI/panel lab + regenerasi lisensi pemilik setelah persetujuan.
- **A4 Terapkan:** pemilik regenerasi lisensinya sendiri (launcher/panel
  miliknya) dengan nilai terpilih → paste → reboot → konfirmasi tampilan.

Risiko: peta bit belum diketahui; kemungkinan "extra channel" terkait akses
kanal upgrade ekstra — diperiksa di A3. Perkiraan: 1–2 sesi kerja.

## Workstream B — SFP DOM native x86 (modifikasi driver, tanpa option.npk)

Tujuan: `interface/ethernet/monitor` menampilkan vendor/part-number/serial/
wavelength/tx-power/rx-power seperti screenshot teman, melalui penggantian
`.ko` driver di dalam NPK system (tanpa entri paket baru).

- **B1-lanjut: TRANSPORT & RESPONDER SELESAI 2026-10-08.** Bus RPC =
  **netlink protokol custom 27** (`socket(AF_NETLINK, SOCK_RAW, 0x1B)`,
  `send()` ber-header magic 0x52B0); **responder = `packet_hook.ko`**
  (satu-satunya modul dengan `__netlink_kernel_create` + `util_init`
  `/dev/util`), yang juga **mengekspor API registrasi driver**
  (`register_proto`/`proto_handlers`/`register_*_handler`, 54 ekspor).
  Rincian di JSON bukti §33 addendum B1-transport. **Langkah B2 (berikutnya):
  bedah dispatch `packet_hook.ko`** — semantik `register_proto`, layout tabel
  handler, dan bagaimana pesan netlink 27 diteruskan ke driver — lalu prototipe
  handler di `ixgbe`/`bnx2x` (0x89F0 via ndo_do_ioctl + 0xA0B1 via API
  registrasi).

- **B1 Reverse protokol privat:** *katalog selesai 2026-10-08 (agent + verifikasi
  parent).* 33 situs identik di 7.24.4/7.23.1; seluruh keluarga 0x89F0–0x89FE
  lewat `nv::ifreqDataIoctl(ifname, buf, req)` dengan buffer 2-dword dua arah
  ({-1,-1} = gagal); semantik relatif-driver. Klaster SFP: 0x89F0 = **get
  module type** (enum 0–13, mask 0x25F0, -1 = absen) → iface+0xd4; 0x89F1 =
  atribut sekunder → iface+0xd8; dipublikasikan sebagai field nv 0x3FC/0x3FB/
  0x1002E dan menggerakkan gating per tipe modul. **Koreksi arsitektur:**
  region 0x8093xxx–0x8097xxx adalah manajemen switch-chip, bukan SFP; data
  EEPROM/DOM **bukan lewat 0x89Fx** melainkan **RPC nv-bus pesan 0xA0B1**
  (magic 0x00A0B000/0x52B0/0x11223344; halaman 1400 B, len ≤ 0x578; reply
  header 0x21-B {status@+6, data_len@+0x1B, data_offset@+0x1D}) — semua
  konstanta terverifikasi parent di biner. Scan 298 .ko vendor untuk dword
  0xA0B1 menghasilkan false positive (displacement `mov [reg+0xa0]` dan data
  symtab); responder kernel belum teridentifikasi dan kerangka bridging tidak
  ada di GPL dump. **Langkah B1-lanjut:** telusuri tujuan pengiriman pesan
  bus 0xA0B1 dari `net` (kanal/proses/`/dev`) untuk menemukan responder yang
  harus diimplementasi, plus pemetaan dua konsumen property (CLI monitor vs
  tab Status Winbox; build teman baru menyala di CLI).
- **B2 Implementasi:** handler protokol privat di `ixgbe` (X520) dan `bnx2x`
  (BCM57800) di atas GPL 5.6.3 + patch MikroTik; data dari pembaca
  EEPROM SFF-8472 yang sudah ada di kedua driver.
- **B3 Build per versi firmware:** 7.24.4 lebih dulu (pipeline/pin/kebijakan
  runtime repo terverifikasi di versi ini), 7.24.2/7.23.1 menyusul;
  configs GPL tersedia; Module.symvers dicari (kandidat: ekstrak vmlinux
  vendor atau build in-tree penuh) — titik risiko tercatat.
- **B4 Integrasi pipeline:** ganti `.ko` dalam NPK `system` lewat patcher
  repo; sesuaikan guard cakupan + paritas metadata untuk file berubah; sign
  keypair lab; build image CHR/installer seperti biasa.
- **B5 Verifikasi bertingkat:** stub protokol di lab (QEMU tidak bisa
  mengemulasi EEPROM SFP) → hardware pemilik (BCM57800; X520 bila tersedia).

Perkiraan: proyek multi-sesi; B1 murni analisa statis (tanpa risiko).

## Urutan eksekusi yang disarankan

A1→A2→A3→A4 dulu (cepat, hasil langsung terlihat), B1 berjalan paralel
sesi demi sesi, lalu B2–B5 berurutan dengan gate lab di tiap fase.

## Workstream C — dukungan RouterOS 7.24.5 (versi baru)

Prinsip: versi baru = **provenance baru** — kualifikasi ulang, tag/rilis baru,
tidak pernah menimpa aset lama (aturan repo). Urutan:

- **C0 Triage: SELESAI 2026-10-08 — hasil sangat menguntungkan.** NPK system
  7.24.5 vendor (20.841.356 B, SHA-256 `d97831be…`, system 7.24.5.final).
  `keyman`/`loader`/`mode`/`login`/console .mem/`logo.txt` **byte-identik
  dengan 7.24.4** (anchor lisensi & pin banner tidak berubah); `net` & `sys2`
  beda byte namun ukuran sama. **Kernel tetap 5.6.3-64**; packet_hook/bnx2x/
  ixgbe tetap ada. Permukaan protokol SFP identik: 12 SIOCETHTOOL, 4× RPC
  0xA0B1, magic lengkap, netlink 27. Implikasi: C1 tinggal ganti pin source
  NPK + verifikasi ulang; Workstream B kemungkinan satu build modul untuk
  7.24.4+7.24.5 (kernel sama).
- **C1 Kualifikasi: SELESAI 2026-10-08 — patch lisensi 7.24.5 TERBUKTI
  setara 7.24.4 (end-to-end lab).** `patch.py` kini mendukung kebijakan
  `x86-installer-7.24.5` (pin source `d97831be…`; komponen pin sama karena
  loader/keyman/mode byte-identik — diverifikasi ulang dari squashfs 7.24.5).
  Build produksi NPK 7.24.5: coverage LICENSE 2 + NPK-sign 5,
  `coverage-passed` (hash `6d6421e4…`). Bukti lab: disk QEMU terpasang
  (sebelumnya 7.24.4 + lisensi fb0) di-upgrade dengan menukar
  `/var/pdb/system/image` ke NPK 7.24.5 ter-patch via debugfs → boot kernel
  7.24.5 → `/system resource print`: **7.24.5 stable**; `/system license
  print`: **software-id SAMA, level 6, features KOSONG** — lisensi fb0
  carry-over sempurna tanpa regenerasi. (Catatan lab: pasca-upgrade console
  kembali menampilkan alur first-login singkat; lisensi tidak terpengaruh.)
  Perbaikan engine ikutan: normalisasi bit permission symlink di
  `_squashfs_metadata`/`_tree_metadata` (mode symlink non-semantik di Linux;
  drift 0777→0755 di round-trip macOS/APFS) + tes regresi; seluruh suite
  engine hijau (x86 31, chr 27, coverage 23+7, branding, banner 23).
- **C2 Banner terminal:** re-pin konsumer login (`CONSUMER_SHA256`) dan sumber
  daya logo untuk 7.24.5 (kebijakan banner versi-sadar bila perlu).
- **C3 Workflow + tes:** `PINNED_VERSION` → 7.24.5, validator inline (pin
  versi+hash), perbarui `test_patch7_branding`/`test_chr_runtime_policy`/
  `test_x86_installer_runtime_policy`; CI profil x86-all.
- **C4 Build + gate lab:** pakai harness yang sudah terbukti (CI atau harness
  macOS sesi A3): install → boot → login → lisensi fb0 (Level 6 + Features
  bersih) → nanti modul SFP Workstream B begitu tersedia.
- **C5 Rilis:** tag/provenance baru, draft opt-in, persetujuan pemilik; aset
  7.24.4/7.23.3 tidak disentuh.

Urutan terhadap workstream lain: **jangan blokir A4** (lisensi bersih untuk
mesin pemilik di 7.24.4) oleh C. Rekomendasi: A4 dulu, C0–C1 paralel, B tetap
mengikuti hasil agent B2. Catatan lisensi: payload fb0 dipercaya
versi-independen (format byte sama), tetap diverifikasi ulang di C4.

## Yang di luar scope rencana ini

Mengubah penampilan changelog/branding firmware, mengikuti trik device-mode
teman, atau memindahkan URL upgrade — tidak dikerjakan tanpa permintaan
terpisah tertulis dari pemilik.
