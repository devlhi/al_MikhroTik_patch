# Non-x86 7.24.4 — representasi anchor ditemukan, matcher belum dibuat

Acuan source: `bb010811bd1443334ed32b0d3168ef09b77bc111`. Investigasi statis
read-only pada enam NPK yang diunduh dari HTTPS vendor menemukan konstruksi
anchor publik yang dikonfigurasi pada **18/18** target `keyman`, `mode`, dan
`loader`. Ini menjelaskan kegagalan matcher literal/i386 sekarang; bukan
hasil patch, signing, boot, atau aktivasi non-x86.

[Bukti tersanitasi](evidence/non-x86-key-inspection-2026-10-05.json) menyimpan
provenance, hash paket/ELF, offset instruksi/store, bentuk instruksi tanpa nilai
kunci/immediate, rekonstruksi independen, sumber inspector, dan batas analisis.
SHA-256 evidence:
`5b6defb062aebc2113d69445aad0405a3d6d3070a4030eed0fb220c561418c18`.
Unduhan HTTPS dan hash lokal bukan verifikasi signature vendor.

| Paket | ELF target aktual | keyman/mode | loader |
|---|---|---|---|
| arm64 | ELF32 little-endian EM_ARM, bukan AArch64 | Buffer 32 byte dari literal dan aritmetika | Buffer 32 byte |
| arm | ELF32 little-endian EM_ARM | Buffer 32 byte | Sepuluh limb alternating 26/25 bit |
| mipsbe | ELF32 big-endian EM_MIPS | LUI + ADDIU/ORI dan delapan store | Sepuluh limb 26/25 bit |
| mmips | ELF32 little-endian EM_MIPS | LUI + ADDIU/ORI dan delapan store | Sepuluh limb 26/25 bit |
| smips | ELF32 big-endian EM_MIPS | Tiga target identik byte dengan mipsbe | Sepuluh limb 26/25 bit |
| ppc | ELF32 big-endian EM_PPC | LIS/ORI dan delapan store | Sepuluh limb 26/25 bit |

Total 13 buffer 32 byte dan lima buffer canonical ten-limb cocok dengan anchor,
diperiksa ulang dari field instruksi mentah. Rekonstruksi limb cocok integer
persis, bukan hanya modulo field. Keenam bentuk byte contiguous yang dicari
sebelumnya tidak ditemukan di target ini.

## Mengapa belum diterapkan

Matcher produksi membutuhkan lebih dari offset yang cocok:

- ELF dan batas decoder harus ketat; perlu membuktikan provenance register,
  layout store, relocation/alias/control flow, serta penolakan overlap.
- ADDIU MIPS memakai low-half signed dan carry, berbeda dari ORI. Store terakhir
  dapat berada pada delay slot JAL; naive immediate swap tidak cukup.
- Satu word ARM diturunkan secara aritmetika dari word lain. Literal pool dapat
  dipakai bersama; mengganti literal tanpa analisis referensi dapat merusak
  pemakaian lain atau menghasilkan target berbeda.
- Anchor loader tidak membuktikan aman diganti. Policy preservasi loader CHR x86
  tidak boleh digeneralisasi ke semua arsitektur. Runtime belum dianalisis penuh.
- ARM64 standalone NPK yang diinspeksi belum dibandingkan dengan NPK embedded
  pada ISO yang gagal di CI.

Rekomendasi investigasi berikut adalah matcher keyman/mode MIPS/PPC yang dipin,
dengan tes positif/negatif, simulasi rekonstruksi hasil, dan review independen
sebelum build. **Belum ada replacement yang disimulasikan atau diterapkan pada
sesi ini.** Guard cakupan tetap aktif; keenam arsitektur tidak diberi label build
sukses hanya karena anchor ditemukan. Tidak ada firmware execution, hardware
access, perubahan keypair, commit/push, atau rilis dari investigasi ini.
