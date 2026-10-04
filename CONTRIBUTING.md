# Melanjutkan pekerjaan — Ali Patch Code

[docs/HANDOFF.md](docs/HANDOFF.md) adalah **memori proyek bersama** yang ikut Git,
agar developer berikutnya dan agent (termasuk Hermes) tahu keadaan terakhir tanpa
bergantung pada ingatan atau chat pribadi.

## Sebelum mulai

1. Baca [HANDOFF](docs/HANDOFF.md) dan [aturan kerja repo](AGENTS.md).
2. Periksa HEAD, cabang, working tree, dan remote sebelum mengedit. Cabang kerja
   sesuai arahan pemilik adalah `main`; jangan menimpa pekerjaan yang belum di-commit.
3. Tentukan masalah yang dilanjutkan, bukti yang tersedia, dan tes/reproduksi yang
   diperlukan. Klaim di HANDOFF tetap punya batas bukti—laporan pemilik bukan
   reproduksi independen.

## Sebelum menyerahkan atau push

**Setiap sesi yang mengubah kode, dokumentasi, temuan, keputusan, atau status tes
wajib memperbarui `docs/HANDOFF.md`.** Gunakan format pada bagian "Protokol pembaruan
memori proyek". Sertakan perubahan, commit acuan, hasil tes aktual (termasuk gagal,
skip, dan yang tidak dijalankan), masalah terbuka, serta langkah berikutnya.
Jangan membuat commit kosong untuk sesi baca saja yang tidak menambah informasi.

- Perbarui status ringkas yang menjadi usang; jangan hapus batas bukti atau mengubah
  laporan kegagalan menjadi sukses tanpa hasil uji baru.
- Bedakan hasil eksekusi, laporan pengguna, dan hipotesis. Jangan mengklaim sudah
  push/rebuild/boot bila operasi itu belum diverifikasi.
- Jangan simpan kredensial, nilai kunci, firmware, atau log mentah yang belum
  disanitasi. Bukti penting jangan hanya ditaruh di scratch sementara.
- Jangan bypass guard cakupan, menggeser tag rilis terbit, mengganti aset lama,
  atau mengubah keypair diam-diam. Push/publikasi tetap perlu izin pemilik.

Setup dan perintah pengujian ada di [HANDOFF](docs/HANDOFF.md); tes kode tidak
membuktikan boot atau aktivasi lisensi. Ini repo lab, bukan layanan lisensi resmi.

Aturan dokumentasi ini adalah kewajiban kontributor, **belum gerbang otomatis
hook/CI**. Developer/agent yang tidak mematuhinya tidak bisa dijamin akan membuat
catatan; reviewer perlu memeriksa pembaruan HANDOFF saat menerima pekerjaan.
