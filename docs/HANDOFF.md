# HANDOFF — Ali Patch Code

Dokumen serah terima untuk developer lain yang mau melanjutkan kerja repo ini.
**Status diperbarui: 2026-10-04 (WITA): ISO belum terdiagnosis (§5); VM pemilik tetap free (§6). Verifier aset CHR x86 7.24.4 memakai anchor vendor dalam delapan immediate (§9). Engine immediate x86 kini ter-commit daf390f (Capstone + preflight overlap, review delta lulus; §11); aktivasi tetap belum terbukti, disk lab masih reboot-loop (§9).**
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
| Commit fungsional acuan | `daf390f` — matcher immediate x86 dua-round ter-review (Capstone, preflight overlap); sebelumnya `be9cd23` guard cakupan patch NPK |
| Rilis 7.24.4 | release biasa + **Latest**; 40 aset; aset TIDAK dibangun ulang dengan guard |
| Rilis 7.23.3 | **prerelease**; tag `7.23.3` + tag build lama; 40 aset; aset TIDAK dibangun ulang |
| Instalasi & boot | **ISO: masalah “load system” masih terbuka (§5). VMDK CHR: VM aktif dan WebFig dapat diakses (§6); asal/hash image belum dikonfirmasi.** Salinan aset VMDK rilis 7.24.4 terbukti boot sampai login di QEMU terisolasi tanpa jaringan (§7) |
| Aktivasi lisensi / upgrade | **VM pemilik tetap free (§6). Aset rilis: `free` → paste → reboot → `free` (§7); anchor vendor yang terlewat pola literal kini terkonfirmasi untuk satu aset (§9). Approval versi source lama ditahan oleh defect overlap (§10); round 2 kini lulus review delta dan diterima parent pada fingerprint tercatat untuk scope sintetis (§11). Lab belum login dan aktivasi belum terbukti.** |

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

### 7. Audit aset CHR 7.24.4, boot dan uji kode pada salinan terisolasi (2026-10-04) — level tetap free

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
  bentuk lain. Saat audit statis belum ada uji aktivasi; uji runtime lanjutan
  di bawah mengonfirmasi level tetap `free`, tetapi tidak menetapkan penyebabnya.

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

**Uji boot awal salinan rilis (sebelum uji aktivasi berikut; terpisah dari §5 ISO):**

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

**Uji aktivasi terkontrol pada salinan terisolasi (baru, 2026-10-04):**

Probe `probe_license_runtime.py` (scratch): overlay qcow2 segar di atas raw aset
rilis (digest dicek sebelum/sesudah), QEMU tanpa NIC, login default salinan,
lalu paste satu blok kode lab untuk System ID salinan itu (dibuat dengan keypair
ter-pin workflow; `license_util.parse` lulus lokal). Hasil berurutan:

1. `level: free` sebelum paste; versi/build-time sama dengan VM pemilik.
2. Paste blok → **konsole global menangani paste** (ada jalur impor; koreksi §6
   konsisten): tampil `line 1 of 2/3/4>` lalu
   **`You must reboot before new key takes effect. Reboot? [y/N]:`**
3. Jawab `y` → guest reboot bersih → login ulang →
   **`level: free` tetap; System ID tidak berubah; filter log kosong.**

Pada aset rilis 7.24.4 (build pra-guard `bd2dc61`), console mengenali blok
kode dan meminta reboot; sesudah reboot **aktivasi tidak terjadi**. Pesan itu
**bukan bukti signature diterima secara kriptografis atau kode tersimpan**.
Ketiadaan jalur paste bukan penjelasan untuk uji ini. Hasil ini direproduksi
agent secara terkontrol, terpisah dari laporan pemilik (asal VMDK pemilik belum
terkonfirmasi). Hasil scan menunjukkan hanya penggantian byte key NPK-sign
yang teramati; lokasi/representasi verifier lisensi tetap belum diketahui.
Jadi **penyebab level tetap `free` belum dibuktikan**; jangan mengubah hipotesis
kunci tak tertanam menjadi kesimpulan, atau menjanjikan bahwa memperluas
patch kernel/CPIO pasti memperbaikinya.

Bukti ringkas yang disanitasi disimpan tahan lama di
[JSON hasil probe](evidence/chr-7.24.4-license-probe.json): identitas image,
isolasi, respons reboot, hasil sebelum/sesudah, dan batas interpretasi.
System ID serta isi kode dihapus. Log mentah dan kode lokal (0600) hanya di
scratch `chr-7244-check/q-_kr4ifpc/`, **bukan bukti tersanitasi dan tidak masuk Git**.
QEMU selesai melalui shutdown guest; pengecekan host tidak menemukan proses
QEMU tersisa. Digest sumber sebelum/sesudah tetap cocok.

Probe baca-saja awal lulus (exit 0). Percobaan apply pertama berhenti di
konfirmasi reboot (exit 1), belum ada hasil sesudah reboot; overlay itu tidak
dipakai ulang. Edit helper sempat menghasilkan SyntaxError sebelum QEMU
start, lalu diperbaiki. Probe apply lengkap berikutnya lulus (exit 0): satu
paste, reboot, login ulang, baca level, shutdown. Uji redaction sintetis
menemukan kebocoran fragmen saat console redraw (1 gagal), diperbaiki dan
uji ulang 1 OK. Pada salinan baru, prompt ganti password dilewati dengan
byte Ctrl-C via socket; **tidak ada password yang diubah**. Suite repo tidak
diulang sesi probe ini; engine, workflow, keypair, tag, dan aset tidak berubah.

**Belum dilakukan:** penetapan akar sebab (trust/signature, layout payload,
atau penyimpanan/penerapan kode), perbaikan engine, dan rebuild. Titik lanjut:
tentukan verifier serta format yang dipakai CHR versi ini dahulu; guard
cakupan dan perbaikan finder/CPIO tidak otomatis menjadi fix aktivasi.

### 8. Investigasi lanjut storage/verifier (2026-10-04) — selesai; bukti baru di §9

Commit acuan `1918ae7`. Pemilik meminta lisensi lab benar-benar dapat dipakai;
agent melanjutkan diagnosis, **bukan sekadar membuat kode baru**. Koreksi arahan
chat: install ulang image yang sama **belum punya dasar sebagai fix**, tetapi
hasil uji `free` juga tidak membuktikan secara pasti kunci tidak tertanam atau
instalasi VM pemilik bebas masalah. Penyebab tetap terbuka saat bagian ini
ditulis; kelanjutan dan bukti tersanitasi ada di §9.

Saat analisis storage, tiga hipotesis dipisahkan: (1) blok tidak tersimpan/
dipakai saat boot, (2) verifier tidak cocok dengan signature/layout payload,
(3) transformasi patch menyasar key yang bukan dipakai untuk lisensi CHR.
Review binari masih berjalan saat itu; hasilnya dan batas bukti baru ada di §9.

**Yang benar-benar dikerjakan sekarang:** analisis offline salinan disk hasil
probe §7; tidak menghubungi VM pemilik, tidak membuat kode/keypair baru,
tidak boot ulang guest, tidak mengubah engine/tag/aset, tidak rebuild.

- Konversi baca-saja overlay probe ke raw scratch; partisi GPT diperiksa,
  lalu `debugfs` membaca partisi ext tanpa opsi write. Digest raw sumber
  tetap cocok dengan fingerprint §7.
- Mencari tujuh representasi kode yang sudah dibuat: body base64, dua baris
  body, binary64, encoded payload16, signature48, decoded payload16.
  **Semua nol hit** pada disk pristine, boot-only control, dan hasil apply
  sesudah reboot (masing-masing 134.217.728 byte). Kontrol matcher positif/
  negatif lulus. Ini **tidak membuktikan kode tak tersimpan** dalam encoding
  lain, hidden storage, atau memori; tidak menetapkan lokasi verifier.
- Snapshot percobaan pertama yang berhenti di prompt reboot juga nol hit,
  tetapi guest belum sync/shutdown: bukti lemah, write tertunda bisa hilang.
- Inventaris filesystem ext boot-only vs sesudah apply/reboot: partisi boot
  6/6 entri identik; partisi sistem 12/16 entri identik. Empat path berubah:
  `/rw/rosmode.msg`, `/rw/startcount`, `/rw/store/cchst2`,
  `/rw/store/cfg.0000` (8482 → 8526 byte). Dua run punya System ID berbeda,
  jam/boot count berbeda; ini **bukan matched control**. Tambahan netto
  44 byte pada cfg **bukan bukti record lisensi** atau sebab aktivasi gagal.
- Gate `assert_activation.py` atas `result.json` nyata §7 mengembalikan
  **exit 1 / `activation_verified: false`** (`free` sebelum/sesudah).
  Exit 0 helper terdahulu hanya menandakan probe selesai, bukan sukses aktivasi.
- Semua file input/log/copy scratch dibuat/diatur 0600. Pemeriksaan host:
  0 proses QEMU tersisa. Suite repo tidak diulang; helper diagnosis saja.

Bukti disanitasi baru:
[JSON investigasi persistence](evidence/chr-7.24.4-license-persistence.json).
System ID dan isi kode tidak diekspor. Bukti §8 disertakan dalam paket
serah-terima engine `daf390f` (§12). Review verifier sudah kembali (lihat §9); jangan
mengubah signature checks, memperluas penggantian kernel, atau bypass guard
untuk memaksa hasil tampak hijau tanpa hubungan sebab yang teruji.

### 9. Verifier terkonfirmasi; kandidat fix ditolak review, boot lab belum berhasil (2026-10-04)

Saat sesi itu berjalan, commit acuan `1918ae7`; perubahan engine sesi ini
kemudian ter-commit `daf390f` (lihat §11). Bukti tahan lama tersanitasi:
[JSON verifier/build/probe/review](evidence/chr-7.24.4-license-verifier-lab.json).
Tidak ada kontak/penulisan VM pemilik, keypair baru, pemindahan tag atau
penggantian aset rilis lama.

**Verifier dan batas temuan:**

- Subagent menelusuri verifier statik `nova/bin/keyman` (`0x804f4c6`), dispatch
  command `0xfe000e` menuju handler `0x8051542`, dan emulasi byte ELF asli
  memakai fixture negatif. Agent utama memeriksa ulang disassembly serta
  membaca seluruh file `keyman`, `loader`, `mode` secara case-sensitive.
- Ketiga biner rilis identik dengan pembanding vendor. Kunci lisensi ter-pin
  vendor cocok **32/32 byte** setelah merekonstruksi delapan immediate dword
  `MOV`; bukan string 32 byte kontigu. Anchor custom tidak cocok di aset lama.
  Pencarian literal lama melewati bentuk tersebut. Ini menjelaskan penolakan
  kriptografis kode custom-signed pada **satu aset CHR x86 7.24.4 yang diaudit**;
  bukan kesimpulan untuk semua arsitektur/rilis atau “sejak dulu”.
- Prompt reboot tidak membuktikan acceptance; jalur persistensi mensyaratkan
  verifikasi sukses. Wording return-code pada F5 laporan subagent keliru;
  koreksi parent dicatat di JSON, tidak disalin sebagai fakta.
- Payload lengkap dan acceptance pascareboot dengan firmware baru tetap belum
  terbukti; emulasi fixture negatif bukan uji aktivasi positif. Provenance
  VMDK pemilik masih belum dikonfirmasi.

**Kandidat engine/build sebelum hasil review:**

- `patch.py` dan tes sintetis/integrasi ditambah untuk penggantian delapan
  immediate sebagai satu kunci utuh, dengan offset pristine/guard yang sama.
  Suite penuh sebelumnya menghasilkan **223 tes OK**; ini hasil sebelum
  perbaikan review lanjutan, bukan sertifikasi source yang sedang berubah.
- Build scratch dari NPK vendor pristine: mapping lisensi **3** replacements;
  mapping NPK-sign **5**; guard dan signature custom lulus. Ketiga anchor lab
  cocok custom. Input raw tetap dipin, tidak ada perubahan di luar partisi sistem.
- Ekstraksi non-root macOS menghasilkan owner 501:20 dan mode berbeda. Adapter
  scratch dinormalisasi terhadap **893 entri metadata** rilis; **582 file reguler**
  dibandingkan: 579 identik, hanya keyman/loader/mode berbeda masing-masing 32
  byte dengan ukuran tetap. Root/mode/mtime identik dengan acuan. Ini bukan
  perbaikan repo/boot yang terbukti; sumber hasil build pra-review disimpan
  versioned, tidak direkomendasikan dipakai pemilik.

**Runtime dan koreksi laporan chat:**

- Disk lab dinormalisasi (`6cd4fce4…`) tetap timeout sebelum serial login;
  **tidak ada kode dikirim**. VGA pada 20–140 detik tetap `Starting services...`.
  Guest cleanup dipaksa karena CLI tak tersedia; sumber digest tidak berubah.
- Kontrol memakai jalur debugfs tulis ulang yang sama tetapi **NPK identik byte
  dengan rilis**, raw `cd6c2165…`: **berhasil CLI**, versi `7.24.4`, level `free`,
  shutdown guest bersih. Klaim chat bahwa kontrol gagal sama persis adalah
  **salah dan ditarik kembali**. Kontrol ini tidak membuktikan metadata menjadi
  akar sebab, atau penggantian kunci bebas dari masalah boot.
- Marker `.asked` ada dan `nova`/`UPGRADED` tidak ada pada **lab maupun kontrol**
  setelah boot. `UPGRADEBOOTER` ada di snapshot lab pendek, tetapi tidak ada
  pada snapshot lab 420 detik. Marker ini tidak menetapkan jalur upgrade atau
  penyebab boot berulang; klaim chat tentang "upgrade loop" ditarik kembali.
- Long-watch 420 detik tuntas: lab disk **reboot berulang**, bukan hang diam
  (30–120s `Starting services...` → `Rebooting...` → `failed to stop parser:
  std failure: timeout (13)` → kernel baru → `Rebooting...` lagi; serial 0 byte,
  tanpa input). Forensik tiga log lab: **5 rekaman signal=11** pada
  `/nova/bin/sys2`, eip `0x0805bfd3`; kontrol jalur-tulis-sama dengan NPK rilis:
  backtrace kosong, CLI tercapai, shutdown guest bersih. Bukti tersanitasi:
  [JSON crash lab](evidence/chr-7.24.4-lab-sys2-crash.json).
- Disassembly situs eip: penulisan nol ke alamat NULL lalu `ud2` — **situs fault
  disengaja** yang dapat dicapai dari **dua cabang konsistensi** (`0x805aece`,
  `0x805bfd1`). EIP tersimpan saja tidak menunjukkan cabang mana yang aktif;
  situs disengaja juga tidak menutup kemungkinan korupsi memori di hulu.
  Sumber nilai: storage satu-byte ber-guard `0x8053144` (pointer diteruskan
  ke konstruktor `nv::Looper`) dan buffer statis `0x805840f` (diinisialisasi
  dari byte rendah jumlah detik+mikrodetik `gettimeofday`). Dataflow setelah
  konstruktor dan hubungan dengan image termodifikasi **belum dibuktikan**.
- Yang sah saat ini: abort teramati pada run image termodifikasi, tidak pada
  kontrol tulis-ulang NPK identik. NPK lab juga berbeda dalam **packing
  SquashFS dan signature**, bukan hanya 3×32 byte program; penggantian anchor
  belum diisolasi sebagai penyebab. Klaim chat "anti-tamper" dan "hampir pasti
  memvalidasi anchor" terlalu jauh dan ditarik kembali. `sys2` sendiri
  byte-identik dengan rilis. Watch tambahan 24 menit dibatalkan sebagai
  redundan (bukan uji selesai); setelah cleanup, 0 proses QEMU/probe miliknya.
  QMP quit/terminasi host **bukan shutdown guest bersih**.

**Review engine `deleg_82ebe314`: `passed=false` (0 security concerns, 3 logic errors).**

1. P1: scan C7 mentah tanpa boundary instruksi; prefix operand-size mengubah
   semantik dan dapat menyebabkan byte instruksi lain ditulis/dihitung.
2. P2: rentang executable section bisa alias metadata ELF; ukuran/version
   header juga belum ketat. Kecocokan di metadata tidak boleh dianggap cakupan.
3. P2: impor fixture tes gagal pada pemanggilan module integrasi, meskipun
   discovery lulus. Saran tambahan: assert seluruh baris coverage, bukan total saja.

Reviewer melaporkan 50 tes patch discovery lulus tetapi defect tetap ada;
hijau bukan bukti matcher aman. Ia juga melaporkan sempat stash/restore file
tes, melanggar mandat baca-saja. Parent memeriksa ulang status tree tetapi tidak
punya byte snapshot sebelum review untuk menjamin seluruh restoration. Worker
berikutnya dilarang stash/reset/checkout; baseline harus di copy scratch.
Fix-agent terpisah ditugaskan TDD atas defect ini, tanpa build/VM/push; hasil fix
dan verifikasi parent dicatat di §10. Target aktivasi tetap terbuka.

### 10. Review ulang pass; approval ditahan oleh regresi overlap baru (2026-10-04)

Perubahan bagian ini awalnya lokal; engine-nya kemudian ter-commit `daf390f`
(§11) dengan dokumentasi terkait.

- Fix-agent `deleg_7012a246` menyelesaikan TDD vertikal atas ketiga defect §9 plus
  saran baris hardlink, tanpa commit/push/build/inspeksi kunci/akses VM, dan tanpa
  menyentuh dokumentasi milik parent. Lima file berubah: `patch.py` (matcher
  immediate berbasis decoding Capstone i386 dari batas section executable,
  fail-closed tanpa decoder, tanpa scan mentah C7), `tests/test_patch_x86_immediates.py`
  (baru, fixture sintetis), `tests/test_patch_coverage_integration.py` (impor
  fixture dua mode invocation + assert baris replacement lengkap),
  `requirements.txt` (`capstone>=5,<6`; 5.0.9 terpasang di venv), dan
  `.github/workflows/patch6.yml` (tambah langkah instal requirements).
- **Verifikasi independen parent** (fingerprint lima file identik dengan fingerprint
  akhir fix-agent; sumber dicek tidak berubah selama eksekusi): suite penuh
  **228 tes OK, 0 gagal/0 error/0 skip**; patch discovery mode `-O` **55 tes OK**;
  integrasi **6+6 OK** pada mode module **dan** discovery; probe sintetis parent
  **18/18 lulus** (prefix operand/address/segment/lock/mov/push ditolak tanpa
  mutasi; alias section-table/program-table ditolak; field header malformed
  ditolak; decoder absen fail-closed; penggantian asli tetap bekerja
  pada empat basis disp32/disp8 dan layout program-header sebelum kode);
  `pip check` OK; `git diff --check` bersih; actionlint 1.7.12 bersih pada
  workflow saat ini **dan** baseline `HEAD` (salinan scratch terisolasi,
  tanpa stash/reset tree).
- Scan statis baris tambahan payload review: 0 temuan (secrets/injection/eval/
  pickle/SQL/material hex-64).
- Bukti tersanitasi tahan lama:
  [JSON verifikasi engine](evidence/chr-7.24.4-engine-review-fix.json) — memuat
  rekam fix-agent, verifikasi parent, sumber probe, digest payload review, scan
  statis, dan batas interpretasi. Artefak aslinya (`evidence.json`,
  `parent-verification.json`, probe, payload diff) tetap di scratch
  `~/.hermes/cache/scratch/split-immediate-review/` untuk reproduksi.
- **Review independen ulang `deleg_71bfd535`: `passed=true` (0 security, 0 logic,
  4 saran; ketiga defect_checks true) — tetapi approval parent DITAHAN.** Verdict
  dicatat sebagaimana dikembalikan, bukan approval akhir. Transkrip mencatat
  pemanggilan suite penuh dan mode module, serta probe overlapping-section yang
  ia anggap aman. Parent mereproduksi probe itu dan menemukan **defect sisa
  kelas P1** (rincian di bawah); verdict pass tidak mengesampingkan defect
  perilaku yang direproduksi.
- **Defect sisa yang direproduksi parent (blocking):** `_x86_immediate_matches`
  men-decode dari awal tiap section executable tanpa memvalidasi rentang section
  yang tumpang-tindih. Dua rentang exec tumpang-tindih dapat menafsir ulang byte
  yang sama dari boundary yang tidak kompatibel: outer section berawal prefix
  `0x66` sebelum delapan MOV (ditolak benar bila sendirian), inner section
  berawal satu byte kemudian — kehadiran inner menyebabkan delapan immediate
  dword ditulis ulang dan dihitung satu kunci utuh. Disassembly stream outer
  benar-benar berubah semantik (`mov word …, 0x100` → `0x2120`; `add al,[ebx]`
  → `and ah,[ebx]`). Direproduksi juga untuk prefix `B8` dan undecodable `0F 04`,
  pada kedua urutan section: **6/6 kasus penolakan gagal, exit 1**; dua kontrol
  positif single-section dan duplicate-range lulus. Observasi, source probe,
  dan digest disalin ke `post_verdict_parent_probe` pada JSON verifikasi engine
  di repo; sumber scratch `split-immediate-review/verify_overlap_parent.py`/`.json`
  bukan satu-satunya bukti. Ini defect fixture sintetis, **bukan penyebab boot
  sys2 yang sudah dibuktikan**.
- **Fix round 2 `deleg_e7b57afb` saat itu didispatch** untuk perbaikan ini (patch.py +
  tes overlap saja, TDD RED→GREEN, dilarang stash/reset/commit/push/build/VM).
  Kontrak: rentang exec tumpang-tindih non-identik fail-closed untuk pencocokan
  instruksi; duplicate range identik boleh didedupe sekali; section disjoint
  normal tetap boleh match. Saran reviewer tentang e_shoff==0/e_shnum==0 ikut
  ditambahkan sebagai fixture penolakan. Hasil round 2 dan verifikasi parent
  terbaru dicatat di §11; bagian §10 mempertahankan riwayat defect/source lama.
- **Adjudikasi saran reviewer** (dicatat di
  [JSON verifikasi engine](evidence/chr-7.24.4-engine-review-fix.json)):
  perubahan `sudo pip` **ditunda**. Workflow mencampur setup-python dengan
  `sudo -E python3`; interpreter install dan eksekusi harus diverifikasi
  bersama pada runner Ubuntu. Klaim chat bahwa `sudo pip` pasti interpreter
  yang benar **ditarik kembali**: resolusi PATH/sudo dan PEP 668 belum diuji
  pada runner sebenarnya. Saran skip-note dan impor module-level ditunda;
  memindahkan impor Capstone dapat mengubah perilaku saat decoder absen.
  Saran tes overlap dieskalasi menjadi defect blocking di atas. Reviewer
  melaporkan 228 tes OK dengan 2 skip; transkrip memuat pemanggilan suite penuh
  tetapi output dipotong. Jangan menyebut run itu tidak ada. Hasil parent
  tetap 228 OK 0 skip pada konfigurasi parent, bukan bukti jumlah skip reviewer.
- Batas tetap: disk lab lama (`6cd4fce4…`) masih tercatat reboot-loop sys2 (§9);
  belum ada build ulang memakai engine baru; diagnosis dataflow check sys2 belum
  dikerjakan.

### 11. Round 2 overlap diperbaiki; review delta diterima untuk scope sintetis (2026-10-04)

Engine dan tesnya ter-commit `daf390f` pada `main` setelah gate pra-push
lulus; **belum ada build firmware ulang, tidak ada akses VM pemilik**. Bukti tersanitasi tahan lama:
[JSON perbaikan overlap round 2](evidence/chr-7.24.4-engine-overlap-fix.json).

- Fix-agent `deleg_e7b57afb` hanya mengubah `patch.py` dan
  `tests/test_patch_x86_immediates.py`. Patcher mengumpulkan rentang kandidat
  executable yang valid/nonkosong, dedupe pasangan start/end identik, urutkan,
  lalu sweep `furthest_end` **sebelum decoding apa pun**. Overlap non-identik
  membatalkan seluruh pencocokan instruksi; section disjoint/adjacent tetap
  boleh match, duplikat identik dihitung sekali. Jalur literal tidak berubah.
- Rekam eksekusi fix-agent memuat RED asli pada source pra-fix: 1 tes dengan
  **2 subtest gagal**, returncode 1; minimal GREEN 1 OK. Matriks lanjutan
  mencakup prefix 66/B8/0F04 dua urutan, partial/containment/same-start,
  duplicate, disjoint/adjacent, empty-range, enam permutasi tiga rentang,
  ambiguity setelah lokasi valid, serta e_shoff==0/e_shnum==0. Ini bukan
  bukti hubungan kausal dengan crash `sys2` pada disk lab lama.
- **Verifikasi independen parent pada source akhir yang stabil:** suite penuh
  **235 tes OK, 0 gagal/error/skip** (Caddy diaktifkan); patch discovery mode
  `-O` **62 OK**; module x86 **20 OK**; integrasi module/discovery **6+6 OK**;
  `pip check` dan `git diff --check` returncode 0. Fingerprint source cocok
  dengan akhir fix-agent dan tidak berubah selama eksekusi.
- Parent menjalankan probe overlap yang sama dengan source probe tak berubah:
  **6/6 kasus yang dahulu RED sekarang GREEN**, byte tetap identik, stats/log
  kosong; disassembly outer tidak berubah lagi. Dua kontrol positif genuine
  dan exact-duplicate juga lulus. RED dan GREEN disimpan terpisah di bukti
  repo; bukan hanya klaim subagent atau hitungan suite.
- **Pelanggaran batas artefak fix-agent diungkap:** ia menjalankan skrip probe
  parent sebelum edit, sehingga JSON pasangannya di scratch tertimpa. Identitas
  byte JSON pra-insiden tidak bisa dijamin (hash awal tidak diambil). Parent
  memeriksa observasi RED asli yang sudah tersimpan di bukti repo: enam kasus
  gagal dan kedua kontrol positif tetap utuh. Setelah uji GREEN, parent
  merekonstruksi JSON scratch dari observasi RED tahan lama; ini **bukan klaim
  pemulihan byte-identik file scratch asli**. Jangan jalankan probe pekerja
  lain yang mempunyai writer top-level; gunakan salinan/output sendiri.
- Versi dependency dilaporkan terpisah: metadata distribusi Capstone **5.0.9**,
  module runtime `__version__` **5.0.7**. Perbedaan sudah ada sebelum round 2;
  dependency tidak diubah dan `pip check` lulus. Jangan menyamakan metadata
  distribusi dengan versi module/native yang benar-benar diimpor.
- **Review delta independen `deleg_4aa912a1` lulus dan diterima parent**
  (`passed=true`, 0 security concerns, 0 logic errors), hanya untuk perubahan
  matcher round 2 dan tes sintetis pada fingerprint tercatat. SHA-256 source
  dua file/payload masih cocok; tidak ada edit source setelah review. Parent
  memeriksa hash **13 rekaman eksekusi**, stdout/stderr lengkap beserta file
  stream pasangannya, dan **56 berkas inventori reviewer**: semuanya cocok.
  Scan statis delta 135 baris tambahan tetap 0 temuan; ini bukan audit keamanan
  seluruh repo atau approval firmware untuk dipasang.
- **Bukti reviewer dikonfirmasi parent, bukan hanya verdict:** reverse+replay
  payload oleh parent menghasilkan baseline pra-fix dengan hash yang sama
  dan mengembalikan source akhir persis. Audit reviewer membatasi perubahan
  produksi pada `_x86_immediate_matches`; `_replace_keys` dan seluruh byte
  sesudahnya identik dengan baseline round 1. Parent membaca lengkap probe
  mandiri reviewer lalu menjalankannya: **13 tes OK, 0 gagal/error/skip**,
  mencakup oracle interval **576 kasus**, spy decoder (0 decoding/konstruksi
  untuk overlap ambigu, tepat 1 decode untuk duplikat identik), kontrol positif,
  dan pemanggilan x86 module/discovery. Source tetap cocok dengan pin.
- Reviewer menjalankan module x86+integrasi **26 OK** dan patch discovery `-O`
  **62 OK**, 0 gagal/error/skip; output lengkapnya tersimpan di bukti repo.
  **Suite penuh tidak diulang pada adjudikasi ini**; angka 235 OK di atas
  adalah run parent sebelumnya pada source yang sama, bukan run baru.
- Kegagalan harness tidak disembunyikan: **3 run eksplorasi reviewer rc=1**
  (dua asumsi panjang fixture salah, satu trap decoder) serta **1 run unittest
  awal: 9 tes, 1 error, rc=1** akibat trap `__path__` pada kontrol valid belum
  tertangkap. Iterasi terkoreksi 9/10/13 OK; parent membaca traceback dan
  memverifikasi ulang final 13 OK. Bukan empat kegagalan produk yang diabaikan.
- Dua saran non-blocking ditunda tanpa mengubah source ter-review: promosi
  decoder-spy menjadi regresi tetap di repo (kini probe/sumbernya ditahan di
  bukti durabel), dan penamaan `entry_size` untuk keterbacaan (sudah divalidasi
  ==40). Tinjau ketika matcher/tes berikutnya diubah; perubahan source baru
  membutuhkan tes dan review sesuai versi baru.
- Dua deviasi reviewer dicatat: penanda `.delta-review-r2-latest-path` ditulis
  di root scratch tanpa memeriksa keberadaan/hash awal, sehingga preservasi
  file yang mungkin sudah ada **tidak dijamin**; dua log eksplorasi awal
  tertimpa di `probe.out` milik reviewer sebelum perekam terstruktur dibuat.
  Batas baca-saja tidak dianggap sempurna hanya karena verdict lulus.
  Verdict lengkap (path disanitasi), manifest, rekaman eksekusi, kegagalan,
  source probe final, dan rerun parent kini disimpan di JSON bukti repo;
  ringkasan penting tidak lagi bergantung pada scratch yang dapat dipangkas.
- Batas tetap: disk lab terakhir pra-review mengalami reboot-loop (§9), belum
  ada firmware baru yang di-boot, dan **aktivasi setelah reboot belum terbukti**.
  Unit/integrasi hijau hanya membuktikan perilaku transformasi sintetis.

### 12. Serah-terima source yang disetujui pemilik (2026-10-04)

Pemilik memberikan izin **"ok push"** untuk source, tes dan bukti sesi ini ke
`main`. Commit engine yang sudah dibuat: `daf390f14263448a9e8e38667cd2d02b9665a5ae`.
Commit dokumentasi yang memuat bagian ini dicatat oleh riwayat Git, bukan
hash yang ditebak terlebih dahulu. Saat catatan ini disiapkan push belum
selesai; ketersediaan publik harus diperiksa lewat SHA branch remote dan
kesamaan byte seluruh file perubahan setelah push.

- Verifikasi pra-push **dijalankan ulang tanpa pipeline yang menyembunyikan
  returncode**, dengan stdout/stderr lengkap disimpan: suite penuh **235 OK,
  0 gagal/error/skip** (77.099 detik, Caddy aktif); patch discovery `-O`
  **62 OK**, 0 gagal/error/skip. Fingerprint lima file source ter-review
  tidak berubah sebelum/sesudah run. `pip check`, actionlint `patch6.yml`,
  dan `git diff --check` seluruhnya exit 0. Remote `main` diperbarui dengan
  fetch dan sama dengan `1918ae7` sebelum commit engine (0 ahead/0 behind).
- Scan konten baru tidak menemukan material kunci/token/password baru.
  **Bukan klaim repo bebas secret:** `patch6.yml` sudah mengandung empat
  konfigurasi kunci hardcoded dari HEAD sebelumnya, termasuk satu privat
  legacy; semuanya identik, tidak ditambahkan/diubah pada delta ini.
  Nilainya tidak ditampilkan atau disalin ke bukti. Kunci legacy bukan
  untuk produksi; jangan menyamakan pengabaian temuan historis dengan audit
  keamanan seluruh repo yang lulus.
- Paket source ini tidak membangun firmware, menggeser tag, mengganti aset
  rilis, menjalankan workflow build manual, mengubah keypair, atau menyentuh
  VM pemilik. Tidak ada bukti runtime baru: **boot/login build kandidat dan
  aktivasi lisensi setelah reboot tetap belum terbukti**. Persetujuan matcher
  terbatas pada versi source dan fixture sintetis yang dijelaskan di §11.

## Yang bisa / perlu dikerjakan selanjutnya

1. **Lanjutkan investigasi laporan boot VMware** (lihat §5): identifikasi ISO dan
   konfigurasi dulu, lalu bandingkan dengan ISO vendor versi/arsitektur yang sama
   pada VM terpisah dengan konfigurasi setara. Simpan bukti dan batas kesimpulan.
2. **Lanjutkan diagnosis boot/runtime di lab terisolasi sesuai izin** — fix
   overlap round 2 lulus review dan diterima untuk scope sintetis (§11), bukan
   bukti image aman dipakai. Sebelum build/probe berikutnya, pin source dan
   input, gunakan kontrol yang benar, lalu telusuri dataflow check `sys2`;
   marker upgrade saja bukan akar sebab dan check tidak boleh dimatikan untuk
   sekadar mencapai login. Tidak ada build/akses VM baru pada adjudikasi ini.
   Pisahkan bukti
   boot/signature dari aktivasi dengan ID sama setelah reboot. Panel custom-lab
   dan tes `tests/test_license_*.py` tidak membuktikan penerimaan firmware.
   Lengkapi provenance VMDK pemilik sebelum mengatribusikan hasil ke VM itu;
   jangan mengganti keypair atau menerbitkan ulang aset untuk menutupi uji.
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

- `unsquashfs` dan `mksquashfs` harus ada di `PATH`; enam tes integrasi di-skip
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
