# Generator lisensi lab di Windows — Ali Patch Code

`generate-license.bat` membuka menu **CHR** atau **RouterOS**, menerima ID,
lalu menyimpan file `.txt` setelah signature, jenis payload, dan ID diperiksa.
Tidak menghubungi atau mengubah router.

**Ini bukan lisensi resmi MikroTik.** Pemeriksaan lokal tidak membuktikan
firmware dapat boot atau lisensi akan aktif setelah reboot. Gunakan hanya
untuk lab sendiri; jangan gunakan pada perangkat produksi.

## Setup sekali

1. Unduh seluruh repo lewat **Code → Download ZIP** di GitHub lalu ekstrak.
   Jangan mengunduh `.bat` saja: file Python, `toyecc/`, dan konfigurasi
   workflow juga dibutuhkan.
2. Pasang **Python 3.10 atau lebih baru** dari
   <https://www.python.org/downloads/windows/>. Aktifkan Python launcher `py`
   atau opsi **Add python.exe to PATH**.
3. Buka Command Prompt di folder repo hasil ekstraksi dan jalankan:

   ```bat
   py -3 -m venv venv
   venv\Scripts\python.exe -m pip install -r requirements-license.txt
   ```

   Jika `py` tidak tersedia tetapi `python --version` menunjukkan 3.10+,
   ganti `py -3` pada perintah pertama dengan `python`.

Tidak perlu administrator. Launcher tidak menginstal Python/paket atau
membuat keypair baru diam-diam. Instalasi PyYAML dibutuhkan jika konfigurasi
workflow dibaca/diperiksa, termasuk ketika memilih kunci override dalam repo
lengkap yang masih mempunyai `patch7.yml`.

## Klik dua kali

1. Buka `generate-license.bat` dari folder repo.
2. Pilih **1 = CHR** atau **2 = RouterOS**.
3. Salin ID dari perangkat lab:
   - **CHR:** System ID, tepat 11 karakter; huruf besar/kecil harus sama.
   - **RouterOS:** Software ID berformat `XXXX-XXXX`.
   Jangan mengganti ID atau membuat ID baru untuk mencoba melewati penolakan.
4. Pilih jalur output atau tekan Enter untuk default:
   - CHR: `ali-lab-license-chr.txt` di root repo.
   - RouterOS: `ali-lab-license-ros.txt` di root repo.
5. Jika muncul **Tersimpan**, buka file tersebut. License body tidak dicetak
   ke terminal. Tidak ada pemasangan otomatis ke router.

File yang sudah ada **selalu ditolak**, tidak ditimpa. Pilih nama baru atau
pindahkan file lama secara sadar sebelum mencoba lagi. File hasil default
masuk `.gitignore`; file pada jalur lain harus diamankan sendiri.

Launcher mengutamakan `venv\Scripts\python.exe`, kemudian `py -3`, lalu
`python`. Jika `venv` ada tetapi rusak/tidak memenuhi versi, perbaiki venv;
launcher tidak diam-diam memakai interpreter lain setelah CLI gagal.

## Pemakaian CLI / otomatisasi

Argumen **tidak diteruskan melalui `.bat`**. Untuk penggunaan non-interaktif,
panggil Python langsung:

```bat
venv\Scripts\python.exe -B scripts\license_cli.py --kind chr --id "pjLQ21gHzfI" --output "C:\Lab\hasil-chr.txt"
venv\Scripts\python.exe -B scripts\license_cli.py --kind ros --id "4JZ2-H049" --output "C:\Lab\hasil-ros.txt"
```

ID di atas hanya contoh publik; gunakan ID perangkat lab sendiri. CLI juga
menyediakan `--private-key-file PATH`, **bukan nilai private key di argumen**.
Gunakan `--help` untuk daftar opsi. Exit code 0 berarti file berhasil dibuat
setelah verifikasi lokal, bukan aktivasi firmware.

Untuk mengotomasi menu tanpa `pause`, tetapkan `ALI_LICENSE_NO_PAUSE=1` sebelum
menjalankan `.bat`; semua input menu tetap dibaca Python, bukan shell `cmd`.

## Konfigurasi kunci dan kecocokan firmware

Prioritas sumber private key:

1. `--private-key-file PATH` pada CLI Python; file eksplisit invalid/hilang
   **tidak** beralih ke sumber lain.
2. Environment `ALI_LICENSE_PRIVATE_KEY` yang telah diatur secara aman.
3. File `.ali_license_private_key` di root repo, sudah diabaikan Git.
4. Pasangan lab yang sudah ada di `.github/workflows/patch7.yml`.

Jika workflow menyediakan `CUSTOM_LICENSE_PUBLIC_KEY`, kunci terpilih harus
cocok dengan public key itu; mismatch ditolak sebelum menyimpan. Konfigurasi
YAML rusak, keypair workflow tidak lengkap saat dipakai sebagai sumber kunci,
atau PyYAML tidak tersedia ketika workflow perlu dibaca juga menghasilkan
error, bukan lisensi yang kelihatan berhasil.

Tidak ada keypair deployment baru dibuat dan nilai kunci tidak ditampilkan.
Kunci legacy dalam repo publik **bukan secret produksi**. Jangan mengganti
private/public key salah satunya saja. Kecocokan terhadap konfigurasi workflow
juga bukan bukti bahwa firmware yang sedang terpasang berasal dari build itu.

## Build GitHub yang mana?

Build baru memakai engine `daf390f` ada pada run
[Patch v7 `37207497763`](https://github.com/devlhi/al_MikhroTik_patch/actions/runs/37207497763).
Hanya **job x86 sukses**. Unduh artifact `ali-patch-code-x86-7.24.4` dari
bagian **Artifacts** (GitHub dapat meminta login). Artifact memuat ISO, CHR,
NPK, dan format disk lain; untuk VMware, kandidat file CHR adalah
`ali-patch-code-x86-chr-7.24.4-patched.vmdk.zip`, **bukan** `install-image`.

Manifest menyatakan `boot_tested: false`. ARM, ARM64, MIPSBE, MMIPS, SMIPS,
PPC diblokir guard cakupan; draft rilis gabungan tidak dibuat. Rilis/tag lama
bukan build baru ini. Artifact Actions sementara, tercatat kedaluwarsa
**18 Oktober 2026**. Metadata/checksum list sudah cocok; hash ulang isi biner
belum selesai akibat unduhan lokal gagal. Lihat
[evidence CI](evidence/ci-7.24.4-run37207497763.json) dan
[HANDOFF §13](HANDOFF.md).

**Belum ada bukti boot/login atau aktivasi lisensi pada artifact baru ini.**
Jangan menyamakan build sukses atau file lisensi tersimpan dengan aktivasi.

## Troubleshooting

- **Python tidak ditemukan:** pasang 3.10+ dan buka ulang terminal; periksa
  launcher `py`/PATH. Tidak perlu memberikan password atau key di chat.
- **PyYAML diperlukan:** jalankan perintah pip setup dengan interpreter yang
  sama, yaitu `venv\Scripts\python.exe`.
- **Kunci tidak cocok:** periksa konfigurasi/keypair secara lokal. Jangan
  membuat keypair baru atau menampilkan nilainya untuk sekadar membuat tes hijau.
- **ID/kunci invalid:** pastikan jenis ID dan kapitalisasi benar. Tidak ada
  file output valid yang dibuat pada kegagalan.
- **Output sudah ada / tidak dapat disimpan:** pilih file baru dalam folder
  yang dapat ditulis. Tidak ada overwrite otomatis.
- **Jendela menutup cepat:** jalankan `.bat` dari Command Prompt untuk membaca
  pesan. `pause` aktif secara default; EOF/Ctrl+C membatalkan pembuatan.

## Pengujian

Workflow `.github/workflows/windows-license.yml` menjalankan tes generator dan
**cmd.exe asli** pada Python 3.10 dan 3.14. Tes memakai keypair sintetis
sementara dalam salinan terisolasi; tidak memakai kunci deployment dan tidak
mengakses router. Pada macOS/Linux, tes native cmd.exe di-skip secara eksplisit.
Status run Windows harus diperiksa sendiri; hadirnya workflow bukan bukti run
sudah lulus.
