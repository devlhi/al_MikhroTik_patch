# Spike 001 — jalur diagnostik power SFP x86

## Pertanyaan dan gerbang

| Pertanyaan | Eksperimen/bukti | Status |
|---|---|---|
| Apakah format teks dapat diparsing tanpa membuat angka power saat data kosong? | CLI offline dan fixture sintetis, validasi unit/duplikat/batas input | Tervalidasi pada fixture yang diuji |
| Apakah Linux dapat mengakses DDM pada kandidat NIC tertentu? | Riset driver dan kemudian `ethtool -m` pada hardware yang sama | Pengujian hardware belum dilakukan |
| Apakah RouterOS x86 7.23.3 mengekspos power NIC itu? | Monitor langsung pada perangkat lab | Belum diuji |
| Apakah daemon tambahan dapat hidup di RouterOS dan diekspor ke UI? | Runtime/ABI/driver/lifecycle paket/boot/rollback | Belum dibuktikan; tidak membuat NPK sebelum gerbang ini |

## Artefak yang dapat dijalankan

Implementasi eksperimen ada di `scripts/sfp_diagnostics.py`, pengujian di
`tests/test_sfp_diagnostics.py`. Jalankan dari root repo:

```sh
python3 scripts/sfp_diagnostics.py --help
python3 scripts/sfp_diagnostics.py --format routeros --input routeros-monitor.txt
python3 scripts/sfp_diagnostics.py --format ethtool --input ethtool-module.txt
python3 -B -m unittest tests.test_sfp_diagnostics -v
```

Python 3.10+; file input wajib berasal dari snapshot satu port yang dikumpulkan
manual. Tidak ada networking, daemon, root request, shell execution, pembacaan
EEPROM langsung, atau modifikasi NPK dalam program ini. Penolakan input berarti
batas parser, bukan bukti hardware tidak didukung. Format raw/JSON/multilane
belum didukung. Panduan lengkap: [power SFP](../../docs/sfp-power.md).

## Bukti eksekusi lokal

- 41 unit/CLI tests SFP lulus, menggunakan fixture **sintetis** saja.
- Review delta memverifikasi 142 tests pada versi sebelum dua hardening terakhir.
  Regresi repo setelah hardening: 152 tests lulus; hitungan ini juga mencakup
  perubahan VPS yang sedang dikembangkan, bukan bukti instalasi VPS selesai.
- Tiga eksekusi CLI terpisah dengan file sintetis: RouterOS dengan power,
  Linux dengan power, RouterOS tanpa data; seluruh status sesuai harapan.
- Setelah review independen `deleg_d78cad1e` (passed, tanpa temuan
  keamanan/logika), lima saran non-blocking diterapkan: wajib `name` port
  RouterOS (input tanpa `name`/kosong ditolak), peringatan untuk sensor yang
  ada tapi tidak terbaca, penolakan SFP-DD/OSFP (SFP56 tetap diterima sebagai
  satu lane), `interface` bukan string kosong, dan `--interface` opsional
  dengan mismatch RouterOS ditolak. Tes batas regresi menambah 9 kasus.
- Review ulang independen atas delta tersebut juga passed tanpa temuan
  keamanan/logika; dua saran hardening diterapkan: label `--interface` kini
  menolak surrogate Unicode dan pemisah baris U+0085/U+2028/U+2029 (label
  dijamin UTF-8 valid, maksimum tetap 255 byte), dan identifier DSFP (dual
  lane) kini ditolak di kedua parser. Dua metode tes baru serta tambahan kasus
  CLI meliputi input yang ditolak dan label multibyte valid pada batas 255 byte.
- Tes membaca file memastikan byte input tidak berubah.
- Baseline awal gagal karena direktori sementara macOS berada di `/var`
  (symlink); tes release memang menolak ancestor symlink. Ulang dengan
  `TMPDIR=$HOME/.hermes/cache/scratch` lulus, tanpa melemahkan validator.

Ini tidak membuktikan sensor, akurasi optik, boot firmware atau instalasi paket.
Versi awal dan delta pertama telah lolos review independen. Hardening terakhir
(Unicode label dan DSFP) telah lolos regresi lokal, tetapi belum direview ulang
secara independen. Hasil review bukan bukti hardware.

## Verdict: PARTIAL

### Yang bekerja
- Interpretasi teks satu snapshot/lane dan pemisahan `null` dari `0 dBm`.
- Data RouterOS dan Linux diberi sumber berbeda; tidak mensertifikasi perangkat.
- Kegagalan input ditolak dengan error ringkas, bukan angka cadangan buatan.

### Yang belum bekerja / belum dijalankan
- Pembacaan sensor pada NIC Intel/Broadcom fisik: tidak ada perangkat uji.
- Akses driver/userland RouterOS, daemon, Winbox field, dan NPK: belum dibuat.
- Raw EEPROM, external calibration, QSFP/CMIS dan pemetaan lane: tidak dicoba.

### Temuan
- CLI yang hanya mengimpor fungsi sempat exit 0 tanpa output; tes subprocess
  memaksa laporan JSON nyata sehingga perilaku itu tidak dihitung sukses.
- Data yang tidak ada atau format tidak dikenal tidak boleh dikonversi ke nol.
- Kemampuan Linux tidak boleh dipromosikan menjadi dukungan RouterOS x86.

### Rekomendasi berikutnya

Mulai dengan **satu kartu + satu modul DDM yang tersedia**, catat model lengkap
serta firmware/PCI ID, dan bandingkan RouterOS dengan Linux. Kalau hanya host
Linux yang dapat membacanya, monitoring eksternal lebih masuk akal untuk diuji
lebih dulu daripada menjanjikan NPK yang belum terbukti. Jangan rilis klaim
“semua merek” atau memakai eksperimen ini sebagai fitur firmware produksi.
