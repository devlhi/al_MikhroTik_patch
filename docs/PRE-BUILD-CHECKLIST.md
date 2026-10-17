# CHECKLIST WAJIB — Sebelum Build & Rilis Firmware

> **ATURAN TIDAK BISA DILEWATI.** Setiap item harus ✅ sebelum build
> dinyatakan selesai. Jika ada satu ❌ atau ⚠️, build TIDAK BOLEH dirilis.
> Pelanggaran = crash di hardware pemilik (terjadi 4x: v6, v7, v7.2, v8.0).

---

## A. ANALISIS CODE PATH (sebelum menulis kode)

| # | Pertanyaan | Cara verifikasi | Wajib |
|---|---|---|---|
| A1 | Field struct yang akan ditulis — apakah itu DATA BYTE atau POINTER? | Disassembly semua pembaca field tsb | ✅ |
| A2 | Jika POINTER: apakah ada code path yang mendereference-nya sebagai objek C++? | Cari `mov reg,[field]` lalu `mov reg2,[reg+offset]` | ✅ |
| A3 | Jika POINTER: JANGAN tulis kecuali objek yang ditunjuk valid untuk SEMUA pembaca | Buat objek dummy atau verifikasi layout | ✅ |
| A4 | Field yang ditulis — apakah dibaca oleh kode di LUAR serializer? (monitor, driver, config) | Scan semua fungsi yang mengakses offset tsb | ✅ |
| A5 | Jika hook via `call`: apakah return address (4 byte) diperhitungkan di semua offset stack? | `esp_setelah_call = esp_sebelum - 4` | ✅ |

## B. AUDIT ASSEMBLY (setelah menulis kode, sebelum build)

| # | Pertanyaan | Cara verifikasi | Wajib |
|---|---|---|---|
| B1 | Semua register yang dipakai kode — apakah ada yang harus diawetkan tapi ditimpa? | Trace setiap register dari entry sampai exit | ✅ |
| B2 | Khusus EAX di serializer: apakah EAX masih berisi pointer wrapper saat label substitusi? | `mov esi,[eax]` di label 3 membutuhkan EAX wrapper | ✅ |
| B3 | Semua alamat absolut (SHADOW_*, SCRATCH_*) — apakah di dalam halaman yang terpetakan RWX? | 0x81ba000..0x81bafff | ✅ |
| B4 | Jmp/call rel32 — apakah dihitung dari posisi SETELAH instruksi (offset+5)? | `rel = target - (addr + len_instr)` | ✅ |
| B5 | `.org 0x200` — apakah fungsi kedua benar-benar di offset 0x200 dari awal blob? | `assert blob[0x200] == 0x60` | ✅ |
| B6 | Ukuran blob — apakah muat di area yang tersedia? | `assert len(blob) <= area_size` | ✅ |

## C. VERIFIKASI BUILD (setelah build, sebelum QEMU)

| # | Pertanyaan | Cara verifikasi | Wajib |
|---|---|---|---|
| C1 | `.text` diff vs net asli — apakah SEMUA byte yang berubah memang disengaja? | `diff` byte-per-byte, assert set terduga | ✅ |
| C2 | Phdr RWX — apakah hanya 1 byte di offset yang benar? | Verifikasi `p_flags == 7` untuk PT_LOAD halaman | ✅ |
| C3 | Hook halaman — apakah byte asli di-assert sebelum ditimpa? | `assert bytes == expected` | ✅ |
| C4 | Disassembly blob ter-assemble — apakah sesuai dengan yang ditulis di .S? | `objdump` dan bedah baris-per-baris | ✅ |
| C5 | Semua branch target — apakah melompat ke label yang benar? | Verifikasi setiap je/jne/jz target | ✅ |

## D. UJI QEMU (wajib sebelum rilis)

| # | Tes | Yang diperiksa | Wajib |
|---|---|---|---|
| D1 | Install + boot | Tidak hang, MBR valid, login berhasil | ✅ |
| D2 | Lisensi | nlevel 6, TANPA expires-in | ✅ |
| D3 | Identitas | Ali-Media-Patch muncul | ✅ |
| D4 | CLI dasar | `/interface print` tidak crash | ✅ |
| D5 | Jalur yang DIPATCH | Breakpoint/invokasi sintetis → perilaku benar | ✅ |
| D6 | Jalur yang TIDAK dipatch | Perilaku identik dengan asli (passthrough) | ✅ |
| D7 | **Jika ada field pointer yang ditulis**: GDB tulis nilai sama di QEMU → verifikasi tidak ada code path yang crash | Baca semua field yang terdampak | ✅ |

## E. ATURAN KHUSUS (pelajaran dari crash)

| # | Aturan | Asal |
|---|---|---|
| E1 | **JANGAN PERNAH** tulis pointer non-NULL ke field yang didereference oleh kode lain sebagai objek C++ | v8.0 crash (+0x1b8) |
| E2 | **JANGAN PERNAH** gunakan register yang berisi file descriptor (angka kecil) sebagai pointer | v7.2 crash (EBX=fd) |
| E3 | **JANGAN PERNAH** letakkan NOP di gerbang serializer yang melindungi interface non-SFP | v6 crash |
| E4 | **JANGAN PERNAH** letakkan kode di "code cave" .text tanpa verifikasi area benar-benar kosong | v7 crash |
| E5 | **JANGAN PERNAH** upload NPK berversi sama dengan yang terpasang — sistem akan menolak ("omitting") | v7.7-V77D rejected |
| E6 | **JANGAN PERNAH** ubah nova/etc/logo — loader menolak paket | v7.7 rejected |
| E7 | Satu-satunya cara update firmware = **NetInstall** | v7.7+ semua rejected |
| E8 | Upload NPK `system-7.23.1` berversi berbeda = ditolak lisensi ("license does not permit") | V77D log |
| E9 | Monitor via API `once=` = respons BEKU; hanya terminal monitor yang menyegarkan | observasi hardware |

## F. SEBELUM RILIS (checklist final)

| # | Item | Wajib |
|---|---|---|
| F1 | Semua item A-E di atas ✅ | ✅ |
| F2 | SHA256 semua artefak dicatat di HANDOFF | ✅ |
| F3 | Catatan rilis jujur (apa yang terverifikasi vs belum) | ✅ |
| F4 | HANDOFF diperbarui dengan hasil ACTUAL (bukan harapan) | ✅ |
| F5 | Git commit + push | ✅ |

---

## SEJARAH CRASH (supaya tidak diulang)

| Versi | Penyebab | Pelajaran |
|---|---|---|
| v6 | NOP di gerbang serializer → interface non-SFP baca field invalid | E3 |
| v7 | Kode di "code cave" .text yang ternyata berisi data | E4 |
| v7.2 | EBQ = fd socket (≈3) digunakan sebagai pointer → deref NULL page | E2 |
| v8.0 | +0x1b8 ditulis pointer EEPROM → kode lain baca sebagai objek C++ → garbage → crash | E1 |
