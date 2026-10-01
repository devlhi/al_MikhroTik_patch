# Ali Patch Code — panel lisensi lab lokal

Panel bahasa Indonesia untuk memilih **CHR System ID** atau **RouterOS Software ID**, menempel ID, membuat lisensi custom, lalu menyalin atau mengunduh hasil `.txt`.

**Bukan lisensi resmi MikroTik.** Hasil membutuhkan firmware lab dengan public key lisensi yang cocok. Pemeriksaan signature oleh server hanya memverifikasi ID, bentuk payload, dan kecocokan kunci; bukan bukti lisensi diterima perangkat atau firmware RouterOS **7.23.3** berhasil boot.

## Menjalankan

Dari root repo, siapkan Python 3.10 atau lebih baru:

```sh
python3 -m venv venv
venv/bin/python -m pip install -r requirements-license.txt
venv/bin/python -B scripts/license_server.py --port 12760
```

Pada Mac ini, bila lingkungan Hermes menambahkan `PYTHONPATH` milik interpreter lain, gunakan `env -u PYTHONPATH` di depan perintah Python.

Buka **http://127.0.0.1:12760/** di browser Mac yang menjalankan server. Hentikan dengan **Ctrl+C**. Tidak ada deploy, tunnel, atau akses dari perangkat lain. Server ini bukan daemon otomatis; jalankan kembali setelah terminal/server berhenti.

Untuk penggunaan berikutnya cukup perintah terakhir; tidak perlu membuat venv atau menginstal ulang paket.

## Cara memakai

1. Buka **System → License** atau jalankan `/system license print` di perangkat lab.
2. Pilih **CHR System ID** untuk ID CHR sepanjang 11 karakter; kapitalisasi harus persis sama. Untuk Software ID format `XXXX-XXXX`, pilih **RouterOS Software ID**; huruf besar dan angka, tanpa huruf `O`.
3. Tempel ID lalu klik **Buat lisensi**.
4. Hasil hanya muncul setelah signature dan ID diverifikasi server. Klik **Salin lisensi** atau **Unduh .txt**.
5. Mengganti ID/jenis atau membersihkan formulir menghapus hasil sebelumnya. Jika sesi kedaluwarsa, klik **Coba koneksi lagi**.

Tidak ada perubahan atau pemasangan lisensi otomatis ke router.

## Sumber kunci

Urutan prioritas konfigurasi:

1. `--private-key-file PATH` — eksplisit, berkas hilang tidak beralih ke sumber lain.
2. Environment `ALI_LICENSE_PRIVATE_KEY`.
3. Berkas `.ali_license_private_key` di root repo (sudah masuk `.gitignore`; atur izin `chmod 600`).
4. Pasangan `CUSTOM_LICENSE_PRIVATE_KEY` / `CUSTOM_LICENSE_PUBLIC_KEY` yang sudah ada di `.github/workflows/patch7.yml`.

Default ke workflow dipilih untuk lab ini. Server membaca YAML secara lokal, mengecek pasangan kunci, dan hanya mencetak fingerprint public key — tidak mencetak nilai private key. Jika memakai berkas sendiri, isinya 64 karakter heksadesimal (32 byte). Tidak ada input private key di browser dan tidak ada opsi nilai private key di command line.

**Kunci contoh yang sudah ada di repo publik tidak rahasia.** Jangan dipakai sebagai secret produksi. Mengganti kunci lisensi membutuhkan public key yang sesuai pada firmware; jangan mengganti salah satunya saja. Override berkas/environment tidak otomatis mengecek firmware yang terpasang.

## Batas keamanan

- Bind IPv4 loopback saja; `--bind 0.0.0.0` ditolak. Jangan pasang reverse proxy atau tunnel untuk mengekspos server.
- Host/Origin diperiksa pada API; token sesi CSRF, batas payload, jeda permintaan, CSP, dan `no-store` digunakan.
- Halaman tidak memakai CDN, font eksternal, analytics, atau penyimpanan ID/hasil di localStorage. Clipboard dan file hasil unduhan hanya ditulis saat tombolnya diklik.
- Server tidak menyimpan riwayat ID/lisensi atau mencetak access log. File statis yang boleh dibaca hanya `index.html`, `app.css`, dan `app.js`.
- Proteksi browser bukan autentikasi terhadap program lokal: proses lokal yang dapat mengakses repo/server masih bisa memakai API. Jalankan hanya pada Mac/lab tepercaya.
- `http.server` digunakan untuk konsol lokal, bukan server internet yang telah di-hardening.

## Verifikasi

```sh
venv/bin/python -B -m unittest discover -s tests -v
node --check web/license/app.js
```

Tes Python lisensi menggunakan keypair sementara; tes frontend memakai harness DOM/transport offline, bukan data firmware. Node dibutuhkan untuk menjalankan tes perilaku frontend (tanpa Node bagian itu dilewati). Browser nyata tetap diperlukan untuk menguji clipboard, unduhan, dan tata letak.

## Troubleshooting

- `No module named 'yaml'`: gunakan interpreter venv yang sama saat install dan menjalankan server.
- Port sudah dipakai: hentikan instance lama atau pilih `--port 12761` dan buka port tersebut.
- HTTP 403: buka alamat localhost yang benar, jangan lewat proxy, lalu hubungkan ulang sesi.
- HTTP 429: tunggu sebentar sebelum klik lagi; token baru tidak menghilangkan jeda.
- Format ID ditolak: cek jenis ID dan salin ulang persis; ID CHR 11 karakter juga harus memenuhi batas angka 64-bit backend.
- Kunci workflow tidak cocok: server menolak start; periksa konfigurasi keypair tanpa menampilkan nilainya di chat/log.
