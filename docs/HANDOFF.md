# HANDOFF — Ali Patch Code

Dokumen serah terima untuk developer lain yang mau melanjutkan kerja repo ini.
Dibuat 2026-10-03 oleh sesi kerja agent Hermes atas instruksi pemilik repo (`devlhi`).
Kalau kamu melanjutkan kerja di sini, **perbarui dokumen ini** di akhir sesimu.

## Status singkat

| Hal | Status |
|---|---|
| Cabang | `main` (satu-satunya) |
| HEAD saat dokumen ini dibuat | `be9cd23` — guard cakupan patch NPK |
| Rilis 7.24.4 | release biasa + **Latest**; 40 aset; aset TIDAK dibangun ulang dengan guard |
| Rilis 7.23.3 | **prerelease**; tag `7.23.3` + tag build lama; 40 aset; aset TIDAK dibangun ulang |
| Boot / aktivasi lisensi | **Belum pernah teruji.** Jangan klaim sebaliknya |

## Apa yang sudah dikerjakan

### 1. Audit flow lisensi (7.17 vs 7.23.3 / 7.24.4)

- Source/engine/generator **identik** dengan baseline komunitas `loskiq/MikroTikPatch` tag `7.17`
  (commit `3160cd6c`): `license.py`, `mikro.py`, `npk.py`, `sha256.py`, `toyecc/`,
  6 nilai konfigurasi kunci, 7 arsitektur, 5 tahap patch, generator payload + verifikasi KCDSA (4/4 tes parity).
- Firmware 7.17 menanam byte kunci lisensi custom di `nova/bin/keyman`, `loader`, `mode`.
  Pada firmware 7.23.3 & 7.24.4 (semua 7 arsitektur, manifest + signature custom valid),
  **byte kunci lisensi yang dicari tidak ditemukan pada data yang berhasil dipindai.**
  Ada warning kandidat XZ yang membatasi cakupan pemindaian → ini *bukan* bukti kunci absen.
- Pembanding penting: NPK **vendor resmi** 7.24.4 identik byte dengan build custom pada
  `keyman`/`loader`/`mode` (yang beda hanya `installer`/`sys2`/ssh karena branding).
  Artinya perubahan penyimpanan kunci lisensi berasal dari **upstream MikroTik**, bukan bug alur repo ini.
- Kesimpulan jujur: alur build sudah sama seperti 7.17 sejak awal; hasilnya beda karena
  MikroTik mengubah cara menyimpan kunci. Aktivasi pada versi baru **belum terbukti berhasil**.

### 2. Guard "sukses palsu" — commit `be9cd23`

Bug yang ditemukan: alur lama **tetap menandatangani paket `system` meski pola kunci wajib
tidak ditemukan** — build tampak sukses padahal kunci lisensi tidak tertanam.

Perbaikan di `patch.py` (jalur `patch.py npk` / `patch_npk_file`):

- Paket `system` wajib punya ≥1 penggantian per mapping (gabungan kernel + SquashFS)
  **sebelum** signing; kalau tidak → `ValueError`, tidak ada file output yang ditulis.
- Hitungan dan pencarian hanya pada **byte asli** di **offset asli**; kecocokan hasil
  penggantian sebelumnya tidak bisa dihitung atau menimpa penggantian lain.
- Overlap antar-pola pada byte asli ditolak; hardlink diproses sekali per inode `(st_dev, st_ino)`.
- `unsquashfs`/`mksquashfs` jalan dengan literal argv di `TemporaryDirectory` terisolasi, repack `-noappend`.
- Log/laporan hanya berisi indeks mapping + jumlah — tanpa material kunci.
- Verifikasi: **213 tes lulus** (26 tes cakupan/integrasi, 4 di antaranya pakai tool SquashFS nyata),
  lulus juga dengan `python -O`, review independen lulus (2 putaran review awal menemukan bug nyata
  dan diperbaiki). Kontrak lengkap: [`docs/patch-coverage.md`](patch-coverage.md).

### 3. Perapian rilis

- Rilis 7.23.3 (id `401130489`) dipindah ke tag `7.23.3`, **tetap menunjuk commit pembuat asetnya**
  `37e5889` (run Actions `36884945543`), status tetap prerelease.
  Tag build lama `ali-patch-code-7.23.3-run36884945543-attempt1` **dipertahankan** sebagai provenance.
- Rilis 7.24.4 (id `401538288`, commit `bd2dc61`, run `36962377447`) tetap release biasa + Latest.
- Catatan audit ditambahkan ke **kedua** rilis: kunci lisensi tidak teramati pada data terpindai,
  guard ada di `main`, dan **aset rilis TIDAK dibangun ulang** dengan guard.
- Seluruh 40+40 aset diverifikasi tidak berubah (ID, nama, ukuran, digest GitHub, state).

## Yang bisa / perlu dikerjakan selanjutnya

1. **Uji boot** — belum pernah dilakukan sekali pun. Paling gampang: QEMU/Proxmox x86-64
   dengan `ali-patch-code-x86-chr-7.24.4-patched.qcow2.zip` (ekstrak dulu, snapshot, lab saja).
2. **Uji aktivasi lisensi** — panel lab ada di `web/license/` + `scripts/license_util.py` /
   `scripts/license_server.py`; lihat `tests/test_license_*.py`. Belum ada bukti aktivasi sukses
   pada firmware 7.23.3/7.24.4.
3. **Bangun ulang firmware dengan guard** — jalankan workflow `patch7.yml` (workflow_dispatch)
   di `main`. Ingat: guard sekarang fail-closed — kalau pola lisensi tetap tidak ditemukan,
   **build akan gagal dengan sengaja**. Itu hasil yang benar; jangan di-bypass.
4. **Perluas guard** ke path mandiri `kernel` / `block` / `netinstall` dan CLI `npk.py sign`
   (saat ini masih tanpa guard paket — lihat "Batas cakupan" di `docs/patch-coverage.md`).
5. **Bug engine historis lain**: `encode_version` IndexError pada string versi, `NameError`
   di `lic_parse_ros`, penanganan XZ 8/64-bit, truncation diterima — belum diperbaiki.
6. **Cari penyebab** verifier lama menolak signature NPK vendor resmi (belum ditelusuri).

## Cara kerja cepat

```sh
# Tes penuh (dari root repo)
env -u PYTHONPATH TMPDIR=$HOME/.hermes/cache/scratch \
  CADDY_TEST_BINARY=/Applications/ServBay/bin/caddy \
  venv/bin/python -B -m unittest discover -s tests -q

# Tes cakupan guard saja (+ integrasi SquashFS nyata, butuh unsquashfs/mksquashfs di PATH)
env -u PYTHONPATH venv/bin/python -B -m unittest discover -s tests -p 'test_patch_coverage*.py' -v
```

- Git: HTTPS, auth `devlhi` via macOS Keychain (`gh` tidak terpasang).
- Artefak audit lengkap (scanner, JSON hasil, laporan `FLOW717-LAPORAN-AUDIT.md`) ada di
  mesin pemilik di luar repo (`~/.hermes/cache/scratch/ali-7244-ops/`); ringkasannya sudah
  tertanam di catatan kedua rilis dan dokumen ini.

## Aturan main — jangan dilanggar

1. **Jangan pernah menampilkan nilai** `MIKRO_LICENSE_PUBLIC_KEY`, `CUSTOM_LICENSE_*`,
   `MIKRO_NPK_SIGN_*`, token, atau credential helper — cukup boolean/nama/jumlah.
2. **Jangan pindahkan tag rilis yang sudah terbit**; tag menunjuk commit pembuat asetnya.
3. **Jangan tambahkan bypass guard** supaya build tampak sukses.
4. Jangan ubah aset rilis yang sudah terbit tanpa build ulang penuh + verifikasi ulang.
5. Ini **lab pribadi**, bukan lisensi resmi MikroTik: jangan klaim aktivasi/kompatibilitas
   tanpa bukti uji; jangan janjikan kompatibilitas semua NIC (SFP hanya offline single-lane).
6. Kunci privat legacy pernah terekspos di repo lama — anggap tidak layak produksi.
