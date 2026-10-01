# Panel PRIVATE custom-lab di VPS

Panel ini menandatangani **lisensi custom-lab untuk firmware hasil patch Ali Patch Code**, bukan lisensi resmi MikroTik. Tidak ada janji firmware dapat boot, lisensi diterima pada firmware lain, atau kompatibilitas hardware. Private key harus cocok dengan public key yang sudah ditanam pada firmware lab.

## Status pengujian dan target

Integrasi paket telah diuji dengan checkout asli: allowlist mencakup dependency `sha256.py`; aplikasi disalin tanpa workflow/kunci lama, dijalankan lewat CLI menggunakan keypair sementara, dan menjawab probe domain `/api/health`. Pengujian lokal ini bukan bukti deployment Linux/systemd/SSL publik telah berhasil.

- Target utama: **Ubuntu 24.04 LTS**, systemd, Python 3.12 dan Caddy paket distro yang kompatibel.
- **Ubuntu 22.04 LTS**: jalur bersyarat. Jika apt menawarkan Caddy 2.4, installer menolak sebelum instal paket; gunakan repo resmi bertanda tangan Caddy untuk kandidat 2.6+ terlebih dahulu. Tidak pernah melewati autentikasi. Penambahan repo dilakukan administrator, bukan skrip ini.
- **Debian 12**: jalur bersyarat dengan Caddy 2.6.2, directive `basicauth`; Caddy 2.8+ memakai `basic_auth`.
- Tes unit, Bash syntax dan render dapat dijalankan tanpa root/network pada macOS. Caddy **2.8.4** lokal sudah menjalankan `validate`, `adapt` dan proxy HTTP **loopback**: seluruh path menolak request tanpa login (401), login fixture mencapai backend, Authorization/Forwarded terhapus, Host yang salah ditolak (421). Tes ini tidak menerbitkan sertifikat.
- Runtime Caddy **2.6.2 belum diverifikasi**; percobaan unduh binari berhenti karena timeout dan artefak parsial tidak dijalankan. Perubahan nama directive diuji renderer; setiap instalasi tetap wajib lulus `caddy validate` versi aktual.
- Instalasi apt/systemd, ACME, Linux kernel sandbox dan reboot pada ketiga distro **belum** diverifikasi dengan deployment VPS nyata. Jangan menyamakan tes renderer dengan sertifikat SSL berhasil. Tes opsional Caddy lokal: `CADDY_TEST_BINARY=/path/caddy python3 -m unittest discover -s tests -p test_vps_deploy.py -v` (listener sementara loopback saja).

## Prasyarat (VPS kosong/standalone saja)

1. Checkout lokal yang telah ditinjau; salin dengan SSH/SCP sebagai user biasa. Jangan jalankan skrip remote melalui pipeline shell. Installer tidak melakukan pembaruan Git otomatis dan tidak mengunduh kode aplikasi sebagai root.
2. **DNS A/AAAA** nama domain harus mengarah ke alamat publik VPS ini. Hapus AAAA salah jika IPv6 VPS tidak dapat dijangkau. Jangan gunakan CDN/proxy DNS saat instalasi. Cek juga CAA agar CA Caddy dapat menerbitkan sertifikat. Masukkan nama ASCII biasa, misalnya `panel.domain-anda.com`, bukan URL, IP, wildcard, port atau nama lokal.
3. TCP **80 dan 443** terbuka dari internet pada firewall VPS *dan* security group/provider. UDP 443 opsional untuk HTTP/3. Jangan membuka 12760: backend hanya `127.0.0.1:12760`.
4. Paket dasar `python3`, `iproute2` (`ss`), `coreutils` (`timeout`), apt dan systemd harus tersedia. Internet keluar diperlukan ke repository apt, PyPI (wheel PyYAML 6.0.3), DNS dan endpoint ACME. Installer memasang Caddy, venv dan CA certificates lewat apt; tidak melakukan upgrade seluruh OS.
5. Tidak ada app/service/user/group panel lama, Caddy (user/group), `/etc/caddy`, state Caddy atau `policy-rc.d` yang dikelola pihak lain. Port TCP 80/443/12760 dan UDP 443 harus kosong. Nginx/Apache/Caddy lain **tidak** dihentikan atau diambil alih. Untuk multi-site, gunakan integrasi manual oleh administrator; installer ini bukan alat migrasi.
6. Private key disediakan **lokal di VPS**, berupa satu baris 64 karakter hex, file biasa, `chmod 600` atau `400`; jangan isi di command line, chat, `.env`, terminal log atau repository. Simpan cadangan terenkripsi secara terpisah. Installer meminta **path** file, bukan isi kunci.

Installer sengaja **tidak** membuat kunci baru dan **tidak** mengambil kunci workflow yang sudah publik. Kunci LAB publik tidak rahasia: siapa pun yang memilikinya dapat menandatangani lisensi lab. Jika sengaja memakai pasangan LAB tersebut, administrator sendiri menyediakan file lokal setelah memahami risikonya; tidak ada fallback diam-diam. Mengganti signing key mengharuskan public key firmware cocok.

## Pemeriksaan tanpa perubahan

Dari root checkout, sebagai user biasa di Linux:

```bash
bash -n deploy/install-panel.sh
python3 -m unittest discover -s tests -p test_vps_deploy.py -v
bash deploy/install-panel.sh --check-config \
  --domain panel.domain-anda.com \
  --private-key-file /home/admin/keys/license.key
```

`--check-config` read-only: validasi domain/username, format/permission file kunci, allowlist sumber, DNS resolve publik dan konflik port/path. Tidak meminta password admin, memasang apt, membuat user/file, membuka port atau menerbitkan sertifikat. Domain dan path akan diminta bila belum diisi. Preflight bukan bukti bahwa semua A/AAAA benar-benar milik VPS; konfirmasi eksplisit diperlukan saat instalasi. Permission sistem tertentu dapat membutuhkan sudo untuk melihat seluruh state.

Untuk **render offline** di macOS atau Linux gunakan file **hash bcrypt**, bukan plaintext. Buat hash dengan Caddy dari prompt interaktif, tidak dengan opsi plaintext di argv:

```bash
umask 077
caddy hash-password --algorithm bcrypt > /path/aman/admin.bcrypt
bash deploy/install-panel.sh --render-only \
  --domain panel.domain-anda.com --admin-user admin \
  --password-hash-file /path/aman/admin.bcrypt \
  --caddy-version 2.8.4 --output-dir /path/aman/config-baru
```

`config-baru` harus belum ada. File Caddyfile/hash dibatasi permission karena hash password tetap sensitif. `--render-only` tidak memanggil Caddy, apt, systemd atau DNS; versi yang dipilih harus sama dengan target. Helper `deploy/render_panel_config.py render` menyediakan CLI yang sama untuk renderer. Pada VPS dengan Caddy yang sesuai, lakukan validasi nyata:

```bash
caddy validate --config /path/aman/config-baru/Caddyfile --adapter caddyfile
```

Validasi ini memeriksa syntax/provisioning, **bukan** penerbitan sertifikat. Jangan tampilkan Caddyfile atau hasil adapt JSON di chat/log publik karena memuat hash bcrypt.

## Instalasi interaktif

Tinjau semua kode dulu, lalu dari checkout lokal di VPS:

```bash
sudo bash deploy/install-panel.sh
```

Masukkan domain, username admin dan **path absolut private key**. Konfirmasi `INSTALL` berarti DNS benar-benar milik VPS ini dan VPS standalone. Password ditanyakan dua kali melalui `/dev/tty`, dengan echo dimatikan, panjang 16–72 **byte**, bukan jumlah karakter Unicode; input di luar batas ditolak sebelum hashing dan echo terminal dipulihkan. Installer menonaktifkan allexport (`set +a`) sebelum membaca password dan memakai PATH sistem `/usr/sbin:/usr/bin:/sbin:/bin` sejak awal, termasuk mode offline. Password hanya ada dalam memori shell yang tidak diekspor dan stdin `caddy hash-password`, kemudian di-`unset`; tidak ditulis sebagai plaintext, argumen program atau log. Jangan menjalankan dengan trace/debug shell atau perekam terminal yang menangkap input. Hash bcrypt disimpan dalam Caddyfile, permission root:Caddy 640.

App yang disalin ke `/opt/ali-patch-code` hanya:

- `scripts/license_server.py`, `scripts/license_util.py`, `license.py`, `mikro.py`, `sha256.py`;
- `toyecc/**/*.py` (tanpa symlink, cache/binary/hidden file);
- `web/license/index.html`, `app.css`, `app.js`;
- `requirements-license.txt`.

Tidak menyalin `.git`, README lama, workflow, `.env`, private key checkout atau seluruh folder web. App/venv milik root, tidak dapat ditulis user service. PyYAML 6.0.3 dipasang sebagai wheel secara eksplisit, bukan menjalankan arbitrary requirements checkout. File kunci dipasang di `/etc/ali-patch-code/license.key` root:ali-patch-code 640 dengan directory 750. Service `ali-patch-code` memakai user non-root/nologin, filesystem read-only dan akses jaringan dibatasi loopback. Sistem Linux tetap harus tepercaya: user lokal yang dapat terhubung loopback tidak melalui Caddy; jangan gunakan VPS multi-tenant dengan shell tidak tepercaya.

Caddy memakai automatic HTTPS, autentikasi **Basic Auth pada seluruh route aplikasi HTTPS**, batas body 4 KB, header 16 KB dan timeout. Browser menampilkan modal login Basic Auth, bukan form password frontend. HTTP port 80 hanya untuk ACME/redirect HTTPS; challenge sertifikat bukan endpoint aplikasi. Authorization dibuang sebelum diteruskan ke backend; Host disetel ke domain persis dan backend memeriksa Host/Origin HTTPS. X-Forwarded/Forwarded bukan bukti autentikasi. Tidak ada request/access log panel; output kedua service dibuang agar ID/URL pengguna tidak masuk jurnal. Konsekuensinya diagnosis runtime sengaja terbatas. Caddy admin API dimatikan: update memakai **restart**, bukan reload.

Sebelum service aktif, installer menjalankan `caddy validate` dan verifikasi unit systemd. Postinstall paket Caddy diblokir sementara dengan `policy-rc.d` agar default HTTP site tidak sempat terbuka tanpa autentikasi. Kemudian:

- probe backend `GET /api/health` dengan `Host: DOMAIN` harus 200 dan JSON `{"status":"ok"}`;
- probe domain publik melalui TLS tepercaya (hostname/cert verification ON) tanpa kredensial harus **401** dan challenge Basic Auth pada static/API/unknown path, termasuk POST generator;
- maksimum menunggu ACME kira-kira lima menit. Service `active` saja tidak dianggap bukti SSL.

Uji kembali dari jaringan **di luar VPS**, karena probe installer dilakukan dari VPS sendiri dan tidak membuktikan routing semua alamat DNS:

```bash
curl --noproxy '*' --max-time 15 -sS -o /dev/null -w '%{http_code}\n' https://panel.domain-anda.com/
# Harus 401, tanpa -k/--insecure.
curl --noproxy '*' --max-time 15 -sS -o /dev/null -w '%{http_code}\n' https://panel.domain-anda.com/api/health
# Harus 401 tanpa kredensial; tidak ada pengecualian health publik.
```

Login browser, pastikan panel terbuka dan operasi lab terverifikasi. Installer tidak menguji password login secara otomatis setelah menghapusnya dari memori. Jangan menaruh password pada `curl -u user:password`; jika pengujian manual diperlukan, gunakan prompt password curl dengan hanya username.

## Gagal instalasi / pemulihan

Installer hanya untuk instalasi pertama dan **menolak overwrite** app/key/site/unit/user/group lama. Snapshot root-only berada di `/var/backups/ali-patch-code-install.*`. Jika validasi atau probe kesehatan/TLS gagal, trap menghentikan/disable panel serta Caddy baru, mengembalikan Caddyfile paket dari `caddy.before`, memindahkan app/config/unit gagal ke backup, dan memuat ulang daftar unit systemd. Tidak memulihkan/mengambil alih Caddy lama karena dari awal ditolak. Detail validasi tersimpan root-only di backup; jangan kirim isi key/hash log secara publik.

Paket apt/user baru dan state sertifikat yang dibuat paket mungkin **tetap ada** setelah rollback. Tidak menghapus paket shared secara otomatis. Sebelum mencoba lagi, administrator meninjau backup, state systemd dan path yang tersisa lalu melakukan uninstall terkontrol di bawah. Kegagalan OS/disk, SIGKILL, mati listrik atau proses lain mengubah file selama transaksi dapat menghalangi rollback otomatis: gunakan snapshot VPS sebagai pengaman utama. Tidak pernah menyentuh SSH, firewall, security group, DHCP, DNS resolver atau konfigurasi network/netplan.

## Pembaruan manual (tidak ada auto-update)

1. Ambil checkout baru sebagai user biasa; tinjau diff, jalankan tes offline dan validasi Caddy versi target. Tidak menjalankan Git sebagai root.
2. Simpan snapshot VPS dan backup root-only app, `/etc/ali-patch-code`, Caddyfile/unit/drop-in. Catat domain, versi Caddy, permission dan status enabled/active.
3. Gunakan `render_panel_config.py copy-app --source CHECKOUT --destination NEW_DIR` untuk staging tree allowlist yang belum ada; buat venv baru pada path final/staging yang akan dipakai (venv pip script mengikat path). Jangan menyalin seluruh checkout atau key ke app.
4. Untuk perubahan config, render ke directory baru dan jalankan `caddy validate`; jangan menimpa file live dulu. Periksa unit dengan `systemd-analyze verify`.
5. Dalam maintenance window, stop panel, pindahkan tree/config yang lama ke backup, pasang staged app/venv root-owned dan config/key permission yang tepat. Jangan gunakan installer untuk update: ia akan menolak.
6. `sudo systemctl daemon-reload`; restart panel, probe health dengan Host domain, lalu restart Caddy (`admin off` mencegah reload). Jalankan probe TLS/401 dari luar dan login browser. Jika gagal, stop service dan pulihkan tree/config/unit/key lama dari snapshot sebelum restart. Jangan menyalin kunci ke log atau world-readable backup.

Tidak ada implementasi one-click update/recovery lintas instalasi. Re-run installer bukan update path dan tidak boleh disiasati dengan menghapus situs Caddy yang bukan milik panel.

## Rotasi password / rotasi signing key

- Password: buat bcrypt baru dengan prompt interaktif `caddy hash-password`, render config baru memakai username/domain/versi aktual, validasi, backup root-only, pasang Caddyfile root:caddy 640, `sudo systemctl restart caddy`, probe 401 dan login browser. Password browser lama mungkin tersimpan sampai browser/sesi ditutup.
- Signing key: jangan generate diam-diam atau berharap firmware lama menerima key baru. Koordinasikan pasangan key dan public key firmware lab, backup, pasang file key baru secara atomik root:ali-patch-code 640, restart panel, uji health dan satu operasi lab. Tidak ada janji boot/kompatibilitas; pertahankan rollback firmware/key yang selaras. Password Basic Auth dan signing key adalah dua hal berbeda.

## Uninstall tanpa merusak service lain

Langkah manual: pastikan file/service masih milik instalasi panel ini, tidak ada situs lain yang ditambahkan ke Caddy. Jika Caddy sekarang dipakai service lain, **jangan stop/disable atau hapus Caddy**; minta administrator memisahkan situs panel dahulu.

```bash
sudo systemctl disable --now ali-patch-code
# Hanya bila Caddy tetap khusus panel:
sudo systemctl disable --now caddy
```

Pindahkan `/opt/ali-patch-code`, `/etc/ali-patch-code`, unit `ali-patch-code.service` dan drop-in `caddy.service.d/ali-panel.conf` ke backup root-only. Pulihkan `/etc/caddy` dari snapshot `caddy.before` jika sesuai instalasi ini, atau simpan Caddyfile panel ke backup bila paket hendak dibuang. `sudo systemctl daemon-reload`. Jangan hapus source key milik administrator. Hapus user/group `ali-patch-code` hanya setelah memastikan tidak dipakai proses/data lain. Jangan menghapus user Caddy/state certificate/paket dependency bila dibutuhkan situs/service lain; `apt purge caddy` adalah keputusan administrator, bukan langkah otomatis. Backup berisi signing key dan hash sensitif: simpan terenkripsi atau hapus menurut kebijakan Anda. Firewall/SSH/network tidak dibuat installer sehingga tidak perlu dipulihkan olehnya.

Referensi resmi: [Caddy Basic Auth](https://caddyserver.com/docs/caddyfile/directives/basic_auth), [Automatic HTTPS](https://caddyserver.com/docs/automatic-https), [instalasi Caddy](https://caddyserver.com/docs/install).
