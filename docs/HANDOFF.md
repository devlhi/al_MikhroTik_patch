# HANDOFF — Ali Patch Code

Dokumen serah terima untuk developer lain yang mau melanjutkan kerja repo ini.
**Status diperbarui: 2026-10-04 (WITA).** Dokumen awal masuk lewat commit `3e2a73b`
atas instruksi pemilik repo (`devlhi`). Ini memori proyek yang ikut Git, bukan
salinan memori pribadi agent atau tempat menyimpan kredensial.

Mulai dari dokumen ini, lalu baca kontrak [guard cakupan](patch-coverage.md).
Kalau melanjutkan kerja, **perbarui dokumen ini** di akhir sesi: commit yang diubah,
tes yang benar-benar dijalankan (termasuk skip/gagal), batas bukti, dan tugas berikutnya.

## Status singkat

| Hal | Status |
|---|---|
| Cabang kerja sesuai arahan pemilik | `main`; jangan membuat cabang lain tanpa persetujuan |
| Commit fungsional acuan | `be9cd23` — guard cakupan patch NPK; commit setelahnya untuk dokumentasi |
| Rilis 7.24.4 | release biasa + **Latest**; 40 aset; aset TIDAK dibangun ulang dengan guard |
| Rilis 7.23.3 | **prerelease**; tag `7.23.3` + tag build lama; 40 aset; aset TIDAK dibangun ulang |
| Boot / instalasi / upgrade / aktivasi | **Belum ada bukti uji runtime dari pekerjaan ini.** Jangan klaim berhasil |

## Apa yang sudah dikerjakan

### 1. Audit flow lisensi (7.17 vs 7.23.3 / 7.24.4)

Ringkasan berikut berasal dari audit sesi sebelumnya, sebelum guard `be9cd23`.
Pemindaian firmware tidak dijalankan ulang saat penulisan handoff ini.

- Pada snapshot `bd2dc61`, komponen `license.py`, `mikro.py`, `npk.py`, `sha256.py`,
  dan `toyecc/` yang dibandingkan identik dengan baseline komunitas
  `loskiq/MikroTikPatch` tag `7.17` (commit `3160cd6c2821af6a8c2b86e12bd16a3c67eb2519`).
  Enam nilai konfigurasi kunci serta tujuh arsitektur/lima tahap patch yang dibandingkan
  cocok; empat tes parity generator lulus. **Bukan seluruh patcher identik:**
  `patch.py` sudah memiliki perbedaan kebijakan kompresi initrd, dan kini juga guard baru.
- Pada **satu NPK x86 baseline 7.17**, byte kunci lisensi custom teramati di
  `nova/bin/keyman`, `loader`, dan `mode`. Ini bukan hasil uji tujuh arsitektur 7.17.
- Pada tujuh NPK sistem **masing-masing versi 7.23.3 dan 7.24.4**, manifest dan
  signature custom lolos pemeriksaan repo; byte kunci lisensi yang dicari **tidak
  teramati pada data yang berhasil dipindai**. Arsitekturnya: `x86`, `arm`, `arm64`,
  `mipsbe`, `mmips`, `smips`, `ppc`. Warning kandidat XZ membatasi cakupan; pencarian
  byte persis tidak mencakup semua representasi. Hasil negatif bukan bukti absensi mutlak.
- Pembanding **x86 7.24.4 yang diunduh dari URL vendor** memiliki tiga file
  `keyman`/`loader`/`mode` identik byte dengan build custom. Verifier lama repo menolak
  signature unduhan pembanding itu; penyebabnya belum ditentukan. Jadi jangan menyebut
  keaslian pembanding sudah terverifikasi secara kriptografis.
- Kesamaan tiga file **tidak menjelaskan penyebabnya**: lokasi, representasi kunci,
  atau mekanisme verifier belum diketahui. Jangan menyimpulkan MikroTik pasti mengubah
  penyimpanan kunci, bahwa repo bebas bug, atau bahwa semua perubahan hanya branding.
  **Aktivasi pada versi baru belum terbukti berhasil.**

### 2. Guard "sukses palsu" — commit `be9cd23`

Bug yang ditemukan: alur lama **tetap menandatangani paket `system` meski pola kunci wajib
tidak ditemukan**. Sukses build/signing tidak membuktikan transformasi yang diharapkan.
Guard memperbaiki pemeriksaan cakupan, **bukan aktivasi lisensi**.[3]

Perbaikan di `patch.py` (jalur `patch.py npk` / `patch_npk_file`):

- Paket `system` wajib punya ≥1 penggantian per mapping (gabungan kernel + SquashFS)
  **sebelum** signing; kalau tidak → `ValueError`, tidak ada file output yang ditulis.
- Hitungan dan pencarian hanya pada **byte asli** di **offset asli**; kecocokan hasil
  penggantian sebelumnya tidak bisa dihitung atau menimpa penggantian lain.
- Overlap antar-pola pada byte asli ditolak; hardlink diproses sekali per inode `(st_dev, st_ino)`.
- `unsquashfs`/`mksquashfs` jalan dengan literal argv di `TemporaryDirectory` terisolasi, repack `-noappend`.
- Log/laporan hanya berisi indeks mapping + jumlah — tanpa material kunci.
- Verifikasi sebelum commit guard: **213 tes suite penuh lulus pada mode normal**;
  **26 tes cakupan/integrasi juga lulus dengan `python -O`**. Bukan klaim seluruh
  suite 213 tes dijalankan dengan `-O`. Empat tes integrasi memakai SquashFS nyata,
  NPK/pola sintetis, dan signing yang di-mock—bukan firmware/kunci nyata.
- Review independen final lulus setelah dua review sebelumnya menemukan bug affix-overlap
  dan pemrosesan ulang hardlink; keduanya diperbaiki dengan tes regresi.
  Kontrak lengkap: [pemeriksaan cakupan patch](patch-coverage.md).

### 3. Perapian rilis

- Rilis 7.23.3 (id `401130489`) dipindah ke tag `7.23.3`, **tetap menunjuk commit pembuat asetnya**
  `37e5889` (run Actions `36884945543`), status tetap prerelease.[1]
  Tag build lama `ali-patch-code-7.23.3-run36884945543-attempt1` **dipertahankan** sebagai provenance.
- Rilis 7.24.4 (id `401538288`, commit `bd2dc61`, run `36962377447`) tetap release biasa + Latest.[2]
- Catatan audit ditambahkan ke **kedua** rilis: kunci lisensi tidak teramati pada data terpindai,
  guard ada di `main`, dan **aset rilis TIDAK dibangun ulang** dengan guard.
- Saat perapian rilis, metadata 40+40 aset dibandingkan sebelum/sesudah: ID, nama,
  ukuran, digest GitHub, dan state tetap sama. Ini **bukan unduh ulang/hash ulang**
  seluruh biner. Pada 2026-10-04, GET anonim kembali memastikan masing-masing rilis
  memiliki 40 aset berstatus `uploaded`, bukan draft; Latest tetap 7.24.4.[1][2]
- Label prerelease tidak melarang unduhan, tetapi juga tidak menjamin boot/aktivasi.

### 4. Peta komponen lain untuk developer berikutnya

| Area | Titik masuk | Batas klaim |
|---|---|---|
| Panel lab lokal | [panduan panel](../web/license/README.md), `scripts/license_util.py`, `scripts/license_server.py` | Bukan layanan lisensi resmi; tes parser/signature bukan bukti aktivasi perangkat |
| Paket deployment | [panduan deployment](../deploy/README.md) | Adanya installer/tes bukan bukti deployment VPS telah berjalan |
| Diagnostik SFP | [panduan SFP](sfp-power.md), `scripts/sfp_diagnostics.py` | Parser offline/read-only single-lane; bukan driver atau dukungan NIC/SFP universal |
| Build dan aset rilis | `.github/workflows/patch7.yml`, `scripts/release_assets.py`, `tests/test_release_assets.py` | Build, manifest, signature, dan boot adalah pemeriksaan yang berbeda |

## Yang bisa / perlu dikerjakan selanjutnya

1. **Uji boot terisolasi, dengan persetujuan pemilik** — mulai dari image CHR/installer
   yang sesuai untuk VM x86, bukan NPK sebagai disk boot. Verifikasi checksum, buat
   snapshot dan rencana pemulihan; simpan versi, arsitektur, hash, serta log boot.
   Belum ada hasil uji ini dalam pekerjaan yang dicatat di sini.
2. **Pisahkan bukti aktivasi dari bukti boot/signature** — gunakan mekanisme lisensi
   resmi yang berlaku. Panel custom-lab dan tes `tests/test_license_*.py` tidak
   membuktikan lisensi diterima firmware 7.23.3/7.24.4.
3. **Build baru memakai guard, bila disetujui** — workflow manual `patch7.yml` di `main`.
   Kalau satu mapping wajib tetap tidak ditemukan, build **harus gagal**. Catat log
   tersanitasi dan jangan bypass guard. Jangan pindahkan tag/aset terbit untuk menyamarkan
   build baru sebagai build lama.
4. **Pertimbangkan guard jalur mandiri** `kernel` / `block` / `netinstall` dan CLI
   `npk.py sign`. Saat ini guard paket belum berlaku di sana; desain kontrak dan
   tes negatif dahulu, bukan klaim jalur tersebut sudah terlindungi.
5. **Reproduksi kandidat bug dari catatan sesi lama** — `encode_version`, `lic_parse_ros`,
   penanganan XZ/truncation. Catatan tersebut belum diuji ulang dalam handoff ini;
   pulihkan bukti atau buat reproduksi sintetis sebelum menyatakan bug/fix terkonfirmasi.
6. **Telusuri verifier signature pembanding vendor** tanpa mengubah kunci atau
   mematikan verifikasi agar hasil tampak lulus.

## Cara kerja cepat

Jalankan dari root repo. Untuk checkout baru, buat virtualenv sendiri dan pasang
`requirements.txt` serta `requirements-license.txt`; jangan menyalin kredensial pemilik.
Python yang digunakan pada sesi sebelumnya: **3.14.6**. Jangan menganggap versi
Python lain sudah diuji hanya karena instalasi berhasil.

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements.txt -r requirements-license.txt

# Tes penuh; baca hasil skip juga, bukan hanya kata OK.
env -u PYTHONPATH venv/bin/python -B -m unittest discover -s tests -v

# Kontrak guard pada normal dan optimized mode.
env -u PYTHONPATH venv/bin/python -B -m unittest discover -s tests -p 'test_patch_coverage*.py' -v
env -u PYTHONPATH venv/bin/python -O -B -m unittest discover -s tests -p 'test_patch_coverage*.py' -v
```

Prasyarat agar cakupan tes tidak diam-diam berkurang:

- `unsquashfs` dan `mksquashfs` harus ada di `PATH`; empat tes integrasi di-skip
  jika tidak tersedia. Sesi guard menggunakan SquashFS **4.7.5**.
- Node.js harus ada di `PATH` untuk tes kontrak frontend; tanpa Node tes itu di-skip.
- Dua tes Caddy nyata hanya aktif jika `CADDY_TEST_BINARY` menunjuk binary Caddy
  yang dapat dieksekusi. Tentukan path sesuai mesinmu; tidak harus ServBay.
- `TMPDIR` harus direktori yang sudah ada dan dapat ditulis. `env -u PYTHONPATH`
  mencegah kontaminasi paket dari lingkungan agent; ini bukan kebutuhan akun Hermes.

Contoh yang dipakai di **mesin macOS pemilik**, bukan path portabel:

```sh
mkdir -p "$HOME/.hermes/cache/scratch"
env -u PYTHONPATH TMPDIR="$HOME/.hermes/cache/scratch" \
  CADDY_TEST_BINARY=/Applications/ServBay/bin/caddy \
  venv/bin/python -B -m unittest discover -s tests -v
```

### Bukti yang tersedia dan yang hilang

- Kode, tes regresi, kontrak guard, riwayat commit, dan catatan rilis berada di GitHub.
- Bukti mentah audit sebelumnya pernah berada di folder sementara
  `~/.hermes/cache/scratch/ali-7244-ops/` dan `ali-7233-repair/`, termasuk scanner,
  JSON per arsitektur dan `FLOW717-LAPORAN-AUDIT.md`. **Pada pemeriksaan 2026-10-04,
  kedua folder sudah tidak ada.** Jangan menganggap developer lain bisa membukanya.
- Ringkasan di atas mempertahankan hasil historis, bukan pengganti bukti mentah atau
  pemindaian baru. Untuk audit ulang, pulihkan backup bila ada atau jalankan kembali
  pemeriksaan; jangan membuat ulang JSON seolah-olah itu output eksekusi asli.
- Bukti baru yang perlu diwariskan harus disimpan secara tahan lama setelah disanitasi;
  jangan mengandalkan scratch yang dapat dipangkas otomatis. Jangan commit firmware,
  kunci, token, kredensial, atau log mentah yang belum diperiksa.

## Aturan main — jangan dilanggar

1. **Jangan pernah menampilkan nilai** `MIKRO_LICENSE_PUBLIC_KEY`, `CUSTOM_LICENSE_*`,
   `MIKRO_NPK_SIGN_*`, token, atau credential helper — cukup boolean/nama/jumlah.
2. **Jangan pindahkan tag rilis yang sudah terbit**; tag menunjuk commit pembuat asetnya.
3. **Jangan tambahkan bypass guard** supaya build tampak sukses.
4. Publikasi build baru harus memakai provenance baru, verifikasi ulang, dan persetujuan
   pemilik; jangan diam-diam mengganti aset rilis lama.
5. Ini **lab pribadi**, bukan lisensi resmi MikroTik: jangan klaim aktivasi/kompatibilitas
   tanpa bukti uji; jangan janjikan kompatibilitas semua NIC (SFP hanya offline single-lane).
6. Kunci privat legacy pernah terekspos di repo lama — anggap tidak layak produksi.

## Sources

[1] https://github.com/devlhi/al_MikhroTik_patch/releases/tag/7.23.3
[2] https://github.com/devlhi/al_MikhroTik_patch/releases/tag/7.24.4
[3] https://github.com/devlhi/al_MikhroTik_patch/commit/be9cd230c93c3b40f5e85239d5fbaab49f77e49b
