#!/usr/bin/env bash
# Fresh standalone VPS only. Never run through a remote shell pipeline.
set +x
set +v
set +a
set -Eeuo pipefail
ulimit -c 0
IFS=$'\n\t'
# Trust system executables before any external call, including preflight/render.
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

restore_tty() {
    if [[ -n ${TTY_STATE:-} ]]; then
        stty "$TTY_STATE" </dev/tty || true
        unset TTY_STATE
    fi
}
fail() { restore_tty; printf 'Ditolak: %s\n' "$*" >&2; exit 1; }
usage() {
    printf '%s\n' \
      'PRIVATE custom-lab panel; bukan lisensi resmi MikroTik.' \
      'sudo bash deploy/install-panel.sh [--domain DOMAIN] [--admin-user USER] [--private-key-file PATH]' \
      'bash deploy/install-panel.sh --check-config --domain DOMAIN --private-key-file PATH' \
      'bash deploy/install-panel.sh --render-only --domain DOMAIN --admin-user USER --password-hash-file PATH --caddy-version VERSION --output-dir NEW_DIR' \
      'Render-only: offline, tanpa root; input hanya hash bcrypt, bukan password.' \
      'Installer baru saja; lihat deploy/README.md untuk pembaruan/uninstall.'
}
refuse_paths() {
    local path
    for path in "$@"; do
        [[ ! -e "$path" && ! -L "$path" ]] || fail "path sudah ada; tidak ditimpa. Lihat pembaruan/uninstall di deploy/README.md: $path"
    done
}
refuse_existing() {
    refuse_paths /opt/ali-patch-code /etc/ali-patch-code /etc/caddy /var/lib/caddy \
        /etc/systemd/system/ali-patch-code.service /etc/systemd/system/ali-patch-code.service.d \
        /lib/systemd/system/ali-patch-code.service /usr/lib/systemd/system/ali-patch-code.service \
        /etc/systemd/system/caddy.service /etc/systemd/system/caddy.service.d \
        /etc/systemd/system/caddy-api.service /etc/systemd/system/caddy-api.service.d \
        /lib/systemd/system/caddy.service /usr/lib/systemd/system/caddy.service \
        /usr/sbin/policy-rc.d
    ! command -v caddy >/dev/null 2>&1 || fail 'Caddy sudah terpasang; tidak mengambil alih situs/service lama.'
    local service
    for service in caddy caddy-api ali-patch-code; do
        if systemctl cat "$service" >/dev/null 2>&1; then
            fail 'unit service sudah dikenal systemd; tidak mengambil alih.'
        fi
    done
    ! getent passwd ali-patch-code >/dev/null || fail 'user ali-patch-code sudah ada; periksa pembaruan.'
    ! getent group ali-patch-code >/dev/null || fail 'group ali-patch-code sudah ada; periksa pembaruan.'
    ! getent passwd caddy >/dev/null || fail 'user Caddy sudah ada; tidak mengambil alih.'
    ! getent group caddy >/dev/null || fail 'group Caddy sudah ada; tidak mengambil alih.'
    if dpkg-query -W -f='${Status}' caddy 2>/dev/null | grep -q 'installed'; then
        fail 'paket Caddy sudah ada; tidak mengambil alih.'
    fi
}
check_ports() {
    local tcp udp
    tcp=$(ss -H -ltn '( sport = :80 or sport = :443 or sport = :12760 )') || fail 'ss TCP gagal'
    udp=$(ss -H -lun '( sport = :443 )') || fail 'ss UDP gagal'
    [[ -z "$tcp" && -z "$udp" ]] || fail 'port TCP 80/443/12760 atau UDP 443 dipakai; hentikan sendiri konflik yang diketahui. Tidak ada service dihentikan installer.'
}
ask() {
    local prompt=$1 variable=$2
    printf '%s: ' "$prompt" >/dev/tty
    IFS= read -r "$variable" </dev/tty || fail 'input terminal dibatalkan'
}
# Password lives only in unexported shell memory and Caddy stdin, never argv,
# files, logs or the environment. Leaves a 0600 bcrypt hash at $1.
hash_admin_password() {
    local target=$1
    unset PASSWORD PASSWORD_CONFIRM
    restore_tty
    TTY_STATE=$(stty -g </dev/tty) || fail 'tty tidak dapat dikonfigurasi'
    stty -echo </dev/tty || fail 'tty tidak dapat menyembunyikan input'
    printf 'Password admin (16-72 byte, tidak ditampilkan): ' >/dev/tty
    IFS= read -rs PASSWORD </dev/tty || { restore_tty; fail 'password dibatalkan'; }
    printf '\nUlangi password: ' >/dev/tty
    IFS= read -rs PASSWORD_CONFIRM </dev/tty || { restore_tty; fail 'password dibatalkan'; }
    restore_tty
    printf '\n' >/dev/tty
    # Count the 16..72-byte policy with a Bash builtin, not Unicode characters.
    # No password is passed to an external length command.
    local LC_ALL=C
    [[ ${#PASSWORD} -ge 16 && ${#PASSWORD} -le 72 ]] || fail 'password harus 16-72 byte'
    [[ $PASSWORD == "$PASSWORD_CONFIRM" ]] || fail 'password tidak cocok'
    printf '%s\n' "$PASSWORD" | caddy hash-password --algorithm bcrypt > "$target"
    unset PASSWORD PASSWORD_CONFIRM
}

# Roll back ONLY objects created by this invocation. Packages remain installed.
# Pre-existing Caddy/sites are refused, never backed up as an excuse to take over.
cleanup() {
    local status=$?
    trap - EXIT INT TERM
    set +e
    restore_tty
    unset PASSWORD PASSWORD_CONFIRM
    if [[ ${POLICY_CREATED:-0} == 1 ]]; then rm -f /usr/sbin/policy-rc.d; fi
    if [[ $status != 0 && ${TRANSACTION:-0} == 1 ]]; then
        printf '%s\n' 'Instalasi gagal; memulihkan snapshot dan menghentikan panel/Caddy baru.' >&2
        if [[ ${UNIT_CREATED:-0} == 1 ]]; then
            systemctl disable --now ali-patch-code >/dev/null 2>&1
            mv /etc/systemd/system/ali-patch-code.service "$BACKUP/failed-ali-patch-code.service"
        fi
        if [[ ${CADDY_INSTALLED:-0} == 1 ]]; then
            systemctl disable --now caddy >/dev/null 2>&1
        fi
        if [[ ${CADDY_CHANGED:-0} == 1 ]]; then
            mv /etc/caddy "$BACKUP/failed-caddy"
            cp -a "$BACKUP/caddy.before" /etc/caddy
        fi
        if [[ ${DROPIN_CREATED:-0} == 1 ]]; then
            mv /etc/systemd/system/caddy.service.d "$BACKUP/failed-caddy-dropin"
        fi
        if [[ ${APP_CREATED:-0} == 1 && -d /opt/ali-patch-code ]]; then
            mv /opt/ali-patch-code "$BACKUP/failed-app"
        fi
        if [[ ${KEYDIR_CREATED:-0} == 1 && -d /etc/ali-patch-code ]]; then
            mv /etc/ali-patch-code "$BACKUP/failed-private-config"
        fi
        systemctl daemon-reload
        printf 'Recovery: %s (root-only). Paket/user baru mungkin masih ada; lihat README.\n' "$BACKUP" >&2
    fi
    if [[ -n ${STAGE:-} && -d $STAGE ]]; then rm -rf -- "$STAGE"; fi
    exit "$status"
}

main() {
    local MODE=install DOMAIN= ADMIN_USER= LICENSE_FILE= HASH_FILE= OUT= VERSION=2.8.4
    local SCRIPT_DIR SOURCE option
    SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
    SOURCE=$(cd -- "$SCRIPT_DIR/.." && pwd -P)
    while (($#)); do
        option=$1
        case "$option" in
            --help|-h) usage; return 0 ;;
            --check-config|--render-only)
                [[ $MODE == install ]] || fail 'pilih satu mode'
                MODE=${option#--}; shift ;;
            --domain|--admin-user|--private-key-file|--password-hash-file|--caddy-version|--output-dir)
                (($# >= 2)) && [[ -n $2 && $2 != --* ]] || fail 'opsi membutuhkan nilai'
                case "$option" in
                    --domain) DOMAIN=$2 ;;
                    --admin-user) ADMIN_USER=$2 ;;
                    --private-key-file) LICENSE_FILE=$2 ;;
                    --password-hash-file) HASH_FILE=$2 ;;
                    --caddy-version) VERSION=$2 ;;
                    --output-dir) OUT=$2 ;;
                esac
                shift 2 ;;
            *) fail 'opsi tidak dikenal; password plaintext tidak diterima melalui argumen' ;;
        esac
    done
    command -v python3 >/dev/null || fail 'python3 diperlukan untuk preflight/offline renderer'
    if [[ $MODE == render-only ]]; then
        [[ -n $DOMAIN && -n $ADMIN_USER && -n $HASH_FILE && -n $OUT ]] || fail 'render-only memerlukan domain, admin-user, password-hash-file, output-dir'
        python3 "$SCRIPT_DIR/render_panel_config.py" render --domain "$DOMAIN" \
            --admin-user "$ADMIN_USER" --password-hash-file "$HASH_FILE" \
            --caddy-version "$VERSION" --output-dir "$OUT"
        printf '%s\n' 'Render selesai, BUKAN validasi Caddy atau bukti SSL. Jalankan caddy validate pada VPS.'
        return 0
    fi
    [[ -z $HASH_FILE && -z $OUT ]] || fail 'hash-file/output-dir hanya untuk render-only'
    [[ $(uname -s) == Linux ]] || fail 'instalasi/check-config memerlukan Linux; gunakan --render-only di macOS'
    export LC_ALL=C
    unset PYTHONPATH PYTHONHOME BASH_ENV ENV
    [[ -f /etc/os-release && -d /run/systemd/system ]] || fail 'Linux systemd diperlukan'
    # System-owned OS metadata; not repository or user-controlled shell input.
    . /etc/os-release
    case "${ID:-}:${VERSION_ID:-}" in
        ubuntu:24.04|ubuntu:22.04|debian:12) ;;
        *) fail 'target Ubuntu 24.04/22.04 atau Debian 12; distro lain belum diverifikasi' ;;
    esac
    local command_name
    for command_name in python3 ss systemctl apt-get apt-cache dpkg-query getent timeout; do
        command -v "$command_name" >/dev/null || fail "prasyarat belum ada: $command_name (pasang sendiri, lalu ulangi)"
    done
    [[ -n $DOMAIN ]] || ask 'Domain publik untuk HTTPS (tanpa https://)' DOMAIN
    DOMAIN=$(python3 "$SCRIPT_DIR/render_panel_config.py" validate-domain "$DOMAIN")
    [[ -n $ADMIN_USER ]] || { if [[ $MODE == check-config ]]; then ADMIN_USER=admin; else ask 'Username admin (3-32 karakter)' ADMIN_USER; fi; }
    python3 "$SCRIPT_DIR/render_panel_config.py" validate-user "$ADMIN_USER" >/dev/null
    [[ -n $LICENSE_FILE ]] || ask 'Path absolut private key yang cocok dengan PUBLIC KEY firmware (tidak membuat kunci baru)' LICENSE_FILE
    [[ $LICENSE_FILE == /* ]] || fail 'private-key-file harus path absolut'
    python3 "$SCRIPT_DIR/render_panel_config.py" validate-key "$LICENSE_FILE"
    python3 "$SCRIPT_DIR/render_panel_config.py" check-source --source "$SOURCE"
    refuse_existing
    check_ports
    timeout 20 python3 "$SCRIPT_DIR/render_panel_config.py" dns-check "$DOMAIN" || fail 'DNS preflight gagal/timeout'
    if [[ $MODE == check-config ]]; then
        printf '%s\n' 'Preflight read-only lulus. Belum memasang paket, menguji root, ACME, atau TLS. Tidak ada SSL yang diklaim berhasil.'
        return 0
    fi
    [[ $EUID == 0 ]] || fail 'instalasi memerlukan sudo/root; check-config dan render-only tidak'
    printf '%s\n' \
        'HANYA VPS standalone. DNS A/AAAA di atas harus menunjuk ke VPS ini (bukan CDN/proxy).' \
        'TCP 80/443 harus terbuka dari internet; 12760 tidak boleh diekspos.' \
        'Key harus cocok dengan firmware lab; installer TIDAK menghasilkan/mengambil workflow key.' \
        'Akan memasang paket distro, app lokal, user, Caddy dan systemd. Tidak mengubah firewall/SSH/network.'
    local CONSENT
    ask 'Ketik INSTALL untuk menyetujui dan mengonfirmasi DNS milik VPS ini' CONSENT
    [[ $CONSENT == INSTALL ]] || fail 'persetujuan tidak diberikan'
    umask 077
    STAGE=$(mktemp -d /run/ali-panel-install.XXXXXX)
    BACKUP=$(mktemp -d /var/backups/ali-patch-code-install.XXXXXX)
    TRANSACTION=1 POLICY_CREATED=0 CADDY_INSTALLED=0 CADDY_CHANGED=0
    APP_CREATED=0 UNIT_CREATED=0 KEYDIR_CREATED=0 DROPIN_CREATED=0
    trap cleanup EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    # Prevent package postinst from opening an unauthenticated default HTTP site.
    (set -o noclobber; printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d)
    POLICY_CREATED=1
    chmod 755 /usr/sbin/policy-rc.d
    apt-get update
    # Distro 22.04 may offer 2.4 only: fail BEFORE package installation, never
    # weaken auth. An administrator may configure the official signed Caddy repo.
    local CANDIDATE
    CANDIDATE=$(apt-cache policy caddy | python3 -c 'import re,sys; m=re.search(r"Candidate:\s+(?:\d+:)?(\d+\.\d+\.\d+)",sys.stdin.read()); print(m[1] if m else "missing")')
    python3 "$SCRIPT_DIR/render_panel_config.py" validate-version "$CANDIDATE" >/dev/null
    CADDY_INSTALLED=1
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        caddy python3 python3-venv ca-certificates
    systemctl disable --now caddy
    rm /usr/sbin/policy-rc.d
    POLICY_CREATED=0
    VERSION=$(caddy version)
    python3 "$SCRIPT_DIR/render_panel_config.py" validate-version "$VERSION" >/dev/null
    cp -a /etc/caddy "$BACKUP/caddy.before"
    systemctl cat caddy > "$BACKUP/caddy-unit.before.txt"
    check_ports
    hash_admin_password "$STAGE/hash"
    python3 "$SCRIPT_DIR/render_panel_config.py" render --domain "$DOMAIN" \
        --admin-user "$ADMIN_USER" --password-hash-file "$STAGE/hash" \
        --caddy-version "$VERSION" --output-dir "$STAGE/config"
    # Config validation must precede installation/start. Output may contain hashes;
    # keep it root-only rather than printing arbitrary config diagnostics.
    if ! caddy validate --config "$STAGE/config/Caddyfile" --adapter caddyfile > "$BACKUP/validation.log" 2>&1; then
        fail 'caddy validate gagal; detail root-only di backup; tidak mengaktifkan panel'
    fi
    useradd --system --user-group --home-dir /nonexistent --no-create-home \
        --shell /usr/sbin/nologin ali-patch-code
    refuse_paths /opt/ali-patch-code /etc/ali-patch-code
    APP_CREATED=1
    python3 "$SCRIPT_DIR/render_panel_config.py" copy-app --source "$SOURCE" --destination /opt/ali-patch-code
    python3 -m venv /opt/ali-patch-code/.venv
    # Do not execute arbitrary requirements/options from a checkout as root.
    /opt/ali-patch-code/.venv/bin/python -m pip --isolated install \
        --index-url https://pypi.org/simple --only-binary=:all: --no-deps 'PyYAML==6.0.3'
    chown -R root:root /opt/ali-patch-code
    chmod -R a+rX,go-w /opt/ali-patch-code
    KEYDIR_CREATED=1
    install -d -o root -g ali-patch-code -m 750 /etc/ali-patch-code
    install -o root -g ali-patch-code -m 640 -- "$LICENSE_FILE" /etc/ali-patch-code/license.key
    printf '%s\n' "$DOMAIN" > /etc/ali-patch-code/domain
    printf '%s\n' "$BACKUP" > /etc/ali-patch-code/install-backup
    chmod 640 /etc/ali-patch-code/domain /etc/ali-patch-code/install-backup
    chown root:ali-patch-code /etc/ali-patch-code/domain /etc/ali-patch-code/install-backup
    UNIT_CREATED=1
    install -o root -g root -m 644 "$STAGE/config/ali-patch-code.service" /etc/systemd/system/ali-patch-code.service
    CADDY_CHANGED=1
    install -o root -g caddy -m 640 "$STAGE/config/Caddyfile" /etc/caddy/Caddyfile
    DROPIN_CREATED=1
    install -d -o root -g root -m 755 /etc/systemd/system/caddy.service.d
    printf '[Service]\nStandardOutput=null\nStandardError=null\nLimitCORE=0\n' > /etc/systemd/system/caddy.service.d/ali-panel.conf
    chmod 644 /etc/systemd/system/caddy.service.d/ali-panel.conf
    systemctl daemon-reload
    systemd-analyze verify /etc/systemd/system/ali-patch-code.service > "$BACKUP/systemd-validation.log" 2>&1 || fail 'unit systemd tidak valid'
    systemctl enable --now ali-patch-code
    local deadline=$((SECONDS + 30))
    until python3 "$SCRIPT_DIR/render_panel_config.py" check-backend "$DOMAIN" >/dev/null 2>&1; do
        ((SECONDS < deadline)) || fail 'backend /api/health dengan Host domain tidak sehat; rollback'
        sleep 1
    done
    systemctl enable --now caddy
    systemctl is-active --quiet caddy || fail 'service caddy tidak aktif setelah start; rollback'
    deadline=$((SECONDS + 300))
    until timeout 40 python3 "$SCRIPT_DIR/render_panel_config.py" check-public "$DOMAIN" >/dev/null 2>&1; do
        ((SECONDS < deadline)) || fail 'TLS valid + HTTP 401 belum tercapai; rollback. Periksa DNS/CAA/80/443/ACME'
        sleep 5
    done
    TRANSACTION=0
    printf 'Panel: https://%s — backend sehat; TLS tepercaya + 401 tanpa kredensial terverifikasi dari VPS.\n' "$DOMAIN"
    printf 'Login dengan modal Basic Auth browser. Uji juga dari jaringan luar. Backup: %s\n' "$BACKUP"
}

# Sourceable pure preflight helpers for offline tests; no action when sourced.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then main "$@"; fi
