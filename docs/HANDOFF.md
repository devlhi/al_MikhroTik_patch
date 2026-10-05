# HANDOFF — Ali Patch Code

Dokumen serah terima untuk developer lain yang mau melanjutkan kerja repo ini.
**Status diperbarui: 2026-10-05: source sudah dipush sebagai `140b94a`. Build all run37277711016 selesai: x86 sukses; arm, arm64, mipsbe, mmips, smips, ppc gagal guard LICENSE mapping1; release gabungan di-skip (§18). VMDK final lokal sudah dibangun lewat jalur produksi dan diuji langsung: boot/login, `free` menjadi `p-unlimited`, dua reboot serta shutdown/cold restart, semuanya dengan System ID sama (§17). Signature custom, coverage aktual 2 LICENSE/5 signing, metadata SquashFS dan integritas ZIP/VMDK lulus. Suite Linux final: 333 tes, 326 lulus, 7 skip, 0 gagal/error. File final ada di `dist/chr-x86-7.24.4-runtime-fix`; belum ada firmware baru diterbitkan di GitHub. Bukti runtime hanya QEMU tanpa jaringan, bukan VMware/upgrade/throughput. Jangan install ulang kandidat CI lama sebagai solusi lisensi.**
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
| Aktivasi lisensi / upgrade | **VM pemilik tetap free (§6). Aset rilis: `free` → paste → reboot → `free` (§7); anchor vendor yang terlewat pola literal kini terkonfirmasi untuk satu aset (§9). Approval versi source lama ditahan oleh defect overlap (§10); round 2 kini lulus review delta dan diterima parent pada fingerprint tercatat untuk scope sintetis (§11). Diagnostik (§16) dan VMDK final produksi lokal (§17) berhasil aktivasi `p-unlimited`. Final lolos dua reboot dan cold restart dengan ID sama; belum diuji di VMware milik pemilik.** |

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

### 13. Fokus GitHub dan launcher Windows — status parsial (2026-10-04)

Pemilik membatalkan rencana build/QEMU lokal dan meminta fokus GitHub serta
file `.bat` untuk generator lisensi lab. Build manual `patch7.yml` didispatch
pada `c636fa654f23b807b2adb51e24106396783cb246` dengan
`create_draft_release=true`; run `37207497763` selesai **failure** secara
keseluruhan.[8] Tidak ada akses VM pemilik atau build/probe QEMU baru.

- **x86 sukses**, dengan artifact `11305142056`, nama
  `ali-patch-code-x86-7.24.4`, ukuran arsip **1.017.399.188 byte**. Log staging
  menyebut 18 aset. Metadata ZIP diambil lewat HTTPS byte ranges: **21 entri
  unik = 18 aset + 3 metadata**, daftar aset cocok persis dengan
  `release_assets.expected_sources`, ukuran ZIP cocok dengan manifest, dan
  seluruh 18 digest pada `SHA256SUMS` cocok dengan manifest. Pemeriksaan ini
  **belum hash ulang isi biner**; unduhan utuh sebelumnya timeout dengan 0 byte
  tersimpan. Percobaan unduhan range dihentikan setelah lebih dari 10 menit
  tanpa kemajuan terlapor; file sparse lokal bukan bukti unduhan lengkap.
  Verifikasi hash isi biner masih terblokir. `boot_tested` tetap `false`.
- **arm, arm64, mipsbe, mmips, smips, ppc gagal**. Ketujuh log job diperiksa;
  seluruh enam kegagalan memuat `no replacement for required mapping(s) 1 in
  system package; signing blocked`. Mapping 1 ialah kunci lisensi pada CLI
  `patch.py`. ARM64 gagal saat patch NPK di ISO; lima lainnya saat patch NPK
  mandiri. Ini bukti pola tidak ditemukan oleh transformer saat ini, **bukan
  bukti lokasi atau representasi kunci non-x86 sudah didiagnosis**. Guard
  tidak diubah/dilewati dan tidak ada artifact non-x86 dari run ini.
- Job `release` **skipped**, sehingga permintaan draft tidak menghasilkan
  draft rilis gabungan. Tag/aset rilis lama tidak diganti. Artifact Actions
  tercatat kedaluwarsa **2026-10-18T14:04:00Z**; bukan rilis permanen.
- Bukti tersanitasi: [rekaman CI dan manifest](evidence/ci-7.24.4-run37207497763.json).
  Record membedakan digest yang dilaporkan GitHub/manifest, metadata yang
  diverifikasi, serta hash biner yang belum selesai. Error helper awal
  (`total_count`, HTTP 415/403, timeout) tidak dihapus dari catatan.
- Launcher `generate-license.bat`, companion `scripts/license_cli.py`, serta
  dua modul tes sudah dibuat. `license_util.py` adalah modul, **bukan CLI**;
  draft tes parent yang mengasumsikan sebaliknya ditolak/diganti. Batch hanya
  membuka menu, tidak meneruskan argumen atau input ID melalui shell. CLI
  menyediakan flags terpisah, memeriksa signature/jenis/ID dan kecocokan kunci
  terhadap workflow sebelum menyimpan, menolak overwrite, dan tidak mencetak
  private key atau license body. Panduan: [Windows](windows-license.md).
- **Tes parent aktual:** focused **49 total, 45 lulus, 4 skip** (33.591 detik);
  full suite **269 total, 265 lulus, 4 skip** (102.585 detik), returncode 0.
  Empat skip semuanya cmd.exe native pada macOS; bukan tes Windows sukses.
  SquashFS/Node tersedia, Caddy diaktifkan. Pipeline parent mempertahankan
  exit code perintah tes melalui `PIPESTATUS`, tetapi hanya ringkasan terminal disimpan; jangan menyebut
  run parent itu mempunyai capture lengkap. `pip check`, `git diff --check`,
  actionlint 1.7.12 workflow Windows, aturan ignore hasil, dan atribut batch
  semuanya lulus. `.gitattributes` mempertahankan byte CRLF batch di checkout.
- **Bukti tahan lama:** [verifikasi Windows/CLI](evidence/windows-license-verification.json)
  memuat 51 rekaman implementer RED/GREEN/failure, fingerprint source,
  batas tes, dan rerun parent terpisah. Implementer melaporkan dua percobaan
  in-process sempat membaca workflow aktual karena root helper tidak ikut
  diisolasi; tidak mencetak/mengubah nilai kunci. Tes akhir mengisolasi root
  CLI **dan** helper server. Kegagalan harness/refactor awal dipertahankan.
- **Review independen `deleg_6132069f`: TIDAK lulus (bukan `{}`):** reviewer
  menemukan defect kontrak nyata — `scripts/license_cli.py` baris 95–98
  melakukan `Path(...).resolve()` pada jalur output sebelum `open('x')`,
  sehingga **symlink dangling yang sudah ada diikuti**: lisensi malah dibuat
  di target baru dan exit 0, padahal kontrak menolak nama output yang sudah
  ada. Parent mereproduksi sendiri lewat probe sintetis terisolasi:
  `dangling-link` → rc 0, target tercipta, link tetap ada (**kontrak gagal**);
  kontrol `fresh` (rc 0 + ID cocok), `existing-regular` (rc≠0, isi dijaga),
  dan symlink ke target yang sudah ada (rc≠0, isi target dijaga) semuanya
  benar. Verdict lengkap + bukti reviewer:
  `scratch/windows-license-independent-review-7tawltxz/`; rekaman parent
  `parent-symlink-red.json` (probe dir sementara). Catatan: hasil review yang
  sampai ke parent tampil sebagai objek kosong `{}`; verdict asli diambil
  dari `verdict.json` reviewer — kegagalan transport ringkasan bukan approval.
- **Fix `deleg_e4d96de0` selesai:** satu baris produksi `resolve()` → `absolute()`,
  sehingga komponen symlink output tidak diikuti sebelum exclusive `open('x')`;
  dua tes regresi melindungi link dangling dan link ke target existing.
  Fix-agent membuktikan RED (dua subtest gagal pada source awal; kontrol
  fresh sign+parse lulus), kemudian **27 tes CLI lulus, 0 skip**.
  Parent mengulang probe miliknya: **4/4 kontrak lulus**, link tetap utuh,
  target dangling tidak tercipta, fresh output tetap sign+parse.
  Suite penuh parent sesudah fix: **271 total, 267 lulus, 4 cmd.exe skip**,
  returncode 0 (99.972 detik); hanya ringkasan terminal retained untuk run ini.
  Fingerprint lima file source diperiksa; hanya CLI dan tes CLI berubah dari
  payload review awal. Bukti reviewer, RED/GREEN fix-agent, dan reproduksi
  parent: [review Windows](evidence/windows-license-review.json).
  **Review delta `deleg_0689555e` lulus dan diterima parent:** 0 security
  concerns, 0 logic errors; tiga tes yang diizinkan benar-benar lulus (0 skip,
  2.200 detik). Parent memeriksa lima pin source, payload delta, digest log
  tes dan seluruh cek pin reviewer; semuanya cocok. Bukti lengkap reviewer
  telah disalin tersanitasi ke JSON review di atas. Approval hanya untuk
  source/fix launcher, **bukan firmware**. Suite parent diulang setelah
  penerimaan: **271 total, 267 lulus, 4 cmd.exe skip**, returncode 0
  (116.808 detik; ringkasan terminal, bukan capture penuh). Strict sources,
  actionlint dan `git diff --check` kembali lulus. Push belum dilakukan
  saat catatan pra-commit ini ditulis.
  Scan baris tambahan: tidak ada token/material kunci baru. Scan awal seluruh
  README menemukan dua contoh blok lisensi legacy; perbandingan dengan HEAD
  memastikan keduanya tidak berubah/tidak ditambahkan pada delta. Pemeriksaan
  diagnostik sempat menampilkan contoh legacy beserta argumen kunci di output
  tool; nilainya tidak disalin ke bukti baru. Ini bukan klaim repo bebas secret.
  Workflow kunci dan konfigurasi deployment tetap byte-identik dengan HEAD.
- Workflow Windows native Python **3.10 dan 3.14** sudah lulus actionlint,
  tetapi belum dipush/dijalankan. Validasi terakhir juga lulus strict sources,
  parse tiga JSON bukti, dan `git diff --check`; fetch remote tetap 0 ahead/
  0 behind pada `c636fa6`.
  Pemilik menyetujui commit/push launcher, tes, workflow Windows, dan dokumentasi
  ke `main` melalui konfirmasi UI; izin itu tidak mencakup penggantian aset/tag
  rilis lama.
- **Publikasi `f392288`:** commit `[verified] feat: add Windows custom-lab
  license launcher` (13 file, 2353 insertions) dipush ke `main`; GET anonim
  mengonfirmasi SHA remote dan **13/13 file publik byte-identical** dengan
  lokal. Workflow Windows terpicu otomatis oleh push. `git diff --cached
  --check` sempat menolak CRLF batch sebagai whitespace; validasi dengan
  `git -c core.whitespace=cr-at-eol diff --cached --check` lulus tanpa
  mengubah byte batch atau melewati pemeriksaan lain.
- **Run Windows asli `37214834349` (Python 3.10.11 & 3.14.7,
  windows-latest):** total 51 tes/job. **Keempat tes cmd.exe native `.bat`
  lulus di kedua Python** — menu CHR pilih-1 sampai file terverifikasi
  signature+ID, menu ROS, ID invalid exit≠0 tanpa file, dan cabang
  Python-hilang menampilkan python.org; path uji memuat spasi, `&`, `!`.
  **Tiga kegagalan/job, semua symlink output**, kelas baru yang tidak
  muncul di macOS:[9]
  1. **Bug produk di Windows terkonfirmasi:** `open('x')` pada Python
     Windows menembus symlink dangling final — akar sebab: CRT memetakan
     `_O_CREAT|_O_EXCL` ke `CreateFileW(CREATE_NEW)` tanpa
     `FILE_FLAG_OPEN_REPARSE_POINT`, dan dokumentasi Microsoft menyatakan
     pembuatan file baru tidak mengubah perilaku reparse. CLI exit 0
     terkonfirmasi; asersi target belum tercapai karena defect tes kedua,
     sehingga target-tercipta masih inferensi dari alur sukses, bukan
     observasi independen dalam log asli. Tidak ada klaim native GREEN.
  2. **Bug tes:** `readlink()` Windows mengembalikan prefix `//?/` sehingga
     `assertEqual(readlink(), target)` gagal dan menutupi asersi target.
  Kandidat lokal precheck `output.is_symlink()` **ditolak** review
  `deleg_58b8d498`: penulis lain dapat memasang symlink sesudah check dan
  sebelum `open('x')`. Ini analisis statis, bukan reproduksi native Windows
  baru. Lima tes macOS lulus tanpa skip; parent memverifikasi pin before/after
  dan digest log reviewer. Penolakan dan log tersanitasi dipertahankan di
  [evidence review](evidence/windows-license-review.json).
- **Kandidat pengganti atomik, belum dipush:** CLI menulis lengkap dan menutup
  staging file di `TemporaryDirectory` pada folder tujuan, kemudian `os.link`
  membuat nama output tanpa overwrite. Path final tidak dibuka untuk write;
  tidak ada fallback jika filesystem tidak mendukung hard link. Folder lab
  tepercaya wajib; bukan sandbox terhadap penggantian ancestor/staging oleh
  pihak yang menguasai akun/folder. Panduan Windows menyebut NTFS dan penanganan
  error cleanup (output mungkin sudah terbit lengkap meski exit nonzero).
  Snapshot `readlink()` tetap dibandingkan sebelum/sesudah, bukan ejaan path.
  Tes race akhir menyisipkan symlink tepat sebelum pemanggilan `os.link` nyata
  lalu memeriksa exit nonzero, link utuh, target tidak dibuat, staging bersih.
  Kontrol fresh dan partial-write juga memeriksa cleanup.
- **Bukti TDD/iterasi:** RED awal pada macOS memakai model perilaku Windows
  `CREATE_NEW`, bukan reproduksi Windows native. Dua subtest race gagal
  (exit 0 dan target tercipta), kontrol fresh lulus. Kandidat staging awal
  `NamedTemporaryFile` menyebabkan satu tes partial-write tidak lagi
  menginjeksi API yang dipakai (28 tes, satu gagal). Diganti direktori staging
  + `Path.open`, seam injeksi diperbarui; 28/28 lulus. Tes final disederhanakan
  memakai race hard-link nyata saja. Kegagalan harness dan log RED/GREEN
  dipertahankan, bukan dihapus.
- **Verifikasi parent final:** modul CLI **28 lulus, 0 skip** (34.595 detik),
  suite penuh **272 total, 268 lulus, 4 cmd.exe skip** (103.596 detik), rc 0.
  Kedua run final ini hanya mempunyai ringkasan terminal, bukan capture lengkap.
  SquashFS tersedia; `git diff --check` dan AST dua file lulus. Diff dua-file
  dari `f392288` dipin SHA-256
  `2649d754e61acf6b6fb1c970af96266394f8717fc807bf9b294e08b20278d399`;
  scan baris tambahan tidak menemukan literal secret/injection.
  **Review delta `deleg_c6179945` lulus dan diterima parent:** tujuh tes terarah
  lulus di macOS (0 skip, rc 0, 16.453 detik). Pin dua file, diff, payload,
  before/after reviewer, serta digest stdout/stderr cocok. Verdict: tidak ada
  security concern atau logic error. Parser laporan reviewer sempat gagal
  mengenali docstring tes dua baris; rc unittest tetap 0, output yang sama
  diparse ulang dan kegagalan wrapper dipertahankan. Probe tambahan reviewer
  hanya ditulis, **tidak dijalankan**, sehingga tidak diklaim sebagai hasil.
  Saran nonblocking: tambah regresi permanen link unsupported, close/flush
  gagal sebelum publikasi, dan cleanup setelah publikasi. Semantik cleanup
  sudah dijelaskan di panduan; bukan rollback output lengkap. Tidak ada kode
  berubah setelah review. Bukti lengkap tersanitasi disimpan di evidence.
  Parent mengulang suite setelah penerimaan review: **272 total, 268 lulus,
  4 cmd.exe skip**, rc 0 (100.472 detik); capture lengkap berada di scratch,
  ringkasan dan digest output dipertahankan di evidence. Strict sources dan
  actionlint kembali lulus. Pemilik menegaskan izin `push`. **Push fix dan
  Windows native belum dilakukan pada titik pra-commit ini.**
- **Publikasi fix terverifikasi:** commit `9b4d6f9054810bf5fc67226feccfecd5590baa64`
  (`[verified] fix: publish Windows lab licenses without following symlinks`)
  dipush ke `main`. GET anonim mengonfirmasi SHA remote dan **5/5 file berubah
  byte-identical**. Tidak ada perubahan tag, aset rilis, keypair, atau firmware.
- **Windows native akhirnya GREEN:** run `37219037250` pada `9b4d6f9` sukses.
  Python **3.10.11: 52/52 tes lulus, 0 skip, 94.659 detik**; Python
  **3.14.7: 52/52 lulus, 0 skip, 90.678 detik**. Log diperiksa dan record tes
  dihitung unik per job; semua tujuh target penting (empat cmd.exe asli,
  existing/dangling symlink, race insertion) lulus, bukan skip.[10]
  Bukti publikasi, 104 hasil tes dua job, serta kedua log tersanitasi dengan
  SHA-256 dipertahankan di
  [bukti native GREEN](evidence/windows-license-native-37219037250.json).
  Validasi collector awal berhenti sebelum menulis akibat normalisasi CRLF
  dan format unittest Python 3.10 yang hanya menaruh nama kelas di kurung;
  validasi diperbaiki memakai raw bytes serta identitas kelas+nama tes.
  Ini koreksi parser bukti, bukan pengulangan atau perubahan hasil CI.
  Pengambilan log memakai credential in-memory hanya ke api.github.com;
  redirect storage memakai request baru tanpa Authorization. Log/key/token
  mentah tidak disimpan. Ini bukti launcher/generator di Windows, bukan
  penerimaan lisensi firmware. Sesudah run tersebut hanya HANDOFF/evidence/
  panduan diubah; suite kode tidak diulang untuk perubahan dokumentasi saja.
- Batas bukti tetap: belum terbukti firmware x86 ini boot/login atau menerima
  lisensi setelah reboot. Generator/parser konsisten hanya menguji bentuk
  payload, ID, dan signature; jangan melabeli artifact siap produksi atau
  aktivasi pasti berhasil. Kunci deployment tidak diganti.

**Titik lanjut:** launcher dan suite Windows sudah lulus serta source fix
ter-push. Pemakaian ada di [panduan Windows](windows-license.md); filesystem
output perlu hard-link support (NTFS). Yang masih terbuka ialah hash ulang
artifact firmware, enam arsitektur non-x86, boot/login dan aktivasi dengan ID
sama setelah reboot. Keberhasilan launcher tidak menutup pekerjaan firmware
itu. Tidak ada build/QEMU lokal atau akses VM baru tanpa arahan pemilik.

### 14. Pemeriksaan ulang rilis publik (2026-10-05)

- Acuan checkout dan remote `main`: `6071aea`; working tree bersih sebelum
  pemeriksaan. GET anonim GitHub API untuk releases, run `patch7.yml`, jobs,
  dan metadata artifact dijalankan ulang pada sesi ini.
- Rilis publik yang terdaftar masih `7.24.4` (Latest menurut status sebelumnya)
  dan `7.23.3`; masing-masing 40 aset. Rilis `7.24.4` mencatat commit sumber
  `bd2dc61`. Aset CHR x86 VMDK ZIP dibuat/diperbarui pada 2026-10-02,
  sebelum perbaikan engine `daf390f`; catatan rilis menegaskan aset belum
  dibangun ulang. Tidak ada rilis publik baru yang memuat fix engine.
- Run firmware terbaru tetap `37207497763` pada `c636fa6`: job x86 sukses,
  enam arsitektur lain gagal, dan job release skipped. Artifact x86
  `11305142056` masih tersedia (`expired: false`), kedaluwarsa
  `2026-10-18T14:04:00Z`. Artifact Actions bukan rilis firmware permanen.
- Ini pemeriksaan metadata langsung, bukan unduh/hash ulang firmware atau
  uji boot/aktivasi. Tidak ada build baru, publikasi, pergantian tag/aset,
  instalasi VM, atau pengulangan suite pada sesi ini. Jangan menyarankan
  install ulang aset rilis lama sebagai solusi lisensi; kandidat x86 baru
  tetap memerlukan verifikasi isi dan uji lab sebelum mengganti VM pemilik.

### 15. Audit rilis, perbaikan pipeline lokal, dan uji kandidat nyata (2026-10-05)

**Acuan checkout:** `main`, HEAD `6071aea0a8059aa4378d56d0e41918ef6bd4bf3b`,
HEAD/origin-main 0/0 pada pemeriksaan sesi. Perubahan berikut belum di-commit
atau di-push. Tidak ada build Actions baru, draft, atau firmware baru diterbitkan.
Bukti tersanitasi: [release-audit-2026-10-05.json](evidence/release-audit-2026-10-05.json).
Panduan gate: [release-validation.md](release-validation.md).

#### Perubahan source yang benar-benar dilakukan

- `.github/workflows/patch7.yml`: pilihan eksplisit `all` / `chr-x86`.
  `all` tetap gagal bila arsitektur wajib gagal; `chr-x86` hanya enam format
  CHR x86, tanpa ISO/Netinstall/produk lain. Tidak memakai bypass guard,
  `continue-on-error`, atau mengganti keypair. Env kunci dibandingkan dengan
  HEAD dan tidak berubah; engine `patch.py`/`npk.py` juga tidak diubah.
- Semua NPK dalam all-packages memakai `patch.py npk`, bukan signing langsung
  tanpa kontrak cakupan. ARM64 memakai satu sumber archive authoritative,
  bukan update ZIP yang bisa mempertahankan entri ISO lama. Draft tetap untested,
  prerelease, bukan Latest, memakai tag run/attempt baru dan commit build.
- `scripts/release_assets.py`: profile/inventory ketat, file kosong ditolak,
  stage transactional dan cleanup miliknya sendiri, rehash hasil copy, serta
  publikasi non-overwrite native Windows; Linux/macOS mempertahankan exclusive rename.
- `scripts/validate_chr_image.py` + tes baru: hash ZIP utuh dibandingkan manifest
  dan checksum, satu member yang tepat, ukuran aktual cocok metadata, CRC,
  header VMDK/QCOW2, tanpa encrypted/symlink/special-file member. Review independen
  mereproduksi dua celah awal (mode file khusus dan ukuran declared palsu);
  keduanya diperbaiki dan tes regresinya lulus. Ini bukan verifier aktivasi.
- `.gitattributes` menetapkan shell script LF; checkout `deploy/install-panel.sh`
  dinormalisasi dari CRLF menjadi LF, byte konten ternormalisasi cocok HEAD,
  tanpa perubahan logika. Fixture subprocess x86 mempertahankan env Windows
  yang dibutuhkan (`SYSTEMROOT`, `WINDIR`, `TEMP`, `TMP`). Tes terkait diperluas.

#### Integritas dan runtime kandidat — hasil tool, bukan laporan VM pemilik

- Kandidat nyata dari commit `c636fa654f23b807b2adb51e24106396783cb246`,
  run `37207497763`, artifact `11305142056` (kedaluwarsa 2026-10-18 14:04 UTC).
  Unduhan selective HTTP ranges memverifikasi member terpilih, **bukan hash
  keseluruhan outer artifact 1 GB**. ZIP VMDK 65,484,382 byte:
  SHA-256 `8dab31741761959ee4ed9e26d2d9abd6e7144f6fe68f95e3ed9e083a5c2f7e4f`.
  Hash cocok manifest/SHA256SUMS dan CRC lulus. Parent menjalankan validator
  final terhadap ZIP tersebut, lulus. Tidak ada verifikasi signature firmware
  nyata baru pada sesi ini.
- VMDK 67,567,616 byte:
  SHA-256 `328b34d4ff3fc116dfbdb548eafd02b46733d4d7aa211cdef93ff23778649f75`.
  QEMU 8.2.2 TCG di WSL Ubuntu, SeaBIOS, 512 MiB, 1 vCPU, IDE,
  fresh disposable qcow2 overlay, tanpa NIC. Tidak mengakses VM pemilik,
  tidak mengirim keyboard/login/lisensi. Base hash sebelum/sesudah sama;
  proses dihentikan melalui host QMP quit, bukan shutdown guest bersih.
- **Tidak mencapai login selama 240 detik.** OCR screenshot 30/60/90/120 detik
  menunjukkan `Starting services...`; 180 detik menunjukkan
  `SCRIPT ERROR: std failure: timeout (13)` dan `Rebooting...`; 240 detik
  menambah `failed to stop parser: std failure: timeout (13)`. Serial nol byte.
  Read gambar dicoba, tetapi model tidak menerima media, sehingga interpretasi
  layar **OCR-only, bukan konfirmasi visual**. Ini urutan reboot pertama,
  bukan bukti loop berulang, fault `sys2`, akar sebab, atau perilaku VMware.
  Kandidat ini berbeda dari eksperimen pre-review §8–10.
- Setup awal gagal karena MSYS path conversion, module path QEMU, dan VGA ROM;
  itu kegagalan harness sebelum uji selesai, bukan kegagalan firmware tambahan.
  Pembanding aset lama tidak selesai diunduh dalam budget 180 detik;
  partial ZIP tidak diverifikasi/tidak dipakai dan **tidak ada boot pembanding baru**.
  Bukti historis login aset lama bukan fresh matched control sesi ini.
- **Aktivasi tidak diuji karena gate boot gagal.** Jangan publish/rekomendasikan
  kandidat sebagai solusi install ulang. JSON ringkasan/OCR tersanitasi tahan lama
  ada di repo; screenshot mentah, full runtime JSON, firmware dan overlay masih
  di folder sementara Windows `mikpatch-lab-20261005`, tidak di-commit.
  Hash screenshot di evidence bukan pengganti file gambar bila scratch hilang.

#### Tes aktual dan kendalanya

- WSL Ubuntu Python 3.12.3, `python -B -m unittest discover -s tests -v`:
  **302 tes, 295 lulus, 7 skip, exit 0, 210.675 detik**. Skip: satu native Windows
  rename, empat cmd.exe, dua Caddy nyata opsional. Full run dimulai sebelum dua
  regresi validator terakhir ditambahkan; jangan menyebut 304 full-suite lulus.
- WSL `python -O -B -m unittest discover -s tests -p 'test_patch*.py' -v`:
  **72 tes, 0 skip, exit 0**; SquashFS nyata tersedia. Bukan seluruh suite mode -O.
- Native Windows Python 3.14.0: release helper normal dan `-O` masing-masing
  **59 tes, 58 lulus, 1 skip POSIX permissions**; child CLI mewarisi -O.
  Race destination Windows nyata lulus. Validator final **11/11** (parent ulang),
  engine x86 **20/20**, workflow **24/24**, license CLI **28/28**,
  launcher cmd.exe **9/9**, semuanya tanpa skip.
- 17 shell block workflow `bash -n`, empat kasus validasi profile, pip check,
  YAML parsing, dan `git diff --check` lulus. Pemeriksaan akhir dokumentasi:
  26 link relatif valid, evidence JSON parse, tidak ada nilai kunci workflow
  terpin pada dokumen/validator baru yang diperiksa. Review independen tidak menemukan
  blocker profile/draft setelah delta validator diperbaiki.
- Baseline native Windows penuh gagal (272 tes, 22 failure, 14 error, 8 skip):
  beberapa deployment POSIX tidak portable, SquashFS/Caddy tidak tersedia,
  CDLL Windows dan env subprocess. **Suite penuh Windows tidak diulang**;
  hanya suite targeted di atas lulus. Linux awal juga gagal: 280 tes,
  20 failure/6 skip karena CRLF shell; intermediate 302 tes error 1/skip 7
  karena mock metadata baru belum autospec. Keduanya diperbaiki sebelum full
  Linux final hijau; jangan menghapus riwayat kegagalan dari laporan.

#### Perubahan remote yang sudah diverifikasi

- Catatan rilis `7.24.4` (`401538288`) dan `7.23.3` (`401130489`) diperbarui
  melalui gh API: warning tegas aset lama bukan fix lisensi; hasil kandidat baru
  dibedakan dari aset terbit dan dari versi 7.23.3. Catatan lama dipertahankan
  sebagai historis. Cakupan izin: perapian rilis sesuai permintaan audit/perbaikan,
  bukan publikasi firmware baru atau push source.
- GET setelah PATCH mengonfirmasi body tepat, serta ID/nama/size/digest/state/
  updated_at **40+40 aset** tidak berubah. Tag/target/name/draft/prerelease tetap;
  Latest tetap 7.24.4. Ini metadata comparison, bukan hash ulang semua 80 file.
  Tidak ada tag dipindahkan, aset diganti/dihapus, atau firmware baru diunggah.
- Kendala utama tersisa: kandidat engine baru tidak lolos boot ke login,
  aktivasi belum terbukti, dan kontrol baru belum tersedia. Perbaikan pipeline
  tidak mengklaim memperbaiki runtime. Jika investigasi dilanjutkan, gunakan
  matched control dan ubah satu variabel dengan provenance tetap; jangan
  mematikan check konsistensi atau cakupan untuk memaksa login.

### 16. Investigasi runtime terfokus setelah permintaan pemilik (2026-10-05, berlangsung)

Pemilik menegaskan target adalah build yang benar-benar menerima lisensi lab,
bukan hanya tooling rilis. HEAD tetap `6071aea` pada `main` dengan perubahan
lokal §15 dipertahankan. Tidak ada commit/push atau publikasi baru pada tahap ini.

- **Kontrol lama kini berhasil diperoleh dan diuji**: ZIP SHA-256
  `b0635638f96ec073d75c9ef028812a64aaec11e27f079a2ad4b1dd9337d9bf7a`
  cocok digest rilis, manifest dan checksum; VMDK SHA-256
  `14dc40bce8f85de0fabad4dd641b14b4f71bb5a0a0c030beef96c243296fc728`.
  Satu run 240 detik dengan konfigurasi QEMU identik kandidat: `CHR Login:`
  muncul pada sampel pertama 30 detik dan semua sampel berikutnya sampai 240.
  Bukti serial menguatkan OCR; tidak ada login/input/lisensi dikirim.
  Base hash tidak berubah, proses berhenti melalui QMP quit.
  [Bukti kontrol](evidence/chr-7.24.4-old-release-control-2026-10-05.json).
  Ini menggantikan kendala unduhan kontrol §15, bukan bukti aktivasi.
- **Crash kandidat nyata terlokalisasi offline**: dua catatan `sys2` SIGSEGV
  pada `0x0805bfd3`; log tidak ada pada base pristine. Package custom signature
  valid menurut verifier repo; kernel boot terpasang cocok byte dengan
  FILE_CONTAINER, demikian pula bash/milo. Tidak ada perubahan base/overlay.
  [Bukti offline](evidence/chr-7.24.4-candidate-offline-crash-2026-10-05.json).
- **Koreksi interpretasi cabang lama**: lokasi abort punya lebih dari dua
  predecessor. Register kandidat `EAX=0x6ed4` mendukung cabang `0x0805a9ef`
  (hasil lookup 173, expected 164) pada asumsi alur normal, bukan bukti langsung
  mismatch dua buffer waktu yang diduga sebelumnya. Data tabel berasal dari
  jawaban IPC loader melalui libumsg; perubahan anchor loader sebagai penyebab
  tetap hipotesis, tidak dibuktikan oleh disassembly saja.
  [Trace statis dan batas inferensi](evidence/chr-7.24.4-candidate-static-startup-trace-2026-10-05.json).
- Parent menguji synthetic challenge signature dua pasangan key workflow:
  pasangan lisensi KCDSA dan signing paket EdDSA konsisten. Hanya boolean
  dilaporkan; tidak ada keypair baru/nilai kunci diekspor. Ini bukan aktivasi.
- **Eksperimen berpasangan selesai** dari input vendor raw SHA-256
  `e87eaa06af9e29f5946d951a0595de56d6e8a972d023e34e56583412265063e7`:
  baseline full (`c03c1674…`) kembali gagal login selama 240 detik, dua crash
  `sys2` di `0x0805bfd3`; diagnostik loader-preserved (`61093f05…`)
  mencapai login pada 30 detik dan setiap sampel hingga 240 detik. Dari
  582 file reguler, hanya isi `nova/bin/loader` berbeda (32 byte immediate);
  mode/mtime kedua varian identik. Keduanya menggunakan toolchain, input,
  metadata policy, dan kernel boot yang sama. Ini mengisolasi penggantian
  anchor lisensi loader sebagai pemicu regresi boot dalam pasangan ini,
  bukan bukti mekanisme internal lengkap atau dukungan arsitektur lain.
  [Bukti eksperimen](evidence/chr-7.24.4-loader-anchor-experiment-2026-10-05.json).
- Guard cakupan tetap aktif; full menghasilkan mapping lisensi/signing 3/5,
  loader-preserved 2/5 penggantian nyata. Signature custom keduanya valid
  menurut verifier repo. Tidak ada check `sys2` atau signature dimatikan.
  Diagnostic memakai intersepsi scratch dan kebijakan mtime/all-root/mkfs-time
  yang sama pada kedua varian; **belum menjadi fix produksi `patch.py`**.
  Verifier repo menolak signature input vendor, sehingga autentisitas
  kriptografis vendor belum dapat diklaim dari pemeriksaan tersebut.
- Probe aktivasi awal belum konklusif: percobaan pertama berhenti pada parser
  output lisensi; kedua berhasil login admin lokal, membaca level `free`,
  dan memverifikasi signature/ID payload lokal, tetapi pembacaan prompt echo
  mengganggu urutan paste/reboot. Kedua probe tidak menghasilkan bukti level
  pascareboot; ini kegagalan helper, bukan verdict penerimaan firmware.
  Base tetap tidak berubah, tanpa NIC/kontak VM pemilik; helper sedang
  diperbaiki pada scratch. Riwayat kegagalan helper dipertahankan sebagai
  incomplete, bukan penolakan lisensi.
- **Probe lengkap berikutnya berhasil**: raw diagnostik `61093f05…` boot/login,
  level awal `free`; payload dibuat dengan key yang sudah ada hanya di memori
  dan wrapper memverifikasi signature lengkap serta kesamaan ID. CHR menolak
  `/system license input`; global paste blok empat baris memerlukan satu baris
  kosong tambahan untuk menyelesaikan multiline entry. Pesan acceptance segera
  tidak berhasil ditangkap, tetapi setelah `/system reboot` nyata level menjadi
  **`p-unlimited`**, setelah reboot kedua tetap **`p-unlimited`**, dengan ID sama
  pada kedua pembandingan. Setelah shutdown guest bersih dan proses QEMU baru
  memakai overlay yang sama, level masih **`p-unlimited`**. Kesamaan ID cold
  restart tidak diuji karena ID awal tidak dipersist antarproses host.
  [Bukti aktivasi/persistensi](evidence/chr-7.24.4-loader-preserved-activation-2026-10-05.json).
  Tidak ada NIC, kontak VM pemilik, penggantian keypair/password atau check
  bypass. Base hash tetap; pemeriksaan `/proc` sesudah cleanup: 0 proses QEMU.
  Overlay berisi lisensi tersimpan dan tetap scratch-only, tidak untuk publikasi.
  Satu uji aktivasi berhasil ini bukan bukti VMware, upgrade, semua arsitektur,
  bandwidth atau pengujian jangka panjang. Suite source tidak diulang pada fase
  diagnostik; `git diff --check` dan cek 31 link dokumen/scan nilai sensitif lulus.
- Implementasi kebijakan produksi sempit CHR x86 7.24.4 dan tes regresi sedang
  berjalan; build final tanpa intersepsi scratch dan aktivasi pada VMDK final
  tetap wajib sebelum menyatakan artefak siap diserahkan.

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
[8] https://github.com/devlhi/al_MikhroTik_patch/actions/runs/37207497763 — GitHub Patch v7 c636fa6: x86 sukses, enam gagal
[9] https://github.com/devlhi/al_MikhroTik_patch/actions/runs/37214834349 — Windows launcher f392288: native menu passes, symlink tests fail
[10] https://github.com/devlhi/al_MikhroTik_patch/actions/runs/37219037250 — Windows hard-link fix 9b4d6f9: 52 tests per Python, no skips


### 17. Build produksi lokal dan uji VMDK final (2026-10-05)

**Hasil tool aktual:** final VMDK berhasil boot/login dan menerima kode lab dari
konfigurasi kunci yang sudah ada; level awal free, lalu p-unlimited setelah dua
reboot dan shutdown/cold restart, dengan System ID sama pada ketiga pemeriksaan.
VM pemilik tidak dihubungi. Bukti hanya QEMU/TCG, BIOS, IDE, 512 MiB, 1 vCPU,
-NIC none; bukan VMware, upgrade, throughput atau uji jangka panjang.

- Acuan Git: main HEAD6071aea0a8059aa4378d56d0e41918ef6bd4bf3b, remote sama,
  0 ahead/behind saat awal lanjutan. Semua perubahan masih lokal; tidak ada
  commit/push/dispatch/publikasi baru atau penggantian tag/aset lama.
- Implementasi patch.py: policy sempit chr-x86-7.24.4, loader LICENSE anchor
  dipertahankan namun tidak dihitung coverage, keyman/mode wajib berubah nyata.
  Signing/check sys2 tidak dimatikan. Workflow memakai opsi hanya CHR x86 7.24.4.
- Dua percobaan produksi sebelumnya gagal sebelum signing karena metadata parity.
  Diagnosis no-key mengonfirmasi caller umask077 menyebabkan 582 file regular
  diekstrak0755→0700 atau0644→0600. Fix memberi subprocess extraction umask0
  hanya di child POSIX; mask parent/private directory tetap, parity tetap ketat.
  Roundtrip vendor893 entry setelah fix:0 delta. patch.py fingerprint final:
  e2fb985d61733393e0345970c67bf594dbd83676430dfe2a4ae34d0c07a6b035.
- Review independen source menemukan0 blocker produksi, tetapi1 helper tes
  mengekstrak tanpa child umask0. Full suite awal077:333total,325pass,7skip,
  1failure,0error. Suite022:333total326pass7skip. Helper tes diperbaiki;
  full suite FINAL077:333total326pass7skip0failure/error exit0,166.186s.
  Skip:4cmd.exe,1Windows rename,2optional Caddy. Policy26/26 normal dan-O
  dilaporkan implementer sebelum helper fix; parent26/26 normal077 setelahnya.
  Patch suites75/75 normal/-O; Windows policy12pass14skip (SquashFS/POSIX).
  Full suite lama331/324pass7skip adalah checkpoint sebelum2 regresi tambahan.
- Build direct production patch_npk_file, tidak monkeypatch, lolos coverage
  LICENSE2/signing5, signature custom, metadata guard,582file inventory,
  loader unchanged, mtime0delta, NPK/kernel readback dan raw/VMDK compare.
  Partisi BIOS template pembanding dipakai ulang dengan hash pinned; partisi
  sistem vendor pristine dipatch baru. Bukan eksekusi identik workflow CI atau
  inventory rilis6format; hanya final VMDK/ZIP lokal.
- Delivery dist/chr-x86-7.24.4-runtime-fix berisi base BELUM diaktivasi,
  ZIP, manifest, SHA256SUMS, build-evidence dan runtime-evidence.
  VMDK SHA2561e86aad1c10fe42294bac28be9597922579989ed210f3d5aed87eff83bd7fa08;
  ZIP SHA256ad5e18d81144f17d948e67b26cf495ccc9703e6686c8437190ba95230d8c7dd5.
  /dist/ diabaikan Git. Activated overlay hanya scratch, tidak disertakan.
- Probe memakai fresh qcow2 dengan backing FINAL VMDK, bukan raw diagnostik.
  Signature dan ID payload diverifikasi lokal; paste global multiline ditutup
  baris kosong. Pesan acceptance eksplisit tidak teramati; bukti penerimaan
  adalah level p-unlimited aktual. Dua guest reboot dan cold restart melalui
  proses QEMU baru semuanya mempertahankan level serta ID. Dua clean shutdown,
  QEMU keluar dan hash base tetap. ID/password/license/log console mentah
  tidak diekspor; password dan keypair tidak diganti. Autentisitas signature
  vendor masih belum established; signature CUSTOM diverifikasi.

Bukti tahan lama: [build final](evidence/chr-7.24.4-final-build-2026-10-05.json),
[runtime final](evidence/chr-7.24.4-final-vmdk-runtime-2026-10-05.json),
[tes/review final](evidence/chr-7.24.4-final-source-tests-2026-10-05.json), dan
[panduan lokal](chr-7.24.4-local-install.md). Checkpoint review lama mencatat
kegagalan sebelum fix, bukan verdict akhir. Langkah tersisa di luar bukti lab:
validasi VMware dan pemakaian lama, serta commit/push/rilis hanya dengan izin
pemilik untuk tindakan itu. Jangan klaim remote release sudah diperbarui.

Validasi penyerahan terakhir: git diff --check exit0;34link relatif pada
HANDOFF/panduan/kontrak valid,0missing; pemindaian nilai kunci pinned pada
dokumen/evidence0hit; dist terkonfirmasi diabaikan Git; hash VMDK/ZIP
dibaca ulang sesudah uji dan cocok. Tidak ada raw log disalin ke repo.

### 18. Permintaan push dan cakupan semua arsitektur (2026-10-05)

Pemilik meminta push perubahan dan memastikan bukan hanya VMDK: x86,ARM,dll.
Review read-only aktual: profil all mencakup x86,arm,arm64,mipsbe,mmips,smips,ppc
dengan37aset firmware+3metadata.27tes workflow dan20matcher lulus,8file Python
parsed serta diff check lulus. Namun6arsitektur non-x86 masih memiliki kegagalan
LICENSE coverage historis; matcher immediate yang tersedia hanya i386. Policy
runtime hanya CHR x86, bukan ISO/install-image. NetInstall memiliki jalur lama
yang menangkap error individual tanpa guard setara. Tidak ada klaim semua
produk siap, tidak memperluas exception atau melemahkan guard.

Acuan sebelum commit6071aea; main dan live remote sama. Push diizinkan pemilik
untuk sesi ini. Source/evidence akan dipush tanpa dist,overlay atau kunci baru.
GH CLI ditemukan tetapi belum authenticated pada environment default; git push
--dry-run berhasil. Build all belum dijalankan pada checkpoint ini.


Hasil akhir push/build all: commit source140b94a049798b2c1e58eceb13af64e7281f2ecf
berhasil dipush ke origin/main. Run37277711016 pada commit itu selesai failure:
x86 success (ISO,install-image,CHR,NetInstall,stage,validator dan upload), enam
lainnya failure. Semua enam log gagal yang dibaca menunjukkan ValueError:
no replacement for required mapping(s) 1 in system package; signing blocked.
ARM64 berhenti pada ISO; ARM/MIPSBE/MMIPS/SMIPS/PPC pada standalone NPK.
Tidak ada bypass. Build success x86 tidak membuktikan runtime ISO/install-image/
NetInstall; hasil boot/aktivasi lokal hanya CHR VMDK §17. Hasil CI belum diuji boot.

Artifact x86 baru ID11330614951,1017398869byte, digest API GitHub
13ffb69e306daf179db056562850fb3dd8054b75377643d657b923b814690ba2;
metadata API saja, bukan unduh/hash ulang1GB. release job skipped; dispatch
create_draft_release=false, tidak ada draft/publikasi/tag/aset lama diganti.
Bukti tahan lama: [build semua arsitektur](evidence/all-profile-build-2026-10-05.json).
Autentikasi GH berhasil memakai credential Git yang sudah tersimpan, hanya
in-memory child environment, tanpa mencetak nilai atau menulis konfigurasi login.

Blokir tersisa: representasi verifier LICENSE non-x86 belum didukung/terverifikasi;
perlu investigasi per arsitektur dan perangkat/emulasi yang sesuai untuk bukti
boot/aktivasi. Jangan menganggap semua siap karena workflow matrix lengkap.
Tes terbaru sesi ini27workflow+20matcher, tidak mengulang full333 karena kode
produksi tidak diubah setelah suite final sebelumnya; hanya dokumentasi/evidence
hasil build diperbarui setelah commit source.
