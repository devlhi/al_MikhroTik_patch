# Power SFP — Ali Patch Code (lab, belum dukungan firmware)

**Status: alat diagnostik offline tersedia. Belum ada NIC/SFP yang terverifikasi
pada RouterOS x86 7.24.4 di proyek ini. Belum ada add-on NPK atau perubahan
driver untuk power SFP.** Jangan mengiklankan “semua merek SFP didukung”.

## Apa yang sudah dan belum ada

| Bagian | Status |
|---|---|
| Membaca teks monitor RouterOS atau `ethtool -m` menjadi JSON | Tersedia, read-only, Python 3.10+ tanpa dependency tambahan |
| TX/RX dBm, suhu, voltase, arus bias, vendor/part number | Hanya ditampilkan jika ada dalam input dengan format dikenali |
| Nilai kosong/tidak dilaporkan | `null`, **bukan 0 dBm** dan bukan vonis modul rusak |
| Validasi vendor | Tidak ada whitelist merek pada parser; ini **bukan** membuka vendor lock NIC |
| Dukungan NIC Intel/Broadcom di RouterOS x86 | Belum dibuktikan; perlu pasangan NIC/firmware/modul/version tertentu |
| Integrasi Winbox, daemon RouterOS, NPK add-on | Belum dibuat; akses hardware dan runtime belum terbukti |
| CHR, arsitektur ARM/ARM64/MIPS/MMIPS/SMIPS/PPC | Belum uji hardware; matriks build tidak membuktikan sensor bekerja |

**Koreksi batas teknis:** patcher repo memang memodifikasi public key di kernel
serta file di squashfs (`patch.py:267–336`), bukan sekadar nama file. Namun belum
ada implementasi driver/monitor SFP dalam perubahan ini. Mengganti kunci tanda
tangan paket saja tidak membuktikan paket tambahan dapat dipasang, dijalankan,
atau menambah field Winbox.

## Bukti yang tersedia

Referensi CLI RouterOS mencantumkan `sfp-tx-power`, `sfp-rx-power`,
`sfp-temperature`, `sfp-supply-voltage`, dan `sfp-tx-bias-current`.[1]
Dokumentasi Ethernet mendefinisikan TX/RX sebagai daya optik dalam dBm.[2]
**Daftar field tersebut bukan daftar NIC x86 yang mendukungnya.** Sumber ini
berstatus dokumentasi umum/current, bukan hasil pengujian build 7.24.4 kita.

Linux `ethtool -m` membaca/mendekode EEPROM modul dan membaca diagnostik optik
**jika driver dan modul mendukungnya**; `ethtool -i` menampilkan informasi
driver.[4] Hasil Linux tidak membuktikan implementasi yang sama tersedia pada
RouterOS. Jangan mengasumsikan RouterOS memanggil program `ethtool` secara
internal hanya karena kernel dasarnya Linux.

MikroTik juga mencatat bahwa modul dengan checksum EEPROM buruk tidak
mengeluarkan informasi EEPROM apa pun ke ethernet monitor, sehingga monitor
DDM tidak bekerja untuk modul seperti itu.[2] Jadi `eeprom-checksum: bad`
adalah kemungkinan penyebab field DDM kosong selain modul tanpa DDM.

## Bukti akses Linux per keluarga driver (bukan bukti RouterOS)

Sumber kode Linux v6.12 untuk lima driver berikut menyediakan jalur pembacaan
EEPROM modul, termasuk pemeriksaan diagnostik pada jalur SFP.[8][9][10]
Implementasi Broadcom juga menyediakan pembacaan bagian A2.[11][12]
Ini bukti **implementasi di Linux**, bukan keberhasilan pada setiap kartu:
fungsi tetap dapat menolak akses sesuai tipe modul, firmware, dan kondisi NIC.
Tidak ada hasil eksekusi hardware di proyek ini, dan sumber tersebut tidak
membuktikan RouterOS x86 menyediakan jalur yang sama.

- ixgbe (Intel 82599/X520): keluarga controller ini tercantum pada dokumentasi
  driver Linux.[21] Ops table memasang `ixgbe_get_module_info` /
  `ixgbe_get_module_eeprom`, memeriksa compliance/DDM/addressing, dan hanya
  memilih layout SFF-8472 jika syaratnya terpenuhi.[8]
- i40e (Intel X710/XL710): kedua controller tercantum pada dokumentasi driver.[22]
  Tanpa capability `I40E_HW_CAP_AQ_PHY_ACCESS`, driver menolak baca dengan
  "Module EEPROM memory read not supported. Please update the NVM image."
  Modul SFF-8472 tanpa DDM diklasifikasikan sebagai layout 8079.[9]
- ice: tabel PCI mencakup `ICE_DEV_ID_E810C_SFP` dan varian E810.[16]
  Fungsi `ice_get_module_info`/`ice_get_module_eeprom` memakai
  `ice_aq_sff_eeprom`; hasil bergantung respons firmware dan tipe modul.[10]
- bnx2x: tabel model memuat BCM57810.[17] Fungsi modul memeriksa flag DDM dan
  membaca A0/A2; ketika guard `bnx2x_is_nvm_accessible` gagal, errornya
  "cannot access eeprom when the interface is down" (`-EAGAIN`).[11]
- bnxt_en: tabel model memuat BCM57414.[18] Jalur modul menolak
  `hwrm_spec_code < 0x10202` dan mengurangi panjang EEPROM ketika data
  diagnostik tidak tersedia; lolos syarat versi bukan jaminan semua modul.[12]
- mlx5 (opsional): tabel ops memuat `mlx5e_get_module_info` dan
  `mlx5e_get_module_eeprom`.[19] Audit fungsi/model belum sedalam lima driver
  tadi; jangan menyatakan semua generasi ConnectX sama.

Dalam sumber resmi MikroTik yang ditinjau untuk riset ini, belum ditemukan
matriks DDM per NIC x86; halaman yang dibaca mendokumentasikan field monitor,
bukan hasil per kartu.[1][2] Ini batas temuan riset, **bukan bukti tidak ada
NIC x86 yang bisa membaca DDM**.

Catatan historis saja: pada thread Intel 82599 tahun 2015, akun `krisjanis`
menulis "We have checked this Intel driver SFP vendor lock thing and so far
we haven’t managed to disable it. Using Intel 10G modules remains the only
option." Kutipan diperiksa pada **arsip 23 Juni 2026**, bukan fetch live.[20]
Jangan gunakan laporan lama tersebut sebagai aturan RouterOS 7.24.4, sebagai
bukti DDM, atau sebagai jaminan pembatasan vendor masih sama hari ini.

MikroTik menyatakan tidak membatasi vendor pada perangkat/modul yang dibahas
halaman kompatibilitasnya, tetapi juga tidak menjamin kompatibilitas semua
produsen; kesesuaian MSA merupakan syarat yang disebut.[6] Halaman itu membahas
perangkat MikroTik dan kompatibilitas transceiver/link, **bukan jaminan DDM
untuk seluruh kartu PCIe Intel/Broadcom**.

## Target NIC untuk investigasi (BUKAN daftar kompatibel)

Urutan ini adalah rencana lab, bukan rekomendasi membeli kartu sebelum diuji.
Pemetaan Linux telah diperiksa pada sumber di atas; semua hasil RouterOS masih
**belum diuji**. Catat model lengkap/OEM, PCI ID + subsystem, driver dan firmware
untuk setiap kartu; nama keluarga saja tidak cukup.

| Prioritas | Keluarga (driver Linux) | Syarat terdokumentasi di Linux | RouterOS x86 7.24.4 |
|---|---|---|---|
| 1 | Intel X520/82599 (ixgbe) | Callback + pemeriksaan DDM/addressing.[8][21] | Belum diuji |
| 1 | Broadcom BCM57810; kandidat kartu BCM57810S (bnx2x) | Guard akses NIC dan flag DDM.[11][17] | Belum diuji |
| 2 | Intel X710/XL710 (i40e) | Capability AQ PHY access dan tipe modul.[9][22] | Belum diuji |
| 2 | Broadcom BCM57414 (bnxt_en) | HWRM >= 0x10202 salah satu syarat, bukan jaminan.[12][18] | Belum diuji |
| 3 | Intel E810 varian SFP (ice) | Admin-queue SFF read.[10][16] | Belum diuji |
| 3 | Kandidat ConnectX dengan mlx5; generasi harus ditentukan | Callback ada; audit model/fungsi belum lengkap.[19] | Belum diuji |

Catatan BCM57810S: bukti tabel kernel memuat BCM57810, bukan pembuktian varian
kartu/OEM berlabel **S** secara terpisah.[17] Perlakukan tiap varian sebagai
kasus uji sendiri. Syarat Linux di tabel tidak otomatis berlaku pada RouterOS.

## Kebijakan lintas merek SFP

MikroTik, Intel, Broadcom, Cisco, FS, Finisar/Coherent, Ubiquiti, dan merek
lain diperlakukan **setara sebagai kandidat uji**, bukan diberi label cocok.
Nama vendor pada EEPROM hanyalah metadata, bukan sertifikat kompatibilitas.

Untuk setiap part number, periksa datasheet dan catat:
- SFP/SFP+/SFP28, jenis optik atau tembaga, speed yang sesuai port.
- Dukungan DOM/DDM, parameter dan ambang yang memang tersedia.
- Wavelength, SM/MM, konektor, pasangan BiDi jika digunakan.
- Coding/OEM/firmware dan syarat vendor pada NIC.
- Kondisi saat pengukuran: link up/down, modul dipasang/dilepas, power optik.

Target awal parser adalah **output decoded satu lane**. EEPROM raw, QSFP/CMIS,
array multichannel, format JSON ethtool, serta output `as-value` RouterOS tidak
merupakan format input yang didukung. QSFP/CMIS/SFP-DD/DSFP/OSFP pada ethtool
serta tipe QSFP/SFP-DD/DSFP/OSFP pada RouterOS ditolak eksplisit; jangan
merata-ratakan lane atau membuang label lane agar parser menerima data. SFP56
satu lane diperlakukan sebagai SFP biasa. CMIS tetap di luar cakupan parser ini,
termasuk jika modulnya satu lane; penolakan CMIS bukan pernyataan bahwa semua
modul CMIS multilane. Modul RJ45 atau DAC bukan bukti ketersediaan daya optik
TX/RX; jangan menciptakan angka dari link rate/counter lalu lintas.

## Jalur 1 — baca RouterOS terlebih dahulu

Jalankan **manual di perangkat lab**, bukan melalui script Python ini:

```routeros
/system resource print
/system resource pci print detail
/interface ethernet print
/interface ethernet monitor ether1 once
```

Ganti `ether1` dengan port sebenarnya. Simpan **satu snapshot satu port**
monitor ke `routeros-monitor.txt` pada komputer. Output `resource` dan `pci`
adalah lampiran terpisah, bukan input parser. Jangan kirim full export,
password, kunci license, token, atau nomor seri tanpa menyamarkannya.

Dari root repo:

```sh
python3 scripts/sfp_diagnostics.py --format routeros --input routeros-monitor.txt
```

Di Mac ini bisa memakai `env -u PYTHONPATH venv/bin/python -B` menggantikan
`python3`. Input stdin juga tersedia melalui `--input -`.

Input RouterOS **wajib** memuat baris `name: <port>` (satu port, tidak boleh
kosong); input tanpa `name` atau `name:` kosong ditolak. Duplikat field juga
ditolak. Pemeriksaan ini tidak dapat membuktikan asal potongan teks yang sudah
diedit atau dicampur: simpan output utuh satu perintah, satu port, satu waktu.
Gunakan `--interface <label>` untuk mencantumkan asal port pada laporan: pada
format RouterOS label harus cocok dengan `name` (mismatch ditolak); pada format
ethtool label hanya metadata manual, bukan hasil deteksi interface oleh parser.
Label kosong menjadi tidak diisi; label dibatasi 255 byte UTF-8 valid, tanpa
karakter kontrol atau pemisah baris Unicode U+2028/U+2029. Surrogate Unicode
ditolak. Label tidak memverifikasi perangkat atau asal data.

## Jalur 2 — pembanding Linux pada NIC/modul yang sama

Gunakan host lab Linux yang **sudah menguasai NIC fisik**, atau boot live Linux
saat maintenance disetujui. Jangan unbind driver, reboot router produksi,
atau memindahkan NIC dari VM otomatis. Proyek ini tidak melakukan tindakan itu.

```sh
uname -r
lspci -nnk
ethtool -i enp1s0
ethtool -m enp1s0
```

Ganti `enp1s0` dengan interface sebenarnya. Empat perintah tersebut untuk
informasi; `-m` berbeda dari `-E` (penulisan EEPROM) atau opsi pengubahan
konfigurasi. Jangan menggunakan `-E`, flashing, atau bypass vendor lock sebagai
langkah diagnostik. Kewenangan OS mungkin diperlukan untuk pembacaan; gunakan
akses lokal yang sah, jangan masukkan kredensial ke laporan.[4]

Simpan **stdout decoded** dari `LC_ALL=C ethtool -m enp1s0` ke
`ethtool-module.txt`. Simpan stderr/exit status secara terpisah jika gagal;
error izin atau “operation not supported” bukan angka power.

```sh
python3 scripts/sfp_diagnostics.py --format ethtool --input ethtool-module.txt --interface enp1s0
```

Alat tidak memanggil `ethtool`, SSH, API, jaringan, atau shell. Tidak ada
pengubahan firmware, konfigurasi port, EEPROM, kunci, atau file input.

## Cara membaca JSON

| Field/status | Makna |
|---|---|
| `power_dbm.tx`, `power_dbm.rx` | Angka **dari teks input**; `0.0` dBm adalah nilai, bukan “kosong” |
| `power-reported` | Dua arah terparse; bukan tanda power sehat atau hardware terverifikasi |
| `partial` | Hanya satu arah valid |
| `not-reported` | Tidak ada power valid dalam input; penyebab belum diketahui |
| `module-absent` | RouterOS melaporkan modul tidak ada; power yang mungkin usang diabaikan |
| `diagnostics-not-supported` | Teks ethtool menyatakan diagnostik tidak didukung |
| `interface` | `name` port RouterOS, atau label `--interface` untuk ethtool |
| `warnings` | Nilai hilang/format tidak dikenal/parsial |
| `hardware_verified: false` | Parser tidak mengamati atau mengautentikasi perangkat |
| `routeros_support_verified: false` | Membaca sebuah teks tidak mensertifikasi dukungan RouterOS |

Exit `0` berarti parsing/laporan berhasil, **bukan** seluruh sensor tersedia.
Exit `2` berarti argumen, file, format, atau input ditolak. Batas input 256 KiB,
UTF-8, satu snapshot. Duplikat field, karakter kontrol, dan input rusak ditolak;
`NaN`/`inf` tidak menjadi angka JSON. mW/dBm ethtool dicek konsistensinya dengan
toleransi pembulatan, tetapi itu bukan kalibrasi sensor. Sensor RouterOS yang
ada tetapi nilainya kosong/tidak valid dihilangkan dari `sensors` dan diberi
peringatan; sensor yang tidak ada dalam input tidak dibuat-buat.

Serial/MAC dan dump EEPROM tidak disertakan ke JSON melalui field asalnya.
Nama interface, vendor, part number tetap berasal dari input: **periksa dan
redaksi seluruh laporan sebelum membagikan**. Ini bukan alat penyamaran rahasia
umum. Pembacaan yang tidak tersedia tidak diubah menjadi `0`; nilai health
“baik/buruk” tidak ditentukan dari ambang universal. Bandingkan dengan datasheet
part number dan ambang modul, bukan angka rekomendasi generik.

## CHR dan passthrough

CHR ditujukan untuk VM; dokumentasinya mencantumkan NIC virtual seperti Virtio,
E1000, dan vmxnet3 pada hypervisor tertentu.[3] Keberadaan link guest tidak
membuktikan guest mengakses EEPROM modul fisik. Untuk lab CHR, uji monitoring
pada host yang menguasai NIC terlebih dahulu. Jika memakai PCI passthrough PF,
passthrough penuh, atau SR-IOV VF, catat mode tersebut sebagai **kasus terpisah**;
jangan menjanjikan DDM dari nama NIC virtual atau hasil PF pada Linux.

## Matriks keputusan

| Hasil nyata | Kesimpulan yang boleh dibuat | Lanjutan |
|---|---|---|
| RouterOS melaporkan TX/RX dan pengujian modul benar | Pasangan khusus itu memberi telemetri pada versi yang diuji | Catat hasil; cek hotplug dan pembanding |
| Linux bisa DDM, RouterOS tidak | Jalur Linux bisa membaca; RouterOS belum mengekspos pada pengujian ini | Pertimbangkan monitoring eksternal; jangan klaim patch NPK memperbaiki |
| Linux maupun RouterOS tidak bisa | Belum diketahui apakah modul, driver, firmware, akses, atau platform | Periksa error, datasheet dan pasangan known-good |
| Hanya nama/vendor modul terbaca | Identifikasi EEPROM berhasil, belum tentu diagnostik | Periksa dukungan DDM dan akses halaman diagnostik |
| Data menghilang setelah hotplug | Belum stabil untuk rilis | Uji ulang tanpa membawa nilai cache lama |

## Gerbang sebelum mencoba add-on NPK

Detail dan hasil prototipe: [spike SFP](../spikes/001-sfp-ddm/README.md).
**Belum ada daemon yang dijalankan pada RouterOS dan belum ada NPK SFP.**

1. Buktikan pembacaan satu pasangan NIC/modul pada perangkat uji.
2. Tentukan apakah jalur yang diizinkan adalah API RouterOS atau monitoring
   Linux eksternal. Jangan mengasumsikan syscall/ethtool Linux host tersedia
   dari userland RouterOS.
3. Jika add-on tetap diperlukan, buktikan ABI, toolchain, akses hardware,
   lifecycle paket/start-stop, hak minimum, dan ekspor telemetri yang sah.
4. Uji malformed EEPROM, hotplug, timeout, nilai hilang, penggunaan CPU, boot,
   pemulihan/rollback pada perangkat cadangan; jangan uji di jalur produksi.
5. Hanya setelah itu nilai apakah packaging NPK masuk akal. Menulis log dari
   daemon juga **bukan** menambahkan field native Winbox.

## Mencatat hasil lapangan

Isi [template laporan](sfp-lab-report.md). Satu laporan untuk satu kombinasi
NIC/OEM/firmware/module part number/OS version/mode virtualisasi. Status sebelum
ada bukti adalah **belum diuji**, bukan “supported”. Bukti tes sintetis parser
wajib dipisahkan dari output hardware asli.

## Sources

[1] https://manual.mikrotik.com/docs/cli-reference/interface/ethernet/monitor — RouterOS CLI reference: interface/ethernet/monitor
[2] https://help.mikrotik.com/docs/spaces/ROS/pages/8323191/Ethernet — MikroTik help: Ethernet (SFP support summary)
[3] https://help.mikrotik.com/docs/spaces/ROS/pages/18350234/Cloud+Hosted+Router+CHR — MikroTik help: Cloud Hosted Router CHR
[4] https://man7.org/linux/man-pages/man8/ethtool.8.html — ethtool(8) Linux man page
[6] https://manual.mikrotik.com/docs/wired-connections/mikrotik-wired-interface-compatibility — MikroTik wired interface compatibility
[8] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/intel/ixgbe/ixgbe_ethtool.c — Linux v6.12 ixgbe ethtool driver
[9] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/intel/i40e/i40e_ethtool.c — Linux v6.12 i40e ethtool driver
[10] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/intel/ice/ice_ethtool.c — Linux v6.12 ice ethtool driver
[11] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/broadcom/bnx2x/bnx2x_ethtool.c — Linux v6.12 bnx2x ethtool driver
[12] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/broadcom/bnxt/bnxt_ethtool.c — Linux v6.12 bnxt ethtool driver
[16] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/intel/ice/ice_main.c — Linux v6.12 ice-main
[17] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c — Linux v6.12 bnx2x-main
[18] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/broadcom/bnxt/bnxt.c — Linux v6.12 bnxt-main
[19] https://raw.githubusercontent.com/torvalds/linux/v6.12/drivers/net/ethernet/mellanox/mlx5/core/en_ethtool.c — Linux v6.12 mlx5-ethtool
[20] http://web.archive.org/web/20260623150652/https://forum.mikrotik.com/t/intel-82599es-10gig-card-and-sfp-modules-compatibility/93996 — Intel 82599 forum 2015 — archived 2026-06-23
[21] https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/networking/device_drivers/ethernet/intel/ixgbe.rst — Linux v6.12 ixgbe-doc
[22] https://raw.githubusercontent.com/torvalds/linux/v6.12/Documentation/networking/device_drivers/ethernet/intel/i40e.rst — Linux v6.12 i40e-doc
