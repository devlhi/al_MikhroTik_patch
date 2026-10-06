# BCM57800 / RouterOS x86 — referensi dan kelayakan modifikasi NPK

## Kesimpulan

Driver Linux bnx2x menyediakan jalur EEPROM SFP. Namun belum ada bukti bahwa
mengganti driver dalam NPK akan memunculkan identitas dan DOM pada RouterOS x86
pemilik. Prioritas adalah menguji batas driver–userland, bukan mengganti driver
atau mengubah nama port tanpa diagnosis. Penelitian ini tidak menghasilkan patch
firmware, build, akses perangkat, atau bukti runtime baru.

Acuan repo: `4d9ae590b43fc93c1a6407b7a9fdc4a6b7eeaf8f`. Main/live sama saat
preflight; perubahan HANDOFF yang belum commit dipertahankan. Riset merujuk pada
RouterOS 7.24.4 dan upstream Linux v5.6; keduanya tidak diasumsikan identik.

## Bukti perangkat yang tersedia

- Pemilik mengirim output ether3: link-ok, 1Gbps, full-duplex yes,
  supported 1G-baseT-full; tidak ada field identitas SFP atau sensor optik.
- Pemilik menyebut ether3 sebagai port SFP. OCR gambar sebelumnya membaca
  Broadcom NetXtreme II BCM57800; pemetaan interface ke fungsi PCI, board OEM,
  modul, PF/VF, dan bare-metal/VM belum dikonfirmasi.
- Ini bukan bukti port tidak berjalan. Link aktif juga bukan bukti sensor ada
  atau jalur DOM sudah tersedia. Nama ether tidak membedakan media fisik.

## Referensi primer yang diperiksa

| Referensi | Temuan yang relevan |
|---|---|
| [MikroTik Ethernet](https://help.mikrotik.com/docs/spaces/ROS/pages/8323191/Ethernet) | Monitor mendokumentasikan vendor/part-number, suhu, bias, TX/RX power; keluaran bergantung interface/modul. Tidak ditemukan jaminan BCM57800 x86 DOM dalam halaman yang diperiksa. |
| [MikroTik kompatibilitas kabel/modul](https://help.mikrotik.com/docs/spaces/ROS/pages/220233794/MikroTik+wired+interface+compatibility) | EEPROM/checksum dan kompatibilitas modul memengaruhi identifikasi/diagnostik. Bukan pembenaran melewati validasi. |
| [MikroTik Packages](https://help.mikrotik.com/docs/spaces/ROS/pages/40992872/Packages) | NPK adalah jalur paket vendor, bukan SDK ekstensi pihak ketiga yang didukung. |
| [Linux v5.6 bnx2x_ethtool.c](https://github.com/torvalds/linux/blob/v5.6/drivers/net/ethernet/broadcom/bnx2x/bnx2x_ethtool.c) | get_module_info/get_module_eeprom, power gate, pilihan SFF, PF/VF. |
| [Linux v5.6 bnx2x_link.c](https://github.com/torvalds/linux/blob/v5.6/drivers/net/ethernet/broadcom/bnx2x/bnx2x_link.c) | Pembacaan PHY/I2C, A0/A2, retry dan power-cycle modul. |
| [Linux v5.6 bnx2x_cmn.c](https://github.com/torvalds/linux/blob/v5.6/drivers/net/ethernet/broadcom/bnx2x/bnx2x_cmn.c) | Pemilihan PHY melalui bnx2x_get_cur_phy_idx. |
| [Linux v5.6 bnx2x_main.c](https://github.com/torvalds/linux/blob/v5.6/drivers/net/ethernet/broadcom/bnx2x/bnx2x_main.c) | Device table, firmware loading dan konfigurasi NIC. |
| [Linux v5.6 pci_ids.h](https://github.com/torvalds/linux/blob/v5.6/include/linux/pci_ids.h) | BCM57800 14e4:168a, Multi Function 14e4:16a5, Virtual Function 14e4:16a9. |
| [ethtool v5.6 ethtool.c](https://kernel.googlesource.com/pub/scm/network/ethtool/ethtool/+/refs/tags/v5.6/ethtool.c) dan [sfpdiag.c](https://kernel.googlesource.com/pub/scm/network/ethtool/ethtool/+/refs/tags/v5.6/sfpdiag.c) | Query module-info/EEPROM dan decoding sensor/kalibrasi, terpisah dari driver. |
| [Linux driver interface](https://docs.kernel.org/process/stable-api-nonsense.html) dan [external modules](https://docs.kernel.org/kbuild/modules.html) | Tidak ada ABI kernel internal stabil; module build membutuhkan kernel/build config dan simbol yang cocok. |
| [MikroTik legal/GPL](https://mikrotik.com/software/legal), [tautan sumber dari forum vendor](https://forum.mikrotik.com/t/anotheros-instead-than-routeros/156113), [arsip GPL v7](https://box.mikrotik.com/d/81912835977544a291c9/) | Source GPL berbeda dari komponen RouterOS proprietary; hak modifikasi/distribusi harus diperhatikan. Listing arsip linux-5.6.3.tgz dan patch.gz bertanggal 2022 bukan bukti build inputs exact 7.24.4 telah tersedia. |

Linux tag v5.6 menunjuk commit `7111951b8d4973bda27ff663f2cf18b663d15b48`;
ethtool v5.6 adalah proyek/tag terpisah dengan commit
`ce6e87d8ee899402d7f9dad9b9e25e2e943c71ae`. Source publik diambil via HTTPS,
bukan eksekusi driver. Kegagalan WebFetch diatasi dengan fetch HTTPS in-memory;
product brief Broadcom HTTP403 tidak dijadikan bukti. Referensi komunitas tentang
BCM57800 passthrough/traffic tidak dipakai sebagai bukti DOM.

## Jalur upstream yang konkret

1. `bnx2x_is_nvm_accessible` (ethtool.c sekitar 1471–1485): pemeriksaan akses
   power-management. Tanpa status PM yang bisa dibaca, interface-running menjadi
   fallback; bila PM terbaca, perangkat harus D0. Bukan syarat carrier-up umum.
2. `bnx2x_get_module_info` (sekitar 1574–1623): membaca A0 byte92/94 untuk
   diagnostic type dan SFF-8472 compliance. Tanpa DDM/compliance atau jika perlu
   address-swap, mengekspos SFF-8079 256 byte; lainnya SFF-8472 512 byte.
   Identitas dapat tersedia tanpa diagnostik.
3. `bnx2x_get_module_eeprom` (sekitar 1509–1572): offset 0–255 ke A0,
   256–511 ke A2, dengan PHY lock. Reader errors dapat dipetakan menjadi EINVAL,
   sehingga error itu bukan diagnosis tunggal.
4. `bnx2x_read_sfp_module_eeprom` (link.c sekitar 8070–8109): pembaca berbeda
   untuk BCM8726, BCM8727/8722, dan DIRECT/Warpcore. Tipe lain ditolak; pembacaan
   dipecah dalam chunk 16 byte.
5. PF ethtool ops memuat kedua callback; VF ops tidak (ethtool.c sekitar
   3700–3733). Link pada VF tidak memberikan akses EEPROM physical port.
6. Mask SFI/fiber juga memakai SUPPORTED_1000baseT_Full (link.c sekitar
   12228–12255). Output 1G-baseT-full sendirian bukan bukti soket RJ45.
7. `ethtool -m` melakukan query info lalu EEPROM dan decoding; temperatur,
   voltage, bias, TX/RX memerlukan data valid serta kalibrasi yang benar.

**Peringatan operasi:** Warpcore read retry (link.c sekitar 7934–7963) dapat
mematikan/menyalakan daya modul setelah kegagalan baca berulang. Karena itu
`ethtool -m` tidak dijamin tanpa gangguan walaupun tujuannya membaca. Ini temuan
upstream, belum diverifikasi identik pada biner RouterOS. Jangan polling atau
mencoba di link produksi. Jangan ubah NIC firmware, EEPROM atau PHY state sebagai
langkah diagnosis spekulatif.

## Hubungan dengan biner RouterOS yang sudah diperiksa

[Temuan statis sebelumnya](sfp-driver-findings.md) mendokumentasikan bnx2x
1.713.36-0 dan callback EEPROM dalam modul vendor, kernel 5.6.3-64. Versi string
upstream yang sama tidak membuktikan source/ABI identik. Driver dan firmware ada
bukan bukti bahwa callback berhasil pada board pemilik.

Pencarian literal baru di pohon vendor cache menemukan nama field sfp-module-present,
sfp-rx-power, sfp-tx-power, sfp-temperature, sfp-vendor-name dan
sfp-vendor-part-number di nova/lib/console/1073741824.mem. nova/bin/net mempunyai
string sfp/qsfp/initQsfp dan prefix penamaan port. Ini hanya string/schema,
bukan bukti jalur runtime atau lokasi instruksi yang aman dipatch.

Pencarian byte 0x8946 yang luas juga menemukan banyak file nonkode/data; hasil
tersebut **bukan bukti callsite ioctl**, tidak dipakai untuk menentukan patch.
Analisis sebelumnya membuktikan penggunaan SIOCETHTOOL pada beberapa callsite net,
tetapi alur lengkap GMODULEINFO/GMODULEEEPROM menuju field monitor belum dibuktikan.
Negatif pencarian literal tidak membuktikan fitur tidak ada: nilai dapat dibentuk
secara dinamis atau dipanggil melalui wrapper. Parameter loader/moduler juga
belum terlacak; jangan menganggap modprobe.conf atau flag boot pasti diteruskan.

## Apa yang harus berubah bila modifikasi NPK memang diperlukan

NPK hanya kontainer; repack/signature bukan implementasi pembaca SFP.

| Hasil pengujian terkontrol | Arah perubahan yang masuk akal |
|---|---|
| Exact NIC/port/modul bisa memberi identitas dan DOM di Linux, tetapi RouterOS tidak | Investigasi backend net: pemilihan interface/capability, query driver, parsing SFF, publikasi property monitor. Driver baru belum tentu perlu. |
| EEPROM hanya memberi identitas | Periksa dukungan DDM modul, compliance/address-swap, pembaca A2 dan decoder; jangan membuat nilai sensor palsu. |
| Driver/PHY EEPROM gagal pada Linux juga | Diagnosis OEM/NVM/PHY/modul dan PF/VF; belum ada dasar mengubah GUI/CLI. |
| Interface guest adalah VF atau NIC virtual | Dukungan physical ownership/passthrough berbeda; rename atau patch field tidak memberi akses I2C host. |

Implementasi native yang benar harus memetakan interface ke NIC/port yang tepat,
melakukan query yang didukung, menjaga batas EEPROM/checksum, decoding dan
kalibrasi SFF-8472, lalu mempublikasikan property native dengan status unavailable
bila tak ada data. Hotplug, multiple ports, no-module, malformed EEPROM, timeout
serta link continuity harus diuji. Laporan eksternal yang membaca sensor Linux
adalah alternatif monitoring, **bukan** native RouterOS/Winbox parity.

Jika bnx2x.ko benar-benar perlu diganti, harus ada build inputs kompatibel kernel,
config dan ABI; vermagic saja tidak cukup. Module.symvers diperlukan sesuai
konfigurasi versioning. Menyalin .ko Ubuntu atau memaksa load bukan solusi aman.
Source proprietary net tidak diperoleh dari arsip GPL; penelitian/implementasi
harus mematuhi hak dan ketentuan lisensi yang berlaku.

## Bukti pembeda yang masih diperlukan

Dari RouterOS: resource/PCI inventory dan detail ether3 tersanitasi, model OEM
kartu, port mapping, PF/VF/bare-metal/VM, part number modul dan datasheet DOM.
Tidak meminta Software ID, lisensi, MAC, serial atau dump konfigurasi penuh.

Pada target lab Linux yang sudah tersedia/diizinkan dengan NIC/port/modul sama,
inventory seperti ethtool -i, lspci -nnk, kernel version dan physfn dapat menentukan
binding. Uji ethtool -m hanya saat gangguan link diizinkan pada target nonproduksi;
rekam ringkasan/error tersanitasi, jangan dump EEPROM/serial mentah. Linux sukses
hanya membuktikan jalur Linux tersebut, bukan langsung bug tertentu di RouterOS.
Tidak ada akses target atau pengujian tersebut dilakukan dalam sesi riset ini.

## Keputusan sesi

Tidak ada patch NPK/driver/firmware, bypass guard, forced speed, reboot, commit,
push atau rilis baru. Penelitian selesai sebagai penilaian dan referensi;
kesiapan patch masih bergantung bukti perangkat dan dataflow userland. Suite
kode tidak diulang karena perubahan dokumentasi saja; hasil riset tidak boleh
menggantikan bukti runtime/SFP hardware.
