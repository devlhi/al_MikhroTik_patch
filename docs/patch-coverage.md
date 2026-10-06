# Pemeriksaan cakupan patch NPK

Pemeriksaan ini mencegah paket sistem ditandatangani ketika penggantian byte
wajib tidak ditemukan. **Ini bukan perbaikan aktivasi lisensi** dan tidak
membuktikan firmware dapat boot, dipasang, di-upgrade, atau menerima lisensi.

## Kontrak

- Setiap pasangan pola dalam `key_dict` untuk paket bernama `system` wajib
  menghasilkan sedikitnya satu penggantian pada keseluruhan paket: kernel
  FILE_CONTAINER yang didukung dan file reguler SquashFS dijumlahkan.
- Tidak semua file atau fragmen harus memuat pola. Dua pola boleh ditemukan
  pada bagian berbeda dari paket yang sama.
- Nol kecocokan untuk satu pola saja menghentikan proses sebelum repack,
  signing dan penyimpanan output. Input dan output yang sudah ada tidak
  ditimpa pada kegagalan cakupan.
- Pemeriksaan memakai `ValueError`, bukan `assert` atau mode opt-in; tetap
  aktif dengan Python `-O`.
- Pada batas paket `system`, `key_dict` harus tidak kosong; setiap pasangan
  pola harus berupa bytes, tidak kosong, berbeda, dan sama panjang. Mapping
  ditolak jika nilai pengganti mengandung pola lama mana pun (containment).
  Pemeriksaan containment saja tidak mencegah kecocokan baru yang terbentuk
  melintasi batas byte pengganti dan byte di sekitarnya.
- Semua kecocokan dihitung dan dicari hanya pada setiap fragmen input asli.
  Penggantian diterapkan pada offset asli non-overlap, sehingga byte hasil
  penggantian tidak pernah menjadi target. Rentang kecocokan asli antar-pola
  yang tumpang-tindih ditolak dengan `ValueError` sebelum statistik fragmen
  diubah atau log penggantian dicetak. Pengulangan pola yang sama memakai
  semantik non-overlap `bytes.count`/`bytes.replace`.
- Pada SquashFS, setiap inode file reguler dibaca dan di-patch hanya sekali
  per traversal berdasarkan pasangan `(st_dev, st_ino)`. Beberapa nama
  hardlink untuk inode yang sama tidak menambah hitungan atau mencari ulang
  byte hasil penggantian. Penulisan melalui satu nama mempertahankan inode
  bersama; hubungan hardlink tetap bertahan setelah repack. File berisi byte
  identik pada inode berbeda tetap di-patch dan dihitung masing-masing.
- Paket tambahan non-`system` tetap melalui operasi sign-only dan tidak
  menjalankan validasi `key_dict`. Dalam NPK multi-package, kegagalan satu
  paket sistem membatalkan signing seluruh file.
- Ekstraksi dan repack menggunakan direktori sementara unik dan literal argv
  untuk `unsquashfs`/`mksquashfs`, bukan perintah shell. Repack memakai
  `-noappend` tanpa mengubah pengaturan kompresi. Direktori dibersihkan juga
  saat proses gagal. Traversal tidak mengikuti symlink file eksternal.

## Laporan

`patch_npk_package()` mengembalikan laporan paket. `patch_npk_file()`
mengembalikan daftar laporan setelah penyimpanan berhasil. Setiap mapping
memiliki indeks, hitungan `kernel`, `squashfs`, dan `total`; nilai kunci tidak
dicetak. Status `coverage-passed` hanya berarti syarat kecocokan literal
terpenuhi, bukan aktivasi berhasil. Status `not-system` berarti guard tersebut
tidak berlaku pada paket tambahan.

API fragmen (`patch_initrd_xz`, `patch_elf`, `patch_pe`, `patch_kernel`,
`patch_bzimage`) mempertahankan return bytes/bytearray sebelumnya. Parameter
`stats` opsional meneruskan hitungan ke pemeriksaan tingkat paket. Fragmen
kosong kecocokan tidak ditolak sendiri.

## Batas cakupan

Guard ini berada pada jalur `patch_npk_file()` / perintah `patch.py npk`.
Perintah terpisah `kernel`, `block`, `netinstall` dan CLI `npk.py sign`
**belum** menggunakan guard tingkat paket ini. Tidak ada jaminan bahwa semua
copy pola lama terhapus, bahwa pola yang cocok benar-benar merupakan verifier
runtime, atau bahwa output diterima perangkat. Tetap diperlukan bukti boot
serta aktivasi yang terpisah.

Pada audit statis tujuh NPK rilis 7.23.3, fingerprint manifest dan signature
custom lolos, tetapi byte kunci lisensi yang dicari tidak teramati pada data
yang berhasil dipindai. Ada warning kandidat XZ; ini bukan bukti absensi
mutlak. Rilis tersebut tidak diubah, dibangun ulang, atau dipublikasikan ulang
oleh penambahan guard ini. Jangan menambahkan bypass guard untuk membuat
build tampak berhasil ketika target penggantian belum diketahui.

## Pengujian

Tes hanya menggunakan pola dan NPK sintetis. Kunci konfigurasi dan firmware
asli tidak dipakai untuk pengujian transformasi atau signing.

```sh
python -B -m unittest discover -s tests -p 'test_patch_coverage*.py' -v
python -O -B -m unittest discover -s tests -p test_patch_coverage.py -v
```

`test_patch_coverage.py` memeriksa positif/negatif, laporan, API fragmen,
pembersihan workspace, kegagalan repack, dan pemisahan sign-only. Tes
`test_patch_coverage_integration.py` memakai tool SquashFS nyata untuk pack,
extract dan membaca ulang byte hasil; signing tetap di-mock. Tes integrasi
secara eksplisit di-skip jika tool belum tersedia—skip bukan bukti lulus.

## Addendum: kebijakan runtime CHR x86 7.24.4

`patch.py npk --runtime-policy chr-x86-7.24.4` memilih kebijakan sempit,
opt-in dan fail-closed. API `patch_npk_file` / `patch_npk_package` menerima
`runtime_policy` serta `license_public_key` (pola lama peran LICENSE) secara
eksplisit; CLI mengambil peran itu dari `MIKRO_LICENSE_PUBLIC_KEY`, **bukan
urutan dictionary**. Tanpa opsi, penggantian/guard generik tetap berlaku.
Opsi ini dapat dibatalkan dengan membangun ulang dari sumber pristine tanpa
opsi; bukan transformasi balik terhadap paket yang sudah di-patch.

- Hanya NPK tunggal `system`, versi persis `7.24.4.final`; multi-package,
  versi/arsitektur tak dikenal, part wajib hilang/duplikat ditolak sebelum
  signing. Pembacaan preflight tidak memakai `__getitem__` yang membuat part.
- Arsitektur authoritative harus `b'i386'` sebelum SIGNATURE. Satu marker
  tambahan `b'I'` hanya diizinkan setelah SIGNATURE, sesuai layout sumber CHR
  yang dilaporkan parent; maknanya belum diketahui. Part itu tidak dihapus atau
  diubah. Duplikat/konflik lain ditolak; tidak ada propagasi arsitektur spekulatif.
- Hanya `nova/bin/loader` persis, regular bukan symlink/hardlink, yang boleh
  mempertahankan satu anchor immediate LICENSE terverifikasi decoder ELF i386.
  Delapan dword adalah **satu anchor**, bukan delapan replacements. Nol/lebih
  dari satu anchor ditolak. `keyman` dan `mode` juga wajib regular tanpa alias
  dan masing-masing menghasilkan ≥1 penggantian LICENSE nyata.
- Seluruh mapping dan envelope instruksi diperiksa overlap pada byte pristine
  **sebelum** anchor loader dikecualikan. Literal LICENSE dan seluruh mapping
  lain (termasuk signing) tetap diproses. Indeks mapping asli/hitungan aktual
  dipertahankan; laporan `preserved_anchors` memuat path, role, `count: 1`,
  `counted_as_coverage: false`. Anchor yang dipertahankan bukan coverage.
  Tidak ada bypass guard, perubahan check `sys2`, atau pelemahan signature.
- Mtime file reguler dipertahankan saat penulisan (juga jalur generik). Kebijakan
  ini memeriksa uid/gid sumber on-image lewat `unsquashfs -lln -full`, menolak
  selain 0/0, lalu repack `-all-root` dan `-mkfs-time` dari uint32 superblock
  SquashFS v4 sumber, bukan waktu saat build. Listing sumber/hasil dibandingkan
  untuk tipe, mode, uid/gid, mtime detik, ukuran non-direktori dan target symlink.
  Dua hasil ekstraksi juga dibandingkan untuk tipe/mode/mtime, device metadata,
  target symlink dan kelompok hardlink. Perubahan metadata atau format listing
  yang tidak dikenali membatalkan signing/output. Panjang byte direktori dapat
  berubah karena packing; xattrs tetap di luar kontrak (`-no-xattrs` seperti
  jalur generik). Ekstraksi tool yang gagal (misalnya special file tanpa izin)
  tetap gagal, tidak dinormalisasi diam-diam.
- Ekstraksi policy memakai `umask=0` **hanya pada child subprocess POSIX**
  untuk mempertahankan mode asli. Umask parent tidak diubah; workspace tetap
  private (0700) dan file output mengikuti umask caller. Ini berdasarkan
  reproduksi sumber nyata: caller umask 077 menyebabkan 582 file reguler
  kehilangan bit group/other (contoh 0755 menjadi 0700), sedangkan roundtrip
  dengan child umask 0 menghasilkan nol delta pada 893 entri. Kedua ekstraksi
  (sumber dan verifikasi) memakai aturan sama; parity tetap wajib, bukan bypass.
  Host non-POSIX menolak ekstraksi policy ini secara eksplisit.

Tes baru `tests/test_chr_runtime_policy.py` memakai ELF/NPK/kunci sintetis saja,
mock signing, dan SquashFS nyata jika tersedia. Jalankan normal serta `-O`:

```sh
python -B -m unittest discover -s tests -p test_chr_runtime_policy.py -v
python -O -B -m unittest discover -s tests -p test_chr_runtime_policy.py -v
```

Kebijakan ini mengikuti hasil diagnostik runtime yang dilaporkan parent;
tes sintetis tidak membuktikan firmware produksi boot atau menerima lisensi.
Build final, verifikasi signature nyata, boot/login dan persistensi aktivasi
harus diuji terpisah. Kebijakan tidak menyatakan dukungan versi/produk lain.

## Addendum: kebijakan installer x86 7.24.4

`patch.py npk --runtime-policy x86-installer-7.24.4` merupakan pilihan eksplisit
untuk paket sistem installer x86 yang sudah dikualifikasi, bukan autodeteksi
produk dan bukan dukungan semua versi. Kebijakan generik tanpa opsi serta
kebijakan CHR tetap terpisah.

- Wire NPK pristine harus tepat SHA-256
  `46de2e3d61a6f5cdb7142f5cb62e3f2e4a28e283ef4fa17984b5511882031a94`.
  Versi `7.24.4.final`, paket tunggal `system`, authoritative `i386`, dan aturan
  marker `I` tetap wajib. Paket termodifikasi, repatched, multipackage, atau
  hanya berlabel versi sama tidak diterima. API langsung `patch_npk_package`
  wajib menerima `source_npk` berupa bytes wire asli lengkap, bukan hash atau
  reserialization objek parsed. Raw digest, outer envelope, batas setiap part
  dan fingerprint state parsed diperiksa bersama. API file/CLI membaca sekali
  dan mem-parsing bytes immutable yang sama dengan yang dipin.
- Fingerprint masing-masing `loader`, `keyman`, dan `mode` dipin sebelum
  transformasi. Satu envelope instruksi LICENSE loader dipertahankan setelah
  pemeriksaan decoder dan overlap; **tidak dihitung sebagai coverage**.
  Penggantian LICENSE nyata pada `keyman` dan `mode` tetap wajib.
- Pemeriksaan metadata, representasi sumber, seluruh mapping dan kegagalan
  sebelum signing/output mengikuti kontrak runtime di atas. Tidak ada fallback
  ke policy generik ketika kualifikasi installer gagal.
- Caller workflow harus mengidentifikasi paket sistem melalui metadata, bukan
  menebak nama file. Add-on tidak menerima runtime policy; operasi sign-only
  generik add-on tidak membuktikan runtime installer.

Dasarnya ialah uji A/B disk x86 terpasang yang terisolasi: varian loader generik
mengalami kegagalan boot, sedangkan varian preservasi loader mencapai login dan
mempertahankan Level 6 setelah dua reboot serta cold restart. Ini bukti satu
konfigurasi QEMU BIOS/IDE tanpa NIC, bukan jaminan Mini PC, UEFI, VMware,
non-x86, atau firmware hasil rebuild lain. Bukti terpisah disimpan dalam
[investigasi runtime installer](evidence/x86-installer-runtime-investigation-20261005T181703Z-9c41b8a2.json).

Tes `tests/test_x86_installer_runtime_policy.py` memeriksa pin, metadata,
penolakan input tidak dikenal/repatched, preservasi anchor dan coverage wajib.
Tes sintetis, verifikasi sumber dan boot/aktivasi firmware tetap merupakan
bukti yang berbeda; hasil tes tidak boleh dipindahkan ke aset rilis baru.

## Opt-in caption di bawah logo ASCII terminal — CHR x86 7.24.4

**Koreksi permintaan pemilik:** keenam baris ASCII MikroTik asli tetap utuh;
plain text `Ali Media Patch` berada tepat di bawahnya, dengan dua spasi indentasi.
Tidak mengklaim kecocokan screenshot referensi karena gambar tidak tersedia untuk
inspeksi. Interpretasi sebelumnya yang mengganti art menjadi block `ALI MEDIA
PATCH` sudah superseded; bukti build/runtime lama tetap historis di HANDOFF §19.

**Temuan offline:** ASCII art versi ini bukan string inline di ELF. `nova/bin/login`
membaca resource `nova/lib/console/logo.txt`. Fitur ini mengubah byte resource logo
firmware yang sebenarnya, **bukan `/system note`**, dan tidak memodifikasi instruksi
ELF, kunci, atau perilaku lisensi. Jangan mengklaim ada offset ASCII art di ELF;
offset ELF yang dilaporkan adalah referensi path resource, bukan art itu sendiri.

API `patch_npk_file`, `patch_npk_package`, dan `patch_squashfs` menerima keyword-only
`terminal_banner='chr-x86-7.24.4-ali-media-patch'`. Default `None` tidak mengubah
logo. Opsi CLI NPK berikut tetap melewati guard cakupan dan signing yang sudah ada;
konfigurasi kunci yang sah harus tersedia seperti build sebelumnya (jangan cetak
nilai). Gunakan sumber pristine dan output baru di lab:

```sh
python -B patch.py npk /path/to/pristine/system.npk \
  --runtime-policy chr-x86-7.24.4 \
  --terminal-banner chr-x86-7.24.4-ali-media-patch \
  -O /path/to/new/banner-system.npk
```

Untuk verifikasi byte **tanpa membaca kunci atau membangun/sign firmware**, CLI
terpisah hanya membaca extracted tree dan membuat satu salinan logo baru:

```sh
python -B patch.py terminal-banner /path/to/extracted-root \
  --policy chr-x86-7.24.4-ali-media-patch -O /path/to/new/logo.txt
```

Output harus belum ada (`xb`); tidak ada overwrite/in-place pada CLI ini. Output
logo saja **bukan firmware siap boot**. API bytes murni tersedia sebagai
`terminal_banner.patch_terminal_banner(data, consumer, policy=POLICY)` dan
mengembalikan `(replacement_bytes, report)`; `consumer` adalah byte login ELF.

Kontrak fail-closed:

- Allowlist NPK tunggal `system`, `7.24.4.final`, authoritative `i386`; hanya marker
  `I` sesudah SIGNATURE boleh menjadi part arsitektur kedua. Part hilang/duplikat,
  arsitektur/versi/policy lain dan multi-package ditolak.
- Target persis `nova/lib/console/logo.txt`; logo dan consumer wajib file reguler
  tanpa hardlink/symlink dan ancestor direktori tidak boleh symlink.
- Anchor logo adalah **seluruh file original 510 byte atau caption output 527 byte**,
  bukan pencarian substring longgar. Hasil block-art lama, partial/duplikat/trailing
  bytes/format baru ditolak; gunakan original pristine untuk rebuild. ELF consumer
  wajib ET_EXEC ELF32 little-endian i386,
  fingerprint pinned, satu anchor `/nova/lib/console/logo.txt\0` seluruhnya di
  tepat satu PT_LOAD read-only non-executable. Missing/ambiguous/out-of-bounds
  segment ditolak. Tidak ada offset patch hard-coded atau fallback spekulatif.
- Consumer pinned membaca delapan baris (index 0..7). Baris kosong index7 diganti
  `b'  Ali Media Patch'`, tepat setelah enam baris MikroTik index1..6 yang tetap
  byte-identical. Leading blank index0 dan footer historis index8 tetap utuh.
  Resource teks tumbuh **510 → 527 byte (+17)**; tidak memerlukan same-length
  patch ELF karena ELF consumer tidak diubah. Jumlah newline tetap9; offset
  sebelum caption tetap, dua newline terakhir bergeser17. Tidak ada NUL/format
  placeholder/control baru. Footer bukan klaim versi runtime OS.
  Output SHA-256 `c320009b2c6fabc9c025b245a4396ef6563c43a6e11cb6cade10a3b97d6abf0c`.
- Laporan logo terpisah di `report['terminal_banner']`; tidak menambah hitungan
  `replacements` mapping/coverage LICENSE. Logo saja tidak bisa meloloskan guard.
  `size` adalah ukuran input; `output_size=527` dan `size_delta=17` saat patch
  original. Exact output memberi `status=already-patched`, `replacements=0`,
  `size_delta=0` (idempoten untuk logo, bukan seluruh proses patch NPK).
- Repack opt-in tetap memeriksa metadata/mtime/mode/uid/gid/link/SquashFS time.
  Hanya ukuran target logo yang sudah tervalidasi di expected inventory berubah
  sesuai report; ukuran source harus cocok, semua field lain tetap. Ukuran logo
  salah ataupun ukuran file lain berubah tetap gagal sebelum signing/output.
  POSIX/SquashFS tools diperlukan. Xattrs tetap
  di luar kontrak. Build dari pristine tanpa flag membatalkan pilihan branding;
  jangan menimpa hasil build/publikasi lama. Workflow tidak di-wire otomatis.

Tes `tests/test_terminal_banner.py` mencakup ELF sintetis (fingerprint test-only),
validasi positif/negatif, CLI no-key, idempotensi, default unchanged, hardlink dan
symlink, metadata, pemisahan statistik, real SquashFS/NPK roundtrip dan guard gagal
sebelum signing/output. Inspeksi vendor read-only opsional di-skip bila scratch
bukan tersedia; hasil tes bukan bukti boot atau tampilan terminal runtime.

```sh
python -B -m unittest discover -s tests -p test_terminal_banner.py -v
python -O -B -m unittest discover -s tests -p test_terminal_banner.py -v
```
