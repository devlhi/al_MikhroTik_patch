# CHR x86 7.24.4 — enam format caption lokal

## Hasil yang tersedia

Folder lokal `dist/chr-x86-7.24.4-caption-all-formats` berisi enam arsip
`ali-patch-code-x86-chr-7.24.4-patched.<format>.zip`: `img`, `qcow2`, `vmdk`,
`vhd`, `vhdx`, dan `vdi`, disertai `manifest.json`, `SHA256SUMS`,
`RELEASE_NOTES.md`, serta `conversion-evidence.json`.

Semua dikonversi dari image caption yang mempertahankan enam baris ASCII
MikroTik dan menambahkan plain `Ali Media Patch` tepat di bawahnya. Perubahan
berada pada resource firmware, bukan `/system note`. Hash source VMDK:
`690506a2d0fba6ed3a6117873d2dec1a6ebcd4a6f4377dde5faea46819ec8d02`.

[Bukti konversi dan integritas](evidence/chr-six-format-caption-2026-10-05.json)
mencatat hash tiap arsip dan payload, perbandingan sektor guest keenam format
terhadap source, ukuran virtual 134217728 byte, serta preservasi artefak lama.
`qemu-img check` lulus untuk QCOW2, VMDK, VHDX dan VDI. Pemeriksaan tersebut
**tidak didukung** driver raw/VPC; IMG dan VHD tetap diperiksa header,
ZIP/CRC/hash, informasi image, dan kesetaraan isi guest.

## Validasi ulang

Dari root repo, gunakan Python dengan dependensi proyek:

```sh
python scripts/validate_chr_image.py \
  --directory dist/chr-x86-7.24.4-caption-all-formats \
  --version 7.24.4 \
  --manifest dist/chr-x86-7.24.4-caption-all-formats/manifest.json \
  --checksums dist/chr-x86-7.24.4-caption-all-formats/SHA256SUMS \
  --qemu-img qemu-img
```

Tanpa `--qemu-img`, pemeriksaan ZIP/CRC/hash/inventory/header tetap berjalan,
namun tidak ada pemeriksaan QEMU maupun perbandingan isi guest. Dengan QEMU,
validator mengekstrak salinan sementara dan memakai operasi read-only; tidak
menjalankan repair. QCOW2 external-data serta VMDK external/split extents atau
parent ditolak sebelum `check`/`compare`. Namun `qemu-img info` sendiri dapat
membuka referensi: validator ini bukan sandbox untuk image tidak tepercaya.
Perbandingan non-strict dapat menerima tambahan sektor nol
untuk geometri VHD; ini bukan perbandingan byte kontainer.

Workflow menerapkan policy caption hanya pada master CHR x86 versi 7.24.4,
sebelum konversi. Validasi keenam arsip menggantikan pemeriksaan satu VMDK.
Policy consumer yang dipin tidak diterapkan ke versi/arsitektur/produk lain.

## Batas hasil

- Ini **enam format CHR x86**, bukan seluruh 37 aset dalam profil `all`.
  ISO, install-image, NetInstall, standalone NPK, dan arsitektur lain tidak
  memperoleh bukti baru dari konversi ini. CHR IMG bukan install-image IMG.
- Source caption telah diuji boot/login dan tampilannya pada QEMU terisolasi
  ([bukti runtime](evidence/chr-7.24.4-ali-media-caption-runtime-2026-10-05.json)).
  Keenam kontainer belum diuji boot pada masing-masing hypervisor. Karena itu
  manifest tetap `boot_tested=false`.
- Aktivasi image caption tidak diuji. Bukti aktivasi image lama pada HANDOFF §17
  tidak otomatis menjadi bukti aktivasi build baru.
- Tidak ada modifikasi driver SFP. Lihat [temuan driver aktual](sfp-driver-findings.md)
  dan [template pengujian hardware](sfp-lab-report.md); keberadaan driver bukan
  jaminan link atau pembacaan daya optik pada setiap NIC/modul.
- Tidak ada commit, push, dispatch CI, atau publikasi GitHub baru pada tahap ini.
  Artefak dan tag lama tidak diganti.
