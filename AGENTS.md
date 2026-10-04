# Panduan agent — Ali Patch Code

Panduan ini berlaku untuk seluruh repo. Untuk developer manusia, lihat juga
[CONTRIBUTING.md](CONTRIBUTING.md).

## Memori proyek wajib dibaca dan diperbarui

1. **Sebelum bekerja**, baca [docs/HANDOFF.md](docs/HANDOFF.md), kemudian periksa
   branch, HEAD, status working tree, serta perbedaan dengan remote. Jangan menimpa
   perubahan orang lain atau menganggap ringkasan percakapan sebagai status terbaru.
2. Gunakan HANDOFF sebagai **memori proyek bersama** untuk Hermes, agent lain, dan
   developer manusia. Ini bukan tempat menyimpan memori pribadi, kredensial, atau
   seluruh transkrip percakapan.
3. **Sebelum commit/push atau menyerahkan pekerjaan**, perbarui HANDOFF untuk setiap
   sesi yang menghasilkan perubahan, temuan, keputusan, atau status pengujian baru.
   Gunakan format pada bagian "Protokol pembaruan memori proyek" di dokumen itu.
   Sesi yang hanya membaca tanpa temuan baru tidak perlu membuat commit kosong.
4. Catat apa yang diubah, apa yang benar-benar diverifikasi, kendala yang tersisa,
   serta langkah berikutnya. Bedakan hasil tool, laporan pemilik, dan hipotesis.
   Catat tes yang gagal/di-skip/tidak dijalankan; jangan menyalin hasil lama sebagai
   tes baru. Cantumkan commit acuan yang sudah ada; jangan mengarang hash commit
   yang belum dibuat. Riwayat Git mencatat commit pembaruan HANDOFF itu sendiri.
5. Jika pekerjaan terhenti, tinggalkan status parsial dan titik lanjut yang jujur
   bila masih memungkinkan. Jangan menandai masalah selesai tanpa bukti.

## Batas kerja tetap

- Cabang kerja pemilik: `main`. Jangan membuat cabang lain atau force-push tanpa
  persetujuan. Commit/push/publikasi tetap mengikuti izin pemilik untuk tugas itu;
  instruksi memori ini bukan izin permanen untuk tindakan jarak jauh.
- Jangan menampilkan atau commit nilai kunci, token, password, output credential
  helper, atau log mentah yang belum disanitasi. Jangan membuat/mengganti keypair
  diam-diam. Kunci legacy bukan untuk produksi.
- Jangan memindahkan tag firmware yang sudah terbit atau mengganti aset rilis lama
  untuk menyamarkan build baru. Pertahankan hubungan tag, commit, dan aset.
- Jangan melewati guard cakupan supaya build tampak sukses. Baca kontrak
  [docs/patch-coverage.md](docs/patch-coverage.md) sebelum mengubah jalur terkait.
- Pisahkan bukti build/signature/cakupan, boot/login, dan aktivasi. Tes unit hijau
  bukan bukti firmware berjalan. Ini lab, bukan layanan lisensi resmi MikroTik.
- Simpan bukti penting yang sudah disanitasi secara tahan lama; folder scratch
  dapat hilang. Nyatakan jelas jika bukti hanya berupa laporan atau sudah tidak ada.

## Pengujian

Perintah setup, suite, prasyarat SquashFS/Node/Caddy, dan kondisi skip ada pada
bagian "Cara kerja cepat" di [docs/HANDOFF.md](docs/HANDOFF.md). Jalankan tes sesuai
cakupan perubahan dan catat hasil aktual. Untuk perubahan dokumentasi saja,
periksa diff, link, dan informasi sensitif; nyatakan jika suite tidak diulang.
