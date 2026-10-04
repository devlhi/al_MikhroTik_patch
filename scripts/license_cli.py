"""Generate a custom-lab license file locally; never contact a router."""
import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import license_util, license_server


WARNING = ('custom-lab-only: bukan lisensi resmi MikroTik; '
           'penerimaan atau aktivasi firmware belum dibuktikan.')


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        # argparse includes invalid values in its default diagnostic.
        self.exit(2, 'Argumen tidak valid; gunakan --help. Kunci hanya melalui berkas/env.\n')


def _run(argv=None):
    parser = _Parser(description=WARNING, allow_abbrev=False)
    parser.add_argument('--kind', choices=('chr', 'ros'))
    parser.add_argument('--id')
    parser.add_argument('--output')
    parser.add_argument('--private-key-file')
    args = parser.parse_args(argv)
    if argv == [] or (argv is None and len(sys.argv) == 1):
        print(WARNING)
        print('1. CHR\n2. RouterOS')
        while args.kind is None:
            args.kind = {'1': 'chr', '2': 'ros'}.get(input('Pilih jenis [1/2]: ').strip())
            if args.kind is None:
                print('Pilihan tidak valid; masukkan 1 atau 2.')
        args.id = input('System ID: ' if args.kind == 'chr' else 'Software ID: ').strip()
        default = REPO_ROOT / ('ali-lab-license-' + args.kind + '.txt')
        args.output = input('Berkas output [default: ' + str(default) + ']: ').strip() or str(default)
    elif not args.kind or not args.id or not args.output:
        parser.error('--kind, --id, dan --output wajib diisi')
    workflow = REPO_ROOT / '.github' / 'workflows' / 'patch7.yml'
    if workflow.is_file() or (args.private_key_file is None and not os.environ.get('ALI_LICENSE_PRIVATE_KEY')
                              and not license_server._default_private_key_file().is_file()):
        try:
            import yaml
        except ImportError:
            print('PyYAML diperlukan untuk membaca/mengecek workflow; pasang requirements-license.txt.',
                  file=sys.stderr)
            return 2
    try:
        if args.private_key_file is not None:
            key = Path(args.private_key_file).read_text(encoding='utf-8')
        elif os.environ.get('ALI_LICENSE_PRIVATE_KEY'):
            key = os.environ['ALI_LICENSE_PRIVATE_KEY']
        elif license_server._default_private_key_file().is_file():
            key = license_server._default_private_key_file().read_text(encoding='utf-8')
        else:
            key = license_server._workflow_private_key()
    except (OSError, UnicodeError, ValueError):
        print('Berkas kunci tidak dapat dibaca; tidak ada fallback.', file=sys.stderr)
        return 2
    generate = license_util.generate_chr if args.kind == 'chr' else license_util.generate_ros
    try:
        text = generate(args.id, key)
    except ValueError:
        print('ID atau kunci tidak valid; tidak ada berkas disimpan.', file=sys.stderr)
        return 2
    public = license_server._derive_public_key(license_util._decode_private_key(key))
    if workflow.is_file():
        import yaml
        try:
            config = yaml.safe_load(workflow.read_text(encoding='utf-8'))
        except (OSError, UnicodeError, yaml.YAMLError):
            print('Workflow tidak dapat dibaca sebagai YAML yang valid.', file=sys.stderr)
            return 2
        env = config.get('env', {}) if isinstance(config, dict) else {}
        workflow_public = env.get('CUSTOM_LICENSE_PUBLIC_KEY') if isinstance(env, dict) else None
        if workflow_public is not None and (
                not isinstance(workflow_public, str)
                or workflow_public.strip().lower() != public.hex()):
            print('Kunci terpilih tidak cocok dengan public key workflow.', file=sys.stderr)
            return 2
    try:
        fields = license_util.parse(text, public.hex())
    except (ValueError, ArithmeticError, AssertionError):
        print('Gagal verifikasi hasil; tidak ada berkas disimpan.', file=sys.stderr)
        return 1
    field = 'System ID' if args.kind == 'chr' else 'Software ID'
    if (fields.get('License valid') != 'True' or fields.get('kind') != args.kind
            or fields.get(field) != args.id.strip()):
        print('Gagal verifikasi hasil; tidak ada berkas disimpan.', file=sys.stderr)
        return 1
    output = Path(args.output).absolute()
    created = False
    try:
        with output.open('x', encoding='utf-8') as stream:
            created = True
            stream.write(text)
    except BaseException as error:
        if created:
            try:
                output.unlink()
            except OSError:
                print('Berkas parsial tidak dapat dihapus; hapus output sebelum mencoba ulang.',
                      file=sys.stderr)
        if isinstance(error, FileExistsError):
            print('Berkas output sudah ada; tidak ditimpa.', file=sys.stderr)
            return 1
        if isinstance(error, OSError):
            print('Tidak dapat menyimpan berkas output; periksa folder dan izin tulis.', file=sys.stderr)
            return 1
        raise
    print('Tersimpan:', output)
    print(WARNING)
    return 0


def main(argv=None):
    if sys.version_info < (3, 10):
        print('Python 3.10+ diperlukan. Pasang dari https://www.python.org/downloads/',
              file=sys.stderr)
        return 2
    try:
        return _run(argv)
    except KeyboardInterrupt:
        print('Pembuatan dibatalkan.', file=sys.stderr)
        return 130
    except EOFError:
        print('Input berakhir; pembuatan dibatalkan.', file=sys.stderr)
        return 2
    except (OSError, UnicodeError, ValueError):
        print('ID, kunci, atau jalur berkas tidak valid/tidak dapat diakses.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
