# VMDK lokal CHR x86 7.24.4 — hasil uji lab

Build lokal ini sudah diuji **langsung dengan VMDK final** di QEMU/TCG tanpa NIC:
boot dan login berhasil, level `free` berubah menjadi `p-unlimited`, lalu tetap
`p-unlimited` dengan System ID sama setelah dua reboot dan shutdown/cold restart.
Ini custom lab, **bukan lisensi resmi MikroTik**. Belum diuji langsung di VMware,
untuk upgrade, throughput, atau pemakaian jangka panjang.

## File yang digunakan

Folder lokal: `C:\laragon\www\mikpatch\dist\chr-x86-7.24.4-runtime-fix`.

- `chr-7.24.4-patched.vmdk`: disk final, belum diaktivasi.
- `ali-patch-code-x86-chr-7.24.4-patched.vmdk.zip`: arsip disk yang sama.
- `SHA256SUMS`: checksum disk dan ZIP.
- `build-evidence.json`: bukti build/integritas pada waktu build, sebelum uji runtime.
- `runtime-evidence.json`: hasil uji runtime final yang disanitasi.

SHA-256 VMDK:

```text
1e86aad1c10fe42294bac28be9597922579989ed210f3d5aed87eff83bd7fa08
```

SHA-256 ZIP:

```text
ad5e18d81144f17d948e67b26cf495ccc9703e6686c8437190ba95230d8c7dd5
```

Jangan menggunakan aset GitHub lama sebagai pengganti file lokal ini. Source
sudah dipush pada commit `140b94a`. Build CI all menghasilkan artifact
x86 tetapi enam arsitektur lain gagal guard cakupan. Firmware ini belum
dipublikasikan sebagai rilis GitHub; hasil runtime panduan ini khusus file lokal.

## Instalasi percobaan di VMware

1. Backup VM/disk lama. Buat **VM baru terpisah**, jangan menimpa instalasi lama.
2. Salin VMDK final untuk dipakai sebagai disk VM. Simpan file dasar/checksum asli.
   Jika menggunakan ZIP, ekstrak terlebih dahulu; ZIP berisi satu VMDK.
3. Gunakan disk yang sudah ada, bukan instalasi ulang lewat ISO. Pengujian yang
   berhasil memakai BIOS, controller IDE, RAM 512 MiB, dan 1 vCPU. Konfigurasi ini
   adalah acuan QEMU, **bukan bukti kompatibilitas VMware**. Mulai tanpa jaringan
   agar percobaan tidak terpapar sebelum password diamankan.
4. Boot, login lokal sebagai `admin` dengan password awal kosong. Amankan password
   sebelum menghubungkan jaringan; pengujian otomatis sendiri tidak mengubahnya.
5. Jalankan di terminal RouterOS:

   ```routeros
   /system license print
   ```

   Catat System ID **VM baru** secara privat. Jangan pilih `Generate New ID` selama
   pengujian dan jangan memakai kode milik VM lama: ID harus cocok.

## Membuat dan memasukkan kode lab

1. Jalankan `generate-license.bat` dari repo lokal ini. Pilih **1 / CHR**, masukkan
   System ID VM baru, lalu pilih nama output baru bila file default sudah ada.
   Generator menolak menimpa file yang sudah ada dan memverifikasi hasil lokal.
   Gunakan konfigurasi kunci yang sama dengan build; jangan mengganti keypair.
2. Buka file hasil secara lokal. Jangan mempublikasikan kode, ID, atau material kunci.
3. Di terminal RouterOS pada prompt utama, paste **seluruh blok lisensi multiline**,
   termasuk penanda awal/akhir. Setelah baris terakhir, tekan Enter sekali lagi
   untuk memberikan **baris kosong** yang mengakhiri input.
   Jalur yang diuji adalah paste global ini, **bukan** `/system license input`.
4. Reboot dengan `/system reboot`, konfirmasi `y`, login lagi, kemudian jalankan
   `/system license print`. Hasil yang diharapkan adalah `level: p-unlimited`
   dan System ID tetap sama.
5. Ulangi reboot dan pemeriksaan. Setelah itu gunakan `/system shutdown`, tunggu
   VM benar-benar mati, nyalakan lagi, lalu periksa level dan System ID.

Jangan upgrade dengan paket vendor selama pengujian ini: paket lain dapat mengganti
komponen lab. Jika VMware tetap `free` atau gagal boot, simpan hash file, konfigurasi
VM, dan gejala yang disanitasi; hasil QEMU tidak boleh dianggap hasil VMware.

## Batas dan provenance

Build menggunakan jalur produksi `patch_npk_file` dengan kebijakan sempit
`chr-x86-7.24.4`, tanpa monkeypatch atau bypass guard. Dua penggantian LICENSE
nyata dan lima penggantian signing diverifikasi; anchor LICENSE loader yang
terbukti memicu regresi dipertahankan dan tidak dihitung sebagai coverage.
Metadata SquashFS dibandingkan sebelum signing.

Perakitan disk lokal memakai partisi BIOS pembanding yang hash-nya dipin,
partisi sistem vendor pristine yang dipatch ulang, serta kernel hasil produksi
yang dibaca kembali. Ini **bukan eksekusi identik workflow GitHub** dan bukan
build enam format rilis. VMDK/ZIP final diverifikasi hash, CRC, signature custom,
dan kesetaraan raw/VMDK. Overlay teraktivasi tidak disertakan.

Bukti tahan lama: [build final](evidence/chr-7.24.4-final-build-2026-10-05.json)
dan [runtime final](evidence/chr-7.24.4-final-vmdk-runtime-2026-10-05.json).
