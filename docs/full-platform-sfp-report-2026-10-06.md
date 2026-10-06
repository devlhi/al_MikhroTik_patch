# Laporan firmware lintas produk dan SFP — 2026-10-06

## Ringkasan dan sumber bukti

Pemilik melaporkan CHR VMDK berhasil. OCR lokal pada screenshot membaca label
`p-unlimited` dan caption Ali Media Patch. Ini laporan pemilik yang konsisten
dengan aktivasi berhasil; bukan pengujian reboot/cold restart baru oleh agent.
Nama/hash image pada mesin pemilik, identitas NIC, dan konfigurasi hypervisor
belum diverifikasi. System ID, kredensial dan blok lisensi tidak dicatat.

Source acuan: `60ed61cd0673a126cdf0bb8846c24a940518bd8e`.
Perubahan pada laporan ini masih working tree, bukan commit/rilis baru.
Rilis NEW yang telah terbit tetap hanya CHR x86 enam format.

## Produk dan arsitektur

| Produk | Cakupan tersedia dalam pipeline | Status bukti |
| --- | --- | --- |
| CHR x86 | IMG, QCOW2, VMDK, VHD, VHDX, VDI | Rilis NEW telah terbit; integritas/ekuivalensi sektor lulus; VMDK berhasil menurut pemilik |
| RouterOS x86 installer | ISO BIOS/EFI, enam format install-image | ISO v2 lulus install/disk-only login QEMU BIOS dan UEFI; IMG v1 USB BIOS lulus. Level 6 persisten hanya diuji pada v1 BIOS/IDE; USB UEFI/bare-metal belum terbukti |
| RouterOS x86 packages | NPK + all-packages ZIP | Termasuk inventori x86-all; signing/coverage bukan bukti install/aktivasi |
| NetInstall | Windows 32/64 dan Linux CLI | Fallback bootloader asli dihapus; error/oversize menolak output; regresi sintetis lulus, deploy belum diuji |
| ARM64 | ISO, CHR enam format, NPK, all-packages | Build sebelumnya gagal LICENSE guard; belum siap |
| ARM, MIPSBE, MMIPS, SMIPS | NPK + all-packages | Matcher/runtime belum terbukti, guard tetap memblokir |
| PPC | NPK + all-packages | Matcher offline hanya keyman/mode; loader belum didukung, bukan kesiapan paket |
| TILE | NPK + all-packages | Ditambahkan ke inventory; matcher, boot dan hardware belum terbukti |

Profil x86-all memilih tepat 18 artefak x86. Profil all kini membutuhkan 39
artefak firmware/tools dari delapan arsitektur. Metadata manifest/checksum/notes
tidak dihitung sebagai format firmware. Format disk dan jenis produk berbeda:
CHR IMG bukan install-image, dan ISO bukan disk sistem terpasang.

### Uji installer: instalasi sukses tidak sama dengan sistem dapat boot

Dua ISO berbeda diuji pada QEMU 8.2.2/TCG/SeaBIOS/IDE, RAM 512 MiB,
1 CPU, disk sementara 1 GiB, tanpa NIC dan tanpa akses disk fisik:

- **ISO rilis lama** (SHA-256 `790a79251afc6cb8c0d66d024457e757950cdd93b51f43195472b271fb76a74b`):
  menu installer, instalasi, lalu boot disk tanpa CD mencapai prompt login.
- **ISO build all run37277711016**, source `140b94a`, artifact11330614951
  (SHA-256 `4e4a5577f1701189dbae31ebad9cbc52bc16ffd04943dee21d277719395faa5b`):
  menu installer dan instalasi selesai, tetapi boot disk tanpa CD **gagal mencapai
  login**. OCR pada 45/90 detik menangkap loading system/starting services/reboot,
  termasuk timeout pada 90 detik. QEMU dengan `-no-reboot` sudah keluar pada
  observasi 180 detik. Kandidat ini gagal gate boot hasil instalasi.

ISO kedua berukuran 71.161.856 byte, diambil melalui HTTP range dari arsip Actions;
CRC member serta SHA256SUMS terverifikasi. Digest arsip lengkap sekitar 1 GB
**tidak diverifikasi**, karena seluruh arsip tidak selesai diunduh. Kedua ISO
menampilkan `open /dev/panics failed` saat install; pesan itu saja bukan diagnosis.
Tidak ada aktivasi pada kedua probe historis tersebut. UEFI, NVMe atau Mini PC
tidak diuji; OVMF tidak tersedia. Hasil rebuild baru dicatat terpisah di bawah.
Observasi berasal dari OCR screenshot sampel, bukan serial kontinu; reboot
berulang tidak dibuktikan. [Bukti ISO build all](evidence/all-profile-run37277711016-iso-boot-20261005T173229Z-0decf647.json)
dan [pembanding lama](evidence/x86-iso-bios-install-probe-20261005T170357Z-81a08fcf.json)
disimpan durabel dengan batas provenance.

Investigasi lanjutan pada pasangan disk x86 terpasang mengisolasi penggantian
anchor loader sebagai penyebab kegagalan boot pada konfigurasi lab tersebut:
varian preservasi loader mencapai login 30 detik, menerima Level 6 lab dan
mempertahankannya setelah dua reboot serta cold restart. Di antara 582 file
reguler hanya loader berbeda; serialization SquashFS/signature juga berbeda.
[Evidence A/B](evidence/x86-installer-runtime-investigation-20261005T181703Z-9c41b8a2.json)
bukan bukti hasil rebuild ISO/install-image atau keberhasilan Mini PC.

Kebijakan opt-in `x86-installer-7.24.4` dibuat terpisah, dengan pin source dan
komponen ketat. Empat NPK sumber dari unduhan HTTPS vendor dan cache cocok
byte-identical; verifikasi signature vendor dengan verifier/kunci konfigurasi
repo menghasilkan false, sehingga keaslian kriptografis belum terbukti.
[Bukti kualifikasi sumber](evidence/x86-installer-runtime-investigation-source-qualification-20261005T184216Z.json)
menyimpan batas tersebut. Celah provenance API dan FAT ordering telah diperbaiki
serta lulus re-review independen. Rebuild media lokal (ISO dan install-image)
masing-masing berhasil install ke disk virtual terpisah 1 GiB pada QEMU SeaBIOS/IDE,
boot tanpa installer, login autentikasi, serta mempertahankan lisensi Level 6 lab
setelah dua reboot dan cold restart dengan Software ID sama (tidak diekspor).
[Bukti build dan install](evidence/x86-installer-runtime-investigation-build-and-install-20261006.json)
mendokumentasikan hash media dan rincian pengujian. Image diuji sebagai media
sekunder IDE, bukan booting USB atau instalasi langsung image ke disk. Hasil ini
terbatas pada lab BIOS/IDE 0 NIC; bukan bukti Mini PC fisik atau UEFI.

Penyebab error Mini PC pemilik tetap belum diketahui: nama/hash image, alat
flashing, BIOS/UEFI dan controller storage belum teridentifikasi. Penjelasan
lama bahwa geometri/format FAT pasti penyebabnya dicabut; layout saja tidak
membuktikan sebab.

PPC parsial sempat diintegrasikan dengan guard package-wide minimal. Review
independen menunjukkan satu keyman yang cocok dapat menambah coverage meski
mode/loader tidak didukung. Integrasi produksi tersebut telah dihapus; matcher
tersimpan sebagai alat offline sampai kebijakan paket/runtime yang lengkap
terverifikasi. Regresi memastikan coverage parsial tidak memicu signing/save
atau menimpa output yang sudah ada.
Tidak menyalin kebijakan loader CHR ke installer/non-x86 tanpa bukti.

## Hasil lanjutan: ISO v2 BIOS/UEFI dan USB

Katalog El Torito ISO v1 memuat count EFI 4096, hasil overflow 16-bit dari
69.632 sektor pada image EFI 34 MiB. Akibatnya rEFInd tidak menemukan kernel.
Koreksi dua byte mengisolasi sebab; fix produksi mengganti genisoimage/mkisofs
menjadi xorriso dengan BIOS load-size 4 dan EFI load-size 0 yang terpisah.
Regresi ISO nyata 1/32/34 MiB serta review readback lulus; NPK/kernel/EFI tidak
berubah. [Bukti build v2](evidence/x86-iso-xorriso-build-readback-20261006.json).

**ISO v2 exact berhasil install ke disk kosong, boot tanpa installer, login
terautentikasi dan resource 7.24.4/board x86 pada QEMU BIOS dan OVMF UEFI.**
[Bukti runtime](evidence/x86-uefi-usb-followup-production-runtime-20261006.json).
Ini repack pohon patched sebelumnya, bukan build/signing ulang dari CI.
Warning rEFInd textmode 0 juga ada pada vendor pristine; probe mengakui warning
lalu memilih default. Aktivasi v2, Secure Boot dan hardware fisik tidak diuji.

IMG v1 melalui **USB BIOS** juga berhasil install ke target virtual dan login
disk-only. **USB UEFI belum berhasil ke target yang dimaksud:** trial mengisi
overlay USB sementara, bukan disk tujuan. Penyebab belum ditetapkan sebagai bug
produk. [Bukti trial dan batasnya](evidence/x86-uefi-usb-followup-20261006.json).
Semua tes tanpa NIC dan tanpa mengakses disk fisik/VM pemilik.

ARM kini memiliki prototipe offline sangat terbatas (satu word pada mode pinned,
bukan penggantian full-key). MIPS positif hanya sintetis; seluruh kandidat nyata
tetap ditolak karena jalur resolver belum aman. Defect overlap callee MIPS sudah
diperbaiki dan direview ulang. Ketiganya bersama PPC tetap detached dari produksi;
lihat [status non-x86](non-x86-findings.md). Tidak ada klaim firmware ARM siap.

## Apa yang dimaksud dukungan SFP

Empat lapisan harus diuji secara terpisah:

1. **Kartu jaringan**: PCI vendor/device/subsystem, OEM/model, driver dan NVM.
   Nama ether saja tidak membuktikan jenis NIC atau jalur EEPROM.
2. **Modul transceiver**: vendor, part number, revision, form factor, speed,
   wavelength, connector dan jenis media. Modul optik, DAC dan SFP RJ45 tidak
   mempunyai sensor atau perilaku yang sama.
3. **DOM/DDM**: TX/RX power (dBm), temperature, voltage dan laser bias apabila
   modul mendukung dan driver/firmware mengekspos EEPROM/diagnostik.
4. **Kehilangan daya link**: perlu data arah yang benar dari kedua ujung.
   Satu nilai RX bukan redaman kabel; selisih TX dan RX lokal juga bukan loss link.

### Temuan driver statis 7.24.4

Bukti di [sfp-driver-findings.md](sfp-driver-findings.md). Ada 298 modul kernel,
bukan 298 kombinasi hardware yang teruji.

| Keluarga driver | Bukti statis | Batas penting |
| --- | --- | --- |
| ixgbe | Callback module-info/EEPROM; generic vendor-check tail warn lalu lanjut | Bukan jaminan semua modul accepted; flag allow_unsupported_sfp tidak membuktikan DOM native |
| i40e / ice | Jalur firmware EEPROM dan pemilihan jenis modul | NVM/module/firmware dan transceiver menentukan dukungan |
| igb | Pembaca SFP internal | Dua slot callback EEPROM yang diperiksa kosong; identifikasi internal bukan DOM userland |
| bnx2x / bnxt_en | Jalur module EEPROM | Guard interface/firmware/capability perlu diuji hardware |
| mlx4 / mlx5 | Jalur query EEPROM | Generasi kartu dan firmware belum diuji |
| virtio_net / vmxnet3 / VF | Driver ada | Tidak otomatis memberi akses ke sensor fisik |

Userland RouterOS menggunakan ioctl ethtool, tetapi alur lengkap dari EEPROM
ke native `/interface ethernet monitor` atau Winbox belum dibuktikan.
Tidak ada modifikasi NPK/driver SFP yang terverifikasi dalam sesi ini.
Menyisipkan parameter ixgbe secara spekulatif tidak menambahkan telemetry dan
bukan solusi universal. Tidak ada firmware NIC, EEPROM atau BIOS yang diubah.

CHR dengan NIC emulasi biasanya tidak mendapat sensor transceiver milik host.
Full PCI PF passthrough dapat menyediakan jalur fisik bila hardware/driver
mendukung; SR-IOV VF tidak setara PF dan tidak otomatis mendapat EEPROM.
Passthrough pun bukan jaminan semua DOM muncul di RouterOS.

## Redaman: definisi dan batas pengukuran

Untuk link dengan pasangan optik/lane/arah yang dikonfirmasi:

- A ke B: **TX A [dBm] - RX B [dBm] = estimasi loss A→B [dB]**.
- B ke A: **TX B [dBm] - RX A [dBm] = estimasi loss B→A [dB]**.

Angka tersebut mencakup jalur, konektor, sambungan, splitter atau attenuator,
dan ketidakpastian sensor. Itu bukan redaman serat saja, bukan posisi gangguan,
dan bukan sertifikasi insertion loss. BiDi memerlukan pasangan wavelength
TX/RX yang benar; jangan mensyaratkan TX kedua ujung sama. QSFP/CMIS/multilane
memerlukan decoder/lane mapping tersendiri dan tidak didukung parser single-lane.
Untuk pengukuran presisi gunakan light source/power meter terkalibrasi; gunakan
OTDR bila perlu karakterisasi panjang/lokasi event. Nilai negatif jangan
langsung diubah menjadi nol: periksa pairing, freshness dan kalibrasi.

## Bukti yang diperlukan dari hardware, tanpa perubahan konfigurasi

Di RouterOS, simpan output terbatas berikut dan redaksi serial, MAC, alamat,
System ID, password dan license key sebelum dibagikan:

```routeros
/system resource print
/system resource pci print detail
/interface ethernet print detail
/interface ethernet monitor <nama-port-sfp> once
```

Ambil monitor kedua ujung pada waktu berdekatan dan tulis timestamp + timezone.
Catat NIC model/PCI IDs/NVM dan part number modul beserta datasheet DOM.
Bila port belum muncul, fokus pengenalan PCI/driver terlebih dahulu. Bila port
ada namun DOM kosong, bedakan modul tanpa DOM, akses EEPROM/driver tidak ada,
dan decoder userland. Jangan menyimpulkan kabel putus dari nilai kosong.

Pembanding Linux pada hardware lab yang sama, tanpa menulis EEPROM:

```sh
lspci -nnk
ethtool -i <interface>
ethtool -m <interface>
```

Catat stdout/stderr/exit status terpisah; Linux bisa membaca DOM tidak berarti
RouterOS native pasti bisa. Jangan reboot, unbind PCI, flash NIC atau melepas
fiber produksi untuk mengambil bukti. Jangan melihat langsung ke ujung fiber.

Template lengkap: [sfp-lab-report.md](sfp-lab-report.md).
Parser yang sudah ada: `scripts/sfp_diagnostics.py`, offline dari output monitor
atau ethtool yang tersimpan; bukan reader hardware, collector SSH atau patch NPK.

## Pelengkap yang diimplementasikan: laporan optik offline

`scripts/sfp_link_report.py` memakai parser monitor RouterOS/ethtool yang sudah
ada untuk dua endpoint single-lane. [Panduan penggunaan](sfp-link-report.md)
menyediakan contoh CLI. Fitur baru:

- Estimasi loss dua arah dengan pasangan TX/RX lintas endpoint, bukan TX−RX lokal.
- Timestamp berzona waktu, batas selisih waktu, penanda data stale dan konfirmasi
  pairing optik eksplisit. BiDi tidak dipaksa mempunyai TX wavelength yang sama.
- Data hilang/nonfinite, modul/DOM tidak tersedia, checksum buruk, stale atau
  pairing belum dikonfirmasi menghasilkan unavailable beserta alasannya.
- Nilai negatif diberi warning, tidak dipalsukan menjadi nol.
- Model NIC/driver yang dimasukkan manual diberi label belum diverifikasi.
  Input dibatasi file teks reguler UTF-8 256 KiB; symlink/reparse ditolak.

Tool tidak membaca hardware langsung, tidak mengubah NPK/driver dan **tidak
membuat SFP yang sebelumnya tidak terbaca menjadi terbaca**. Informasi hardware
asli dan dukungan native RouterOS tetap ditandai belum diverifikasi. Tanggal
capture adalah input pengguna; tool memeriksa selisih antar-capture, bukan
menyatakan snapshot historis sebagai data live. Jangan masukkan serial, MAC,
license key atau informasi pribadi ke label/model maupun input laporan.

## Pengujian dan review akhir

Checkpoint lanjutan terbaru: full normal WSL frozen **540 tes, 530 lulus,
9 skip, 1 failure, 0 error** (178.647 detik). Failure cooldown tidak dihapus.
Pada source yang sama, isolated test 1/1, server 25/25 dan full repeat
**540 tes, 531 lulus, 9 skip, nol failure/error** (184.564 detik).
Akar kegagalan pertama belum diketahui: harness tidak menyimpan assertion/status
atau durasi per tes. Cooldown 60 detik dimulai sebelum signing, tetapi expiry
akibat durasi/scheduling hanya hipotesis, bukan bukti session bypass atau fix.

Workflow 39/39, ARM 19/19 dan MIPS 33/33 masing-masing normal/-O dengan nol skip.
76/76 raw source hashes serta fixtures stabil. Xorriso nyata dan fixture
ARM/MIPS/PPC aktif. Sembilan skip: rename Windows 1, QEMU opt-in 2, Caddy 2,
native BAT 4. Full -O/full Windows tidak diulang. [Bukti regresi terbaru](evidence/followup-final-regression-20261006.json)
mempertahankan failure awal dan diagnostic harness errors, bukan memberi label
seluruh hasil tanpa kegagalan.

Pada checkpoint v1 sebelumnya, full suite WSL menjalankan **486 tes: 476 lulus,
10 skip, nol gagal/error** (157.985 detik). Seluruh 72 raw hash source/config/test
stabil sebelum dan sesudah run. Sepuluh skip: fixture vendor PPC opsional (1),
rename Windows (1), QEMU opt-in (2), Caddy (2), BAT native (4). SquashFS serta Node
tersedia. Probe media QEMU di atas terpisah dari dua tes suite yang di-skip.

Focused installer **31/31**, workflow **37/37**, masing-masing normal dan `-O`.
Full suite `-O` tidak dijalankan. [Bukti tes frozen](evidence/x86-installer-final-regression-2026-10-06.json)
memuat perintah, prasyarat, ID tes/skip dan hash source. Run interim 485 tes
beririsan perubahan source, sehingga bukan acuan frozen. Run 443 tes pada
[bukti checkpoint lama](evidence/local-expanded-scope-tests-2026-10-06.json)
tetap historis. Full Windows pernah gagal (15 failure, 13 error, 47 skip);
suite Linux/focused Windows tidak membuktikan kegagalan tersebut diperbaiki.

Review menemukan dua defect P2: canonical serialization menghilangkan bukti
wire malformed pada direct API; serta EFI/kernel FAT ditulis sebelum preflight.
Keduanya diperbaiki, mendapat regresi dan re-review independen lulus. File/API
kini memerlukan wire asli yang dipin; FAT menyelesaikan preflight/dispatch NPK
sebelum boot writes. Bukan transaksi rollback atau bukti eksekusi CI. Nilai
konfigurasi workflow tidak diubah. Hasil ISO lama tetap gagal; dua media baru
memiliki hash berbeda dan bukti runtime sukses tersendiri.

## Artefak lokal dan pemakaian yang tidak boleh tertukar

**ISO terbaru:** [mikrotik-7.24.4-x86-installer-lab-v2-uefi.iso](../dist/x86-installer-lab-v2-uefi/mikrotik-7.24.4-x86-installer-lab-v2-uefi.iso),
71.157.760 byte, SHA-256
`87ef83ad64fbc5da71283c4176543cf248f7b8ce81b6936ae18c87d41c5f4281`.
Folder `dist/x86-installer-lab-v2-uefi` memuat manifest, SHA256SUMS serta bukti
build/runtime. Status lokal BIOS/UEFI boot validated, **belum dipublikasikan**;
aktivasi pada exact ISO ini belum diuji. Folder delivery diabaikan Git dan hanya
tersedia lokal; bukti durable ada di docs/evidence.

Folder `dist/x86-installer-lab-v1` tetap dipertahankan dan memuat:

- `mikrotik-7.24.4-x86-installer-lab-v1.iso` — 71.161.856 byte; SHA-256
  `9aafa225ddf31f7ee795039ae9cb4b0b2a2a6bb0742d605079a9b0c581556820`.
- `install-image-7.24.4-x86-installer-lab-v1.img.zip` — 35.032.805 byte; SHA-256
  `3876a41ab116dc1c59ad4d1c8a15e6e005bd3d099e8cdc40a78240b72f4c439a`.
- Manifest, SHA256SUMS, dan salinan evidence. Tidak ada disk target teraktivasi,
  kredensial, identifier atau file lisensi.

ISO dan install-image adalah **media installer**, bukan disk RouterOS siap
boot hasil instalasi. Uji memakai media installer terpisah dari disk target
kosong. Jangan mengartikan hasil ini sebagai bukti bahwa menulis IMG ke SSD
lalu menjalankan SSD itu langsung sudah menginstal RouterOS. Instalasi memformat
disk target; backup dan identifikasi disk wajib sebelum percobaan hardware.
Hasil lanjutan membuktikan ISO UEFI dan IMG USB BIOS pada QEMU saja. USB UEFI
ke target yang dimaksud, NVMe dan model Mini PC pemilik tetap belum terbukti.

Build ini dijalankan lokal memakai patcher produksi, bukan GitHub Actions.
Builder menggunakan mtools, bukan seluruh YAML/loop mount; hash workflow saat
build dan saat delivery berbeda dan keduanya disimpan di evidence. Tidak ada
klaim build dapat direproduksi byte-identik dari satu commit remote saat ini.

## Status penyerahan

**Publikasi NEW v2 selesai 2026-10-06:** source `369f5b9` dipush hanya main,
CI [37407917092](https://github.com/devlhi/al_MikhroTik_patch/actions/runs/37407917092)
x86-all berhasil. [NEW v2 prerelease lab](https://github.com/devlhi/al_MikhroTik_patch/releases/tag/ali-patch-code-7.24.4-run37407917092-attempt1)
memuat18produk+3metadata; seluruh21aset diunduh, size/SHA/GitHub digest cocok,
15ZIP CRC/13NPK signature/12disk container-sector equivalence lulus. Empat
structural checks raw/VHD unsupported; delapan format lain pass. Ini bukan
runtime: **tidak ada boot/login/aktivasi ulang pada aset CI**. ISO lokal v2 dan
Level6v1 tetap bukti terpisah. Tag tetap build commit; Latest tetap7.24.4,
rilis/tag lama89aset tidak berubah. [Bukti durable](evidence/new-v2-x86-publication-2026-10-06.json)
dan HANDOFF §28 memuat detail termasuk cooldown awal unresolved dan limits.

Paragraf berikut adalah checkpoint sebelum publikasi scoped NEW v2, bukan status
publikasi terkini.

ISO/IMG lokal sudah lolos gate lab x86 BIOS/IDE, tetapi **belum ada push atau
rilis NEW v1**, dan belum ada klaim semua arsitektur/hardware selesai. Permintaan
publikasi setelah ARM/bare-metal/semua berfungsi belum terpenuhi oleh uji x86
virtual ini. Non-x86 tetap fail-closed; native SFP tidak dimodifikasi karena
belum ada bukti NIC/modul/jalur DOM aktual. Tidak ada bukti SFP fisik, hotplug,
akurasi DOM atau redaman link pemilik. NetInstall, upgrades, networking dan
format lain belum mendapat gate runtime baru. Hasil source, review, evidence
installer dan status publikasi dicatat pada HANDOFF terbaru. Rilis lama/tag
serta dist lama tidak diganti; artefak baru tetap lokal dan berlabel lab.
