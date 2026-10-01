# Template laporan lab SFP — bukan hasil pengujian

Salin template ini untuk setiap kombinasi perangkat. Jangan isi kolom hasil
dengan contoh angka. Simpan serial, MAC, IP, kredensial dan license key secara
privat atau redaksi sebelum membagikan. Jangan lampirkan full export RouterOS.

## Identitas kombinasi

- Tanggal/jam + zona waktu:
- Penguji:
- Mesin/perangkat lab:
- RouterOS versi/build dan arsitektur:
- Image resmi/custom (ID commit dan hash artifact jika ada, tanpa kunci):
- Bare-metal / CHR virtual NIC / passthrough PF / SR-IOV VF:
- NIC vendor/model/OEM:
- PCI vendor:device + subsystem IDs:
- NIC firmware/NVM dan driver/version:
- Port/interface:
- Modul vendor + part number + revision (tanpa serial):
- Form factor, speed, wavelength, konektor, SM/MM/BiDi:
- Datasheet dan DOM/DDM yang dinyatakan:
- Peer dan kondisi link (tanpa alamat privat):

## Bukti terpisah

- Output `/system resource print` yang sudah disamarkan:
- Output `/system resource pci print detail` yang sudah disamarkan:
- Output **satu port** `/interface ethernet monitor <port> once`:
- Jika pembanding Linux: distro, kernel, `ethtool --version`, `ethtool -i`:
- Jika pembanding Linux: stdout `ethtool -m`, stderr dan exit code:
- Label `--interface` Linux, jika dipakai (diisi manual, bukan deteksi parser):
- JSON parser (bukan bukti mandiri hardware):
- Pembanding datasheet/alat ukur optik bila tersedia:

## Pengujian (isi hanya yang benar-benar dilakukan)

| Kasus | Dilakukan? | Hasil nyata dan timestamp |
|---|---|---|
| Modul terpasang, link up | Belum | |
| RX/TX, suhu, voltase, bias terbaca | Belum | |
| Link down/fiber dilepas pada lab | Belum | |
| Modul dilepas: nilai lama hilang | Belum | |
| Modul dipasang kembali: nilai segar | Belum | |
| Reboot perangkat cadangan | Belum | |
| Sampling ulang dan beban CPU | Belum | |
| Pembanding Linux pada kartu/modul sama | Belum | |
| Pembanding power meter | Belum | |

Jangan melepas fiber atau modul pada jalur produksi. Jangan melihat langsung
ke ujung fiber/transceiver. Gunakan prosedur keselamatan optik perangkat.

## Kesimpulan terbatas

- Status: **BELUM DIUJI** / TERBACA PADA KOMBINASI INI / TIDAK TERBACA / PARSIAL.
- Yang terbukti:
- Yang belum terbukti:
- Apakah nilai berasal dari perangkat nyata atau fixture sintetis:
- Anomali/error dan cara reproduksi:
- Lingkup klaim (jangan diperluas ke model/merek lain):
