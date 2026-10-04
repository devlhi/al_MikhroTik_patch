# HANDOFF — Ali Patch Code

Dokumen serah terima untuk developer lain yang mau melanjutkan kerja repo ini.
**Status diperbarui: 2026-10-04 (WITA): ISO belum terdiagnosis (§5); VM pemilik tetap free (§6); audit aset CHR rilis dan boot salinan terisolasi selesai, aktivasi belum diuji (§7).**
Dokumen awal masuk lewat commit `3e2a73b`
atas instruksi pemilik repo (`devlhi`). Ini memori proyek yang ikut Git, bukan
salinan memori pribadi agent atau tempat menyimpan kredensial.

Mulai dari dokumen ini, lalu baca kontrak [guard cakupan](patch-coverage.md).
Kalau melanjutkan kerja, **perbarui dokumen ini** di akhir sesi: commit yang diubah,
tes yang benar-benar dijalankan (termasuk skip/gagal), batas bukti, dan tugas berikutnya.

## Protokol pembaruan memori proyek

Dokumen ini adalah memori proyek bersama (developer manusia dan agent, termasuk
Hermes) yang diwariskan lewat Git, bukan memori pribadi. Aturan pemakaiannya
juga tertulis di [AGENTS.md](../AGENTS.md) dan [CONTRIBUTING.md](../CONTRIBUTING.md).

- **Baca dulu** dokumen ini sebelum bekerja; jangan menganggap ringkasan percakapan
  atau ingatan pribadi sebagai status terbaru.
- **Perbarui setiap sesi** yang menghasilkan perubahan, temuan, keputusan, atau
  status pengujian baru—sebelum commit/push atau penyerahan. Sesi yang hanya membaca
  dan tidak menambah informasi tidak perlu commit kosong.
- Format pembaruan: apa yang berubah (file/commit acuan yang sudah ada), apa yang
  benar-benar diverifikasi dan bagaimana (perintah, mode, jumlah tes, skip/gagal),
  kendala yang tersisa, langkah berikutnya, dan tanggal.
- Bedakan sumber: hasil eksekusi tool, laporan pemilik, dan hipotesis. Jangan
  menyalin hasil tes lama sebagai hasil baru, dan jangan mengubah laporan kegagalan
  menjadi sukses tanpa bukti uji baru.
- Riwayat Git (commit message + diff) mencatat kapan pembaruan HANDOFF dibuat;
  dokumen ini tidak perlu mencatat commit pembaruannya sendiri.
- Ini kewajiban dokumentasi kontributor, **belum dipaksakan hook/CI**. Reviewer
  perlu memeriksa pembaruan HANDOFF; agent lain harus membaca aturan repo tersebut.

## Status singkat

| Hal | Status |
|---|---|
| Cabang kerja sesuai arahan pemilik | `main`; jangan membuat cabang lain tanpa persetujuan |
| Commit fungsional acuan | `be9cd23` — guard cakupan patch NPK; commit setelahnya untuk dokumentasi |
| Rilis 7.24.4 | release biasa + **Latest**; 40 aset; aset TIDAK dibangun ulang dengan guard |
| Rilis 7.23.3 | **prerelease**; tag `7.23.3` + tag build lama; 40 aset; aset TIDAK dibangun ulang |
| Instalasi & boot | **ISO: masalah “load system” masih terbuka (§5). VMDK CHR: VM aktif dan WebFig dapat diakses (§6); asal/hash image belum dikonfirmasi.** Salinan aset VMDK rilis 7.24.4 terbukti boot sampai login di QEMU terisolasi tanpa jaringan (§7) |
| Aktivasi lisensi / upgrade | **VM pemilik tetap free (§6); penyebab belum dibuktikan.** Pada satu aset CHR x86 7.24.4, perubahan file sistem reguler/kernel teramati hanya berupa key NPK sign (§7); bukan bukti penerimaan kode lisensi |

## Apa yang sudah dikerjakan

### 1. Audit flow lisensi (7.17 vs 7.23.3 / 7.24.4)

Ringkasan berikut berasal dari audit sesi sebelumnya, sebelum guard `be9cd23`.
Hasil ini bersifat historis; audit baru satu aset CHR x86 7.24.4 dicatat terpisah di §7.

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

### 5. Laporan percobaan boot VMware (2026-10-04) — masalah masih terbuka

Ini percobaan instalasi/boot yang **dilaporkan pemilik**, bukan reproduksi agent.
ISO belum teridentifikasi, sehingga hasil ini **belum dapat diatribusikan ke tag
7.23.3 atau 7.24.4 tertentu**. Tidak ada perbaikan firmware yang dilakukan pada sesi ini.
Pemilik memilih menyerahkan investigasi ke developer lain.

#### Bukti yang tersedia

- Pemilik mengatakan mencoba instalasi ISO di **VMware Workstation**. Versi VMware
  dan sistem operasi host tidak disebutkan; UI VMware tidak tampak di foto.
- Foto installer menunjukkan disk `/dev/sda`, ukuran yang dilaporkan `18397 MB`,
  pembuatan partisi, dan progress format `RouterOS` / `RouterOS Boot` hingga 100%.
  Salah satu baris format bertumpuk; jangan menganggap transkripnya log lengkap.
- Tiga baris penting yang terbaca pada foto, berurutan:

  ```text
  open /dev/panics failed
  Software installed.
  Press ENTER to reboot
  ```

  Ini membuktikan **installer menampilkan pesan selesai**, bukan bahwa instalasi
  telah terverifikasi atau sistem hasil instalasi dapat boot.
- Laporan lanjutan pemilik, verbatim: **“muncul load system terus”**. Dalam percakapan
  ini dipahami sebagai tertahan di tahap `Loading system…`, tetapi **belum ada foto
  layar pascareboot atau log** untuk memastikan ejaan pesan, durasi, hang diam,
  maupun reboot berulang. Belum ada login/boot sukses yang dilaporkan.
- Foto installer ada dalam percakapan pemilik, **tidak disalin ke repo**; ringkasan
  dan cuplikan teks di atas disimpan di Git agar tidak bergantung pada scratch.

#### Data yang masih perlu diminta developer berikutnya

- Nama ISO lengkap, asal unduhan, versi/arsitektur, ukuran, SHA-256, dan kecocokan
  dengan manifest rilis. Jangan mengasumsikan 7.24.4 hanya karena berlabel Latest.
- Versi VMware/host, firmware BIOS atau UEFI, status Secure Boot bila relevan,
  controller disk, tipe NIC, RAM, vCPU, dan urutan boot.
- Apakah ISO masih tersambung, serta apakah boot berikutnya berasal dari disk
  terpasang atau kembali ke installer CD/DVD.
- Foto/video setelah reboot, durasi menunggu, dan apakah VM restart sendiri.
  Pengaturan dan hasil uji ISO vendor belum diberikan; reproduksi terkontrol belum ada.

#### Koreksi arahan percakapan sebelumnya

- Klaim bahwa `open /dev/panics failed` pasti normal/tidak berbahaya di VM atau
  pasti bukan efek patch **belum dibuktikan untuk percobaan ini**. Pesan yang mirip
  di forum tidak menetapkan penyebab. Hubungannya dengan gejala boot belum diketahui.
- Saran langsung mengganti BIOS/UEFI, controller disk, atau NIC **bukan fix teruji**.
  Klaim umum bahwa RouterOS tidak memiliki driver VMXNET3/VirtIO tidak dijadikan
  dasar diagnosis; dukungan harus diperiksa untuk produk, versi, dan arsitektur
  yang tepat. Jangan mengubah beberapa setting sekaligus atau install ulang
  sebelum mencatat konfigurasi awal dan mengamankan disk percobaan.
- `Software installed`, signature valid, dan tes Python hijau **bukan bukti boot
  atau aktivasi sukses**. Jangan ubah metadata `boot_tested` menjadi sukses.

#### Titik lanjut investigasi (belum dijalankan)

1. Lengkapi identitas ISO, konfigurasi, dan bukti gejala di atas. Buat snapshot/backup;
   jangan menimpa disk VM yang menyimpan satu-satunya bukti percobaan.
2. Siapkan pembanding ISO vendor **dengan versi dan arsitektur yang sama**, di VM
   lab terpisah dengan konfigurasi setara dan disk baru. Verifikasi checksum kedua
   media. Tidak ada instalasi ulang atau pergantian firmware VM yang dilakukan di sesi ini.
3. Bandingkan sampai tahap boot dari disk hasil instalasi, bukan hanya boot installer:
   - keduanya gagal: telusuri faktor bersama (media, konfigurasi, kompatibilitas
     versi/hypervisor); ini **tidak membuktikan** patch bebas masalah;
   - vendor berhasil, patched gagal: memperkuat dugaan masalah artefak/proses patch,
     tetapi belum menentukan loader/kernel atau komponen tertentu sebagai akar sebab.
4. Setelah ada reproduksi, ubah satu variabel per uji dan simpan konfigurasi, hash,
   log tersanitasi serta hasil aktual. Pisahkan bukti boot, login, dan aktivasi.

#### Cakupan sesi penyerahan ini

- Hanya dokumentasi yang diperbarui: HANDOFF memuat laporan VMware dan protokol
  memori bersama; `AGENTS.md` serta `CONTRIBUTING.md` menegaskan kewajiban membaca/
  memperbaruinya; README mengarahkan kontributor ke ketiga dokumen itu. Tidak ada
  edit engine/workflow, build firmware, perubahan kunci/tag/aset, atau uji VM oleh agent.
- Hasil regresi terakhir sebelum penambahan aturan dokumentasi: **213 tes penuh
  normal** dan **26 tes cakupan mode `-O`** pada source `f65ab0f`, semuanya exit 0
  dan **0 skip**. Itu bukan reproduksi atau perbaikan masalah VMware. Suite tidak
  diulang khusus untuk penambahan aturan dokumentasi ini; kode tidak berubah.
- Validasi dokumentasi: 20 link relatif valid, `git diff --check` dan pemeriksaan
  sitasi lulus; pemindaian pola kredensial pada dokumen baru/HANDOFF serta baris
  README yang ditambahkan tidak menemukan temuan baru. Bukan audit keamanan seluruh repo.
- Status saat diserahkan: **masalah boot terbuka; penyebab dan solusi belum terkonfirmasi**.

### 6. VM CHR aktif + percobaan kode lab (2026-10-04) — level tetap free, penyebab belum diketahui

Pemilik melaporkan memasang RouterOS lewat **file VMDK** di VMware (PC lain) dan
meminta kode lisensi lab untuk dicoba sendiri. Asal VMDK (vendor resmi vs hasil
konversi aset patched) **belum dikonfirmasi** — tanpa itu, hasil uji lisensi tidak
bisa diatribusikan ke patch.

Bukti yang tersedia (pisahkan screenshot pemilik dari akses langsung):

- Screenshot Resources: versi `7.24.4 (stable)`, Build Time `2026-09-16 11:32:21`,
  board `CHR VMware`, arsitektur `x86_64`, uptime `00:27:32`. Judul WebFig live
  mengonfirmasi CHR 7.24.4 tetapi menyebut `i386`; perbedaan label belum dijelaskan.
- WebFig System → License dibaca langsung: System ID CHR berhasil diperoleh,
  `Level: free`, kolom renewal/deadline kosong. ID lengkap tidak dipublikasikan
  dalam repo; generator menggunakan nilai yang dibaca dari VM.
- Screenshot Packages menampilkan **13 entri total**, `routeros` bertanda installed
  dan 12 entri lain tidak terpasang. Updater menampilkan installed `7.24.4`, channel
  `stable`, latest `7.24.5`. Tampilan ini tidak membuktikan patch terpasang/tidak.
  Tidak ada download/upgrade oleh agent; pembaruan paket vendor dapat mengganti
  komponen lab dan mengacaukan pembanding, sehingga jangan upgrade saat uji ini.

Tindakan agent sesi ini:

- Kode lisensi CHR lab dibuat dengan private key yang **sudah dipin** di workflow
  (tidak membuat keypair baru; proses generator tidak mencetak kunci), untuk System ID
  VM tersebut. Verifikasi lokal `license_util.parse`: kind `chr`, System ID cocok,
  signature valid terhadap public key repo; file disimpan di Desktop pemilik
  (`ali-lab-license-chr.txt`, izin 600) dan **tidak di-commit**. Tes `test_license_util`
  15/15 lulus sebelum pembuatan.
- Dokumentasi resmi CHR menjelaskan aktivasi/renewal melalui akun MikroTik dan
  `/system license renew`; dokumentasi itu bukan bukti dukungan impor kode lab.[5]
- **Pemilik melaporkan sudah memasukkan kode, tetapi lisensi tidak berubah.**
  Screenshot lanjutan (`image_8621ec.png`, hanya di percakapan, tidak masuk repo)
  menunjukkan `Level: free`, kolom renewal/deadline kosong, dan tindakan
  `Generate New ID` / `Renew License`. Terminal sebagian tertutup jendela License;
  prompt terlihat, tetapi blok yang ditempel, output impor/error, dan permintaan
  reboot **tidak terlihat**. Resources menampilkan uptime `00:00:38`; itu sendiri
  bukan bukti penerimaan lisensi atau reboot akibat kode.
- Ini laporan percobaan pemilik plus observasi screenshot, **bukan reproduksi agent**.
  Aktivasi belum terbukti berhasil; belum bisa menentukan apakah input tidak diproses,
  jalur impor tidak didukung, atau verifier menolak kode. Asal/hash VMDK masih belum ada.
- **Koreksi arahan agent:** sebelumnya agent menyarankan paste blok langsung ke
  Terminal dan menyebut kemungkinan pesan sukses/reboot. Jalur impor itu belum
  diverifikasi untuk CHR ini; arahan tersebut terlalu jauh dan ditarik kembali.
  Jangan menyamakan CHR dengan alur x86 atau menganggap validasi generator membuktikan
  firmware menerima kode. File adalah keluaran generator lab, bukan lisensi resmi.
- `/system license print` sudah diperiksa langsung oleh agent (rincian di bawah).
  Yang masih kurang: output Terminal asli saat pemilik menempel kode serta nama,
  sumber, dan hash VMDK di PC host VMware. Terminal WebFig baru milik agent tidak
  memperlihatkan output percobaan di sesi WinBox pemilik. Jangan mengulang pemasangan
  kode, reboot, upgrade, atau mengganti ID/keypair hanya untuk menebak penyebab.
- Jangan menyimpulkan peluang penerimaan hanya dari scan statis (§1). Jika kode
  ditolak, simpan pesan persis, identitas/hash image, dan hasil lokal sebelum
  menentukan apakah penyebabnya generator, format, key mismatch, atau firmware.
- **Pemeriksaan langsung oleh agent (WebFig + Terminal, semuanya baca-saja):**
  - `/system license print` → System ID sama dengan kode yang dibuat, `level: free`.
  - Mengetik `/system license ` lalu **F1, tanpa Enter** menampilkan help:
    `export`, `generate-new-id`, `get`, `print`, `renew` (serta navigasi `..`).
    Tidak ada subperintah `import`, `input`, atau `paste` yang ditampilkan pada sesi
    ini. Ini **bukan bukti bahwa semua jalur penerimaan blok kunci tidak didukung**;
    help submenu tidak menguji penanganan paste pada console global.
  - WebFig Log menampilkan **16 entri buffer memory** saat diperiksa. Filter CLI
    `/log print where message~"license|key|reboot|shutdown|failure|error"` hanya
    menampilkan reboot pada waktu router `2026-10-04 13:21:19`, melalui terminal
    WinBox dengan akun admin. Identitas manusia yang menjalankannya tidak dibuktikan.
    Tidak ada pesan penerimaan/penolakan lisensi dalam hasil filter **yang masih
    tersedia**; ini bukan bukti bahwa sebelumnya tidak pernah ada pesan.
  - Banner saat membuka Terminal baru memuat pesan critical terdahulu:
    `2026-10-04 12:11:05 ... router was rebooted without proper shutdown` dan login
    failure pada `12:11:09`. Ini terpisah dari hasil filter log saat ini; kaitannya
    dengan percobaan lisensi tidak diketahui. Zona waktu jam router belum dicek.
  - `/system resource print` → uptime 20m25s, `7.24.4 (stable)`, build-time
    `2026-09-16 11:32:21`, `x86_64`, board `CHR VMware`, RAM 1280 MiB, HDD 89.2 MiB,
    `write-sect-since-reboot = write-sect-total = 424`.
  - `/system package print` → 13 entri: `routeros 7.24.4` dan 12 entri lain
    berflag `XA` (`X - DISABLED`, `A - AVAILABLE`) tanpa versi terpasang yang
    ditampilkan. Daftar ini bukan indikator patch.
  - Kesimpulan terbatas: **level tetap free dikonfirmasi langsung**, bukan hanya
    screenshot. Agent tidak mengulang paste kode dan tidak mengetahui output asli
    percobaan; tidak bisa menyatakan kode diabaikan atau verifier menolaknya.
    Asal VMDK masih belum diketahui; penerimaan kode/penyebab belum dibuktikan.
- Agent hanya membaca VM. Tidak mengunggah/memasang lisensi, mengubah konfigurasi,
  meminta renewal, mengganti ID, mengunduh paket, atau me-reboot.

- Verifikasi sesi ini: `env -u PYTHONPATH venv/bin/python -B -m unittest discover
  -s tests -p test_license_util.py -v` → **15 tes, OK**; artefak lisensi dibaca ulang
  dan diverifikasi lokal. Engine tidak diubah; suite penuh tidak diulang untuk tugas ini.
  Pada pemeriksaan langsung lanjutan, agent menjalankan perintah baca-saja di VM
  dan memperbarui dokumentasi; suite tidak diulang, tidak ada build/perubahan engine
  atau konfigurasi VM.

### 7. Audit aset CHR 7.24.4 dan boot salinan terisolasi (2026-10-04) — aktivasi belum terbukti

Audit statis membaca salinan unduhan; uji boot hanya menulis overlay disposable.
Engine, keypair, tag, aset rilis, dan VM pemilik tidak diubah; dokumentasi ini
bertambah. Artefak biner dan JSON/probe tersimpan sementara di scratch
`~/.hermes/cache/scratch/chr-7244-check/`; **firmware tidak masuk Git**. Scratch
bisa terpangkas — ringkasan, fingerprint, dan batas bukti di bawah dipertahankan
sebagai catatan tahan lama.

**Identitas artefak yang diperiksa:**

- Aset rilis `ali-patch-code-x86-chr-7.24.4-patched.vmdk.zip` (asset id 604788961,
  65.482.116 byte): hash arsip cocok dengan digest metadata GitHub. Setelah
  konversi ke raw, GPT valid (CRC header+entri).[7]
- Pembanding vendor `chr-7.24.4.img.zip` dari URL resmi MikroTik: GPT valid,
  zip CRC lulus.[6] **Bukan verifikasi kriptografis keaslian** — HTTPS dan hash
  lokal dicatat apa adanya. Fingerprint lengkap berikut untuk reproduksi,
  bukan material kunci:

  | Artefak | SHA-256 |
  |---|---|
  | Arsip VMDK rilis | `b0635638f96ec073d75c9ef028812a64aaec11e27f079a2ad4b1dd9337d9bf7a` |
  | VMDK rilis sebelum konversi | `14dc40bce8f85de0fabad4dd641b14b4f71bb5a0a0c030beef96c243296fc728` |
  | Raw hasil konversi rilis | `5ad08494fb0144ec98298169c5477733fc91babe461abee17d191cca1a6781de` |
  | Arsip image vendor | `dd678564de45eb7ae27b22f5fb4bd45a67970aed842e1cea96f5dd018d7b00ae` |
  | Raw vendor | `e87eaa06af9e29f5946d951a0595de56d6e8a972d023e34e56583412265063e7` |

- Dari kedua disk diekstrak `/EFI/BOOT/BOOTX64.EFI` dan `/var/pdb/system/image`
  (NPK `system`, paket tunggal). NPK rilis diverifikasi signature-nya dengan
  pasangan kunci custom repo → lulus; NPK vendor diverifikasi dengan dua public
  key vendor yang dikonfigurasi repo → **False**. Penyebab kegagalan verifier
  belum diketahui; jangan menyimpulkan key mismatch atau keaslian unduhan
  sudah terverifikasi secara kriptografis.

**Hasil pemindaian byte (scanner dengan kontrol positif/negatif lulus):**

- SquashFS paket `system` dibaca **582/582 file reguler** per path case-sensitive
  (`unsquashfs -cat` + verifikasi ukuran; ekstraksi penuh ke APFS tidak dipakai
  karena tabrakan nama `xt_DSCP.ko`/`xt_dscp.ko` dkk). Kernel EFI didekompresi
  penuh (payload LZMA + window CPIO initramfs yang dipakai patcher).
- **Kunci lisensi custom: 0 kemunculan** pada seluruh cakupan yang dipindai
  (kernel dekompresi, initramfs, seluruh file SquashFS, NPK mentah, EFI mentah).
- **Kunci lisensi vendor: juga 0 kemunculan bentuk raw** pada cakupan yang sama.
  Probe tambahan untuk beberapa bentuk encoded16/split16/reversed32 hanya
  mencakup `keyman`, `sys2`, EFI, kernel dekompresi dan window initramfs, bukan
  seluruh file. Hasil probe tambahan juga nol; lokasi/representasi verifier
  lisensi aktual 7.24.4 **belum ditemukan**.
- Kunci NPK sign: kernel EFI disk memuat 2 kemunculan setelah dekompresi;
  salinan EFI di NPK memuat 2 juga; tiga file SquashFS di bawah masing-masing
  memuat 1. Peran key vendor pada pembanding berubah menjadi custom pada rilis.
  Jumlah agregat scanner **11** mencakup kernel dan window initramfs yang
  tumpang-tindih; jangan menyebutnya 11 lokasi byte independen pada disk.

**Perbandingan seluruh file reguler rilis vs vendor (582 file):**

- **579 file identik byte-per-byte.** Tiga file berbeda: `bndl/security/nova/bin/ssh`,
  `nova/bin/installer`, `nova/bin/sys2` — masing-masing **seluruh perbedaannya
  dijelaskan oleh penggantian byte kunci NPK sign** (1 kemunculan per file).
- Kernel dekompresi: perbedaan seluruhnya dijelaskan 2 kemunculan kunci NPK sign.
- `nova/bin/keyman`, `nova/bin/loader`, `nova/bin/mode` **identik dengan vendor**.

**Interpretasi dan batas:**

- Pada baseline 7.17 (§1), byte kunci lisensi custom teramati di
  `keyman`/`loader`/`mode`. Pada 7.24.4, byte kunci lisensi vendor tidak
  ditemukan dalam representasi yang dicari. Pada **satu aset CHR x86 7.24.4**
  yang dibandingkan, perubahan 582 file reguler dan kernel dekompresi seluruhnya
  dijelaskan oleh penggantian kunci NPK sign. Ini tidak menambah uji terhadap
  semua image, arsitektur, atau rilis 7.23.3. Hubungan dengan level `free` pada
  VM pemilik masih merupakan hipotesis **bila** VMDK-nya berasal dari aset rilis —
  asal VMDK pemilik masih belum dikonfirmasi, jadi atribusi tetap terbuka.
- Hasil negatif pemindaian berlaku untuk representasi dan cakupan yang diuji;
  **bukan bukti mutlak** verifier 7.24.4 tidak memakai kunci tersebut dalam
  bentuk lain, dan bukan bukti firmware pasti menolak kode lab (belum ada uji
  aktivasi terkontrol).

**Review independen jalur pipeline (subagent, diverifikasi ulang oleh agent):**

- Jalur `patch.py kernel` (dipakai untuk `BOOTX64.EFI` CHR) **tidak punya guard
  cakupan**; guard `be9cd23` hanya di jalur `patch.py npk` (docs/patch-coverage.md
  sudah mengakui batas ini).
- Probe sintetis (dijalankan ulang oleh agent, reproduksi lulus): `patch_bzimage`
  hanya mem-patch **CPIO pertama** — salinan pola di luar CPIO pertama tidak
  tersentuh dan tetap ada di output; jika semua marker di luar CPIO pertama,
  terjadi **0 penggantian tanpa error**. `find_7zXZ_data` tidak mengenali stream
  XZ ber-check CRC64 pada fixture; fixture tiga stream mengembalikan stream
  valid tetapi bukan yang terakhir. **Jalur EFI x86 yang diperiksa memakai
  offset/panjang payload, bukan finder XZ itu.** Probe sintetis ini tidak
  menetapkan penyebab kegagalan lisensi, dan bukan bukti perlu memperluas
  penggantian ke semua byte kernel.
- Aset rilis 7.24.4 dibangun di `bd2dc61` **pra-guard**: `patch_npk_file` lama
  menandatangani tanpa syarat cakupan, jadi nol penggantian kunci lisensi tetap
  menghasilkan aset signed. Blok env kunci `bd2dc61` vs `main` identik —
  generator dan aset memakai keypair yang sama.
- Generator `lic_gen_chr` konsisten secara lokal (round-trip System ID pada
  5 nilai batas lulus). Empat byte tetap `0,87,134,244`, **jika** ditafsirkan
  sebagai timestamp uint32 little-endian, berarti 2100-01-01 UTC; jika signed,
  berarti 1963-11-25 UTC. Makna field/layout payload terhadap verifier 7.24.4
  belum dibuktikan; byte tunggal 244 bukan tanggal tersendiri.

**Uji boot salinan rilis (bukti baru, terpisah dari §5 ISO):**

- Salinan raw aset rilis di-boot di QEMU lokal terisolasi (TCG, 512 MB, **tanpa
  perangkat jaringan**, overlay qcow2 — sumber tidak diubah, digest diverifikasi
  ulang). Hasil: banner `MikroTik 7.24.4 (stable)`, prompt `CHR Login:`,
  login akun default tanpa password mencapai prompt ganti password. Banner
  critical menampilkan `router was rebooted without proper shutdown`; proses
  QEMU pertama memang dihentikan tanpa shutdown guest sebelum boot ulang,
  tetapi sebab pesan itu tidak diperiksa lebih jauh. **Boot sampai login
  terbukti; aktivasi lisensi TIDAK diuji** pada salinan ini. Proses QEMU sudah
  dihentikan; metadata rilis `boot_tested` tidak diubah.

**Verifikasi baru oleh agent utama:** `test_license_util.py` → 15 OK;
`test_patch_coverage*.py` → 26 OK mode normal dan 26 OK mode `-O` (empat tes
integrasi nyata ikut berjalan, 0 skip); `test_patch7_branding.py` → 14 OK.
Probe sintetis reviewer dijalankan ulang → exit 0. Suite penuh tidak diulang.
Konfigurasi enam nilai key workflow pada `bd2dc61` vs `main` dibandingkan
secara lokal → seluruhnya sama; fungsi NPK pra-guard diperiksa lewat `git show`.
Nilai key tidak dicetak atau ditambahkan ke dokumen ini.

Percobaan helper boot tambahan tidak berjalan karena `timeout` tidak tersedia
(exit perintah 127; wrapper shell sempat melaporkan 0). Tidak ada hasil
`/system license print` dari helper itu; ini bukan uji lisensi. Proses QEMU
utama telah dikonfirmasi `exited`, sumber raw tetap cocok dengan fingerprint.

**Belum dilakukan:** uji penerimaan kode lisensi pada salinan QEMU (System ID
salinan belum dibaca), rebuild, dan perubahan engine. Tidak ada kode lab yang
dikirim ke salinan. Semua tindakan lanjutan tersebut menunggu keputusan pemilik.

## Yang bisa / perlu dikerjakan selanjutnya

1. **Lanjutkan investigasi laporan boot VMware** (lihat §5): identifikasi ISO dan
   konfigurasi dulu, lalu bandingkan dengan ISO vendor versi/arsitektur yang sama
   pada VM terpisah dengan konfigurasi setara. Simpan bukti dan batas kesimpulan.
2. **Pisahkan bukti aktivasi dari bukti boot/signature** — gunakan mekanisme lisensi
   resmi yang berlaku. Panel custom-lab dan tes `tests/test_license_*.py` tidak
   membuktikan lisensi diterima firmware 7.23.3/7.24.4. Temuan §7 tidak menentukan
   penyebab runtime. Lengkapi provenance VMDK pemilik dan mekanisme penerimaan
   resmi/terverifikasi sebelum memberi prosedur tulis; jangan mengganti keypair
   atau menerbitkan ulang rilis untuk menutupi pengujian yang belum selesai.
3. **Build baru memakai guard, bila disetujui** — workflow manual `patch7.yml` di `main`.
   Kalau satu mapping wajib tetap tidak ditemukan, build **harus gagal**. Catat log
   tersanitasi dan jangan bypass guard. Jangan pindahkan tag/aset terbit untuk menyamarkan
   build baru sebagai build lama. Batas guard jalur mandiri tetap harus dicatat;
   probe sintetis §7 menunjukkan jalur kernel bisa nol-penggantian tanpa error,
   bukan bukti bahwa memperluas cakupan akan memperbaiki aktivasi.
4. **Pertimbangkan guard jalur mandiri** `kernel` / `block` / `netinstall` dan CLI
   `npk.py sign`. Saat ini guard paket belum berlaku di sana; desain kontrak dan
   tes negatif dahulu, bukan klaim jalur tersebut sudah terlindungi.
5. **Reproduksi kandidat bug dari catatan sesi lama** — `encode_version`, `lic_parse_ros`,
   dan truncation belum diuji ulang dalam handoff ini. Sebagian batas CPIO/finder
   XZ sudah direproduksi dengan fixture sintetis (§7), bukan runtime firmware.
   Jangan menyatakan bug baru sebagai penyebab aktivasi tanpa bukti keterkaitan.
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
[5] https://help.mikrotik.com/docs/spaces/ROS/pages/18350234/Cloud+Hosted+Router+CHR — MikroTik CHR licensing docs (current page)
[6] https://download.mikrotik.com/routeros/7.24.4/chr-7.24.4.img.zip
[7] https://api.github.com/repos/devlhi/al_MikhroTik_patch/releases/tags/7.24.4
