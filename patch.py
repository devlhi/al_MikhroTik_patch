import subprocess
import lzma
import struct
import os
import tempfile
import re
import stat as stat_module
from pathlib import Path
from npk import NovaPackage, NpkPartID, NpkFileContainer


def _x86_immediate_matches(data: bytes, old: bytes, new: bytes):
    """Match one 32-byte value in eight adjacent i386 stack MOVs.

    Limit instruction matching to executable PROGBITS sections of ELF32/i386.
    Each C7 /0 writes one dword to [ebp + displacement]; the destinations must
    cover one consecutive 32-byte buffer. Never match independent key words.
    """
    if (len(old) != 32 or len(new) != 32 or len(data) < 52
            or data[:7] != b'\x7fELF\x01\x01\x01'
            or struct.unpack_from('<H', data, 18)[0] != 3):
        return []
    (_, elf_type, _, version, _, program_offset, section_offset, _, header_size,
     program_entry_size, program_count, entry_size, section_count,
     string_index) = struct.unpack_from('<16sHHIIIIIHHHHHH', data)
    section_end = section_offset + entry_size * section_count
    if (elf_type not in (1, 2, 3) or version != 1 or header_size != 52
            or entry_size != 40 or not 0 < section_count < 0xff00
            or section_offset < header_size or section_end > len(data)
            or string_index >= section_count or program_count == 0xffff):
        return []  # Extended numbering and unsupported headers fail closed.
    metadata = [(0, header_size), (section_offset, section_end)]
    if program_count:
        program_end = program_offset + program_entry_size * program_count
        if (program_entry_size != 32 or program_offset < header_size
                or program_end > len(data)
                or (program_offset < section_end and section_offset < program_end)):
            return []
        metadata.append((program_offset, program_end))
    elif program_offset or program_entry_size not in (0, 32):
        return []
    code_ranges = set()
    for index in range(section_count):
        section = struct.unpack_from('<10I', data, section_offset + index * entry_size)
        _, kind, flags, _, start, size, *_ = section
        end = start + size
        # A code range must never alias ELF header or table metadata.
        if (kind != 1 or not flags & 4 or not size
                or start < header_size or end > len(data)
                or any(start < reserved_end and end > reserved_start
                       for reserved_start, reserved_end in metadata)):
            continue
        code_ranges.add((start, end))
    code_ranges = sorted(code_ranges)
    # Identical ranges share a boundary and are decoded once. Any other
    # overlap is ambiguous: validate all ranges before decoding any of them.
    furthest_end = 0
    for start, end in code_ranges:
        if start < furthest_end:
            return []
        furthest_end = max(furthest_end, end)
    # Decode from the section start, never resynchronize by scanning for C7:
    # prefixes, immediates and displacements are not instruction boundaries.
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_32
        from capstone.x86_const import X86_INS_MOV
    except (ImportError, OSError):
        return []  # No decoder means no instruction matches, not a raw fallback.
    from collections import deque
    decoder = Cs(CS_ARCH_X86, CS_MODE_32)
    decoder.detail = True
    decoder.skipdata = False
    matches = []
    seen = set()
    for start, end in code_ranges:
        pending = deque(maxlen=8)
        for instruction in decoder.disasm(data[start:end], start):
            displacement_size = {b'\xc7\x45': 1, b'\xc7\x85': 4}.get(
                bytes(instruction.bytes[:2]))
            # These exact unprefixed ModR/M encodings name [ebp+disp], not
            # another segment/register/address size. The decoder validates
            # both the instruction boundary and the operand/immediate sizes.
            if (instruction.id != X86_INS_MOV or displacement_size is None
                    or any(instruction.prefix) or instruction.addr_size != 4
                    or instruction.imm_size != 4
                    or instruction.imm_offset != 2 + displacement_size
                    or instruction.size != 6 + displacement_size):
                pending.clear()
                continue
            immediate = instruction.address + instruction.imm_offset
            displacement = int.from_bytes(
                instruction.bytes[2:instruction.imm_offset], 'little', signed=True)
            pending.append((instruction.address, immediate + 4, displacement, immediate))
            if len(pending) != 8:
                continue
            begin, _, base, _ = pending[0]
            position = pending[-1][1]
            if (any(current[0] != previous[1]
                    for previous, current in zip(pending, list(pending)[1:]))
                    or any(displacement != base + word * 4
                           or data[immediate:immediate + 4] != old[word * 4:word * 4 + 4]
                           for word, (_, _, displacement, immediate) in enumerate(pending))
                    or (begin, position) in seen):
                continue
            replacement = bytearray(data[begin:position])
            for word, (_, _, _, immediate) in enumerate(pending):
                offset = immediate - begin
                replacement[offset:offset + 4] = new[word * 4:word * 4 + 4]
            matches.append((begin, position, bytes(replacement)))
            seen.add((begin, position))
    return matches


def _replace_keys(data: bytes, key_dict: dict, label, stats: dict | None = None,
                  preserve_license: bytes | None = None) -> bytes:
    """Replace original nonoverlapping literal/instruction matches atomically."""
    matches = []
    counts = []
    preserved = []
    for index, (old_public_key, new_public_key) in enumerate(key_dict.items(), 1):
        literal_count = data.count(old_public_key)
        offset = 0
        for _ in range(literal_count):
            start = data.find(old_public_key, offset)
            end = start + len(old_public_key)
            matches.append((start, end, new_public_key))
            offset = end
        instruction_matches = _x86_immediate_matches(data, old_public_key, new_public_key)
        matches.extend(instruction_matches)
        if preserve_license == old_public_key:
            if len(instruction_matches) != 1:
                raise ValueError('loader must contain exactly one LICENSE instruction anchor')
            preserved = instruction_matches
        count = literal_count + len(instruction_matches) - (
            len(instruction_matches) if preserve_license == old_public_key else 0)
        if count:
            counts.append((index, old_public_key, count))
    matches.sort(key=lambda match: match[0])
    for previous, current in zip(matches, matches[1:]):
        if current[0] < previous[1]:
            raise ValueError('replacement patterns overlap in original fragment')
    # Keep the preserved envelope in overlap preflight; suppression happens only
    # after every mapping has been planned against pristine bytes.
    if preserve_license is not None and not preserved:
        raise ValueError('explicit LICENSE mapping required for loader preservation')
    new_data = bytearray(data)
    for start, end, new_public_key in reversed(matches):
        if (start, end, new_public_key) not in preserved:
            new_data[start:end] = new_public_key
    for index, old_public_key, count in counts:
        print(f'{label}: mapping {index}, replacements={count}')
        if stats is not None:
            stats[old_public_key] = stats.get(old_public_key, 0) + count
    return bytes(new_data)


def patch_bzimage(data: bytes, key_dict: dict, stats: dict | None = None):
    PE_TEXT_SECTION_OFFSET = 414
    HEADER_PAYLOAD_OFFSET = 584
    HEADER_PAYLOAD_LENGTH_OFFSET = HEADER_PAYLOAD_OFFSET + 4
    text_section_raw_data = struct.unpack_from(
        '<I', data, PE_TEXT_SECTION_OFFSET)[0]
    payload_offset = text_section_raw_data + \
        struct.unpack_from('<I', data, HEADER_PAYLOAD_OFFSET)[0]
    payload_length = struct.unpack_from(
        '<I', data, HEADER_PAYLOAD_LENGTH_OFFSET)[0]
    # last 4 bytes is uncompressed size(z_output_len)
    payload_length = payload_length - 4
    z_output_len = struct.unpack_from(
        '<I', data, payload_offset+payload_length)[0]
    vmlinux_xz = data[payload_offset:payload_offset+payload_length]
    vmlinux = lzma.decompress(vmlinux_xz)
    assert z_output_len == len(
        vmlinux), 'vmlinux size is not equal to expected'
    CPIO_HEADER_MAGIC = b'07070100'
    CPIO_FOOTER_MAGIC = b'TRAILER!!!\x00\x00\x00\x00'  # 545241494C455221212100000000
    cpio_offset1 = vmlinux.index(CPIO_HEADER_MAGIC)
    initramfs = vmlinux[cpio_offset1:]
    cpio_offset2 = initramfs.index(CPIO_FOOTER_MAGIC)+len(CPIO_FOOTER_MAGIC)
    initramfs = initramfs[:cpio_offset2]
    new_initramfs = _replace_keys(initramfs, key_dict, 'initramfs', stats)
    new_vmlinux = vmlinux.replace(initramfs, new_initramfs)
    new_vmlinux_xz = lzma.compress(new_vmlinux, check=lzma.CHECK_CRC32, filters=[
        {"id": lzma.FILTER_X86},
        {"id": lzma.FILTER_LZMA2,
         "preset": 9 | lzma.PRESET_EXTREME,
         'dict_size': 32*1024*1024,
         "lc": 4, "lp": 0, "pb": 0,
         },
    ])
    new_payload_length = len(new_vmlinux_xz)
    assert new_payload_length <= payload_length, 'new vmlinux.xz size is too big'
    # last 4 bytes is uncompressed size(z_output_len)
    new_payload_length = new_payload_length + 4
    new_data = bytearray(data)
    struct.pack_into(
        '<I', new_data, HEADER_PAYLOAD_LENGTH_OFFSET, new_payload_length)
    vmlinux_xz += struct.pack('<I', z_output_len)
    new_vmlinux_xz += struct.pack('<I', z_output_len)
    new_vmlinux_xz = new_vmlinux_xz.ljust(len(vmlinux_xz), b'\0')
    new_data = new_data.replace(vmlinux_xz, new_vmlinux_xz)
    return new_data


def patch_block(dev:str,file:str,key_dict):
    BLOCK_SIZE = 4096
    #sudo debugfs /dev/nbd0p1 -R 'stats' | grep "Block size" | sed -n '1p' | cut -d ':' -f 2 

    #sudo debugfs /dev/nbd0p1 -R 'stat boot/initrd.rgz' 2> /dev/null | sed -n '11p'
    stdout,_ = run_shell_command(f"debugfs {dev} -R 'stat {file}' 2> /dev/null | sed -n '11p' ")
    #(0-11):1592-1603, (IND):1173, (12-15):1604-1607, (16-26):1424-1434
    blocks_info = stdout.decode().strip().split(',')
    print(f'blocks_info : {blocks_info}')
    blocks = []
    ind_block_id = None
    for block_info in blocks_info:
        _tmp = block_info.strip().split(':')
        if _tmp[0].strip() == '(IND)':
            ind_block_id =  int(_tmp[1])
        else:
            print(f'block_info : {block_info}')
            id_range = _tmp[0].strip().replace('(','').replace(')','').split('-')
            block_range = _tmp[1].strip().replace('(','').replace(')','').split('-')
            blocks += [id for id in range(int(block_range[0]),int(block_range[1])+1)]
    print(f' blocks : {len(blocks)} ind_block_id : {ind_block_id}')
    
    #sudo debugfs /dev/nbd0p1  -R 'cat boot/initrd.rgz' > data
    data,stderr = run_shell_command(f"debugfs {dev} -R 'cat {file}' 2> /dev/null")
    new_data = patch_kernel(data,key_dict)
    print(f'write block {len(blocks)} : [',end="")
    with open(dev,'wb') as f:
        for index,block_id in enumerate(blocks):
            print('#',end="")
            f.seek(block_id*BLOCK_SIZE)
            f.write(new_data[index*BLOCK_SIZE:(index+1)*BLOCK_SIZE])
        f.flush()
        print(']')


def patch_initrd_xz(initrd_xz:bytes,key_dict:dict,ljust=True,stats:dict|None=None):
    initrd = lzma.decompress(initrd_xz)
    new_initrd = _replace_keys(initrd, key_dict, 'initrd', stats)
    preset = 6
    new_initrd_xz = lzma.compress(new_initrd,check=lzma.CHECK_CRC32,filters=[{"id": lzma.FILTER_LZMA2, "preset": preset }] )
    while len(new_initrd_xz) > len(initrd_xz) and preset < 9:
        print(f'preset:{preset}')
        print(f'new initrd xz size:{len(new_initrd_xz)}')
        print(f'old initrd xz size:{len(initrd_xz)}')
        preset += 1
        new_initrd_xz = lzma.compress(new_initrd,check=lzma.CHECK_CRC32,filters=[{"id": lzma.FILTER_LZMA2, "preset": preset }] )
    if len(new_initrd_xz) > len(initrd_xz):
        new_initrd_xz = lzma.compress(new_initrd,check=lzma.CHECK_CRC32,filters=[{"id": lzma.FILTER_LZMA2, "preset": 9 | lzma.PRESET_EXTREME,'dict_size': 32*1024*1024,"lc": 4,"lp": 0, "pb": 0,}] )
    if ljust:
        print(f'preset:{preset}')
        print(f'new initrd xz size:{len(new_initrd_xz)}')
        print(f'old initrd xz size:{len(initrd_xz)}')
        print(f'ljust size:{len(initrd_xz)-len(new_initrd_xz)}')
        assert len(new_initrd_xz) <= len(initrd_xz),'new initrd xz size is too big'
        new_initrd_xz = new_initrd_xz.ljust(len(initrd_xz),b'\0')
    return new_initrd_xz


def find_7zXZ_data(data: bytes):
    offset1 = 0
    _data = data
    while b'\xFD7zXZ\x00\x00\x01' in _data:
        offset1 = offset1 + _data.index(b'\xFD7zXZ\x00\x00\x01') + 8
        _data = _data[offset1:]
    offset1 -= 8
    offset2 = 0
    _data = data
    while b'\x00\x00\x00\x00\x01\x59\x5A' in _data:
        offset2 = offset2 + _data.index(b'\x00\x00\x00\x00\x01\x59\x5A') + 7
        _data = _data[offset2:]
    print(f'found 7zXZ data offset:{offset1} size:{offset2-offset1}')
    return data[offset1:offset2]


def patch_elf(data: bytes, key_dict: dict, stats: dict | None = None):
    initrd_xz = find_7zXZ_data(data)
    new_initrd_xz = patch_initrd_xz(initrd_xz, key_dict, stats=stats)
    return data.replace(initrd_xz, new_initrd_xz)


def patch_pe(data: bytes, key_dict: dict, stats: dict | None = None):
    vmlinux_xz = find_7zXZ_data(data)
    vmlinux = lzma.decompress(vmlinux_xz)
    initrd_xz_offset = vmlinux.index(b'\xFD7zXZ\x00\x00\x01')
    initrd_xz_size = vmlinux[initrd_xz_offset:].index(
        b'\x00\x00\x00\x00\x01\x59\x5A') + 7
    initrd_xz = vmlinux[initrd_xz_offset:initrd_xz_offset+initrd_xz_size]
    new_initrd_xz = patch_initrd_xz(initrd_xz, key_dict, stats=stats)
    new_vmlinux = vmlinux.replace(initrd_xz, new_initrd_xz)
    new_vmlinux_xz = lzma.compress(new_vmlinux, check=lzma.CHECK_CRC32, filters=[
                                   {"id": lzma.FILTER_LZMA2, "preset": 9, }])
    assert len(new_vmlinux_xz) <= len(
        vmlinux_xz), 'new vmlinux xz size is too big'
    print(f'new vmlinux xz size:{len(new_vmlinux_xz)}')
    print(f'old vmlinux xz size:{len(vmlinux_xz)}')
    print(f'ljust size:{len(vmlinux_xz)-len(new_vmlinux_xz)}')
    new_vmlinux_xz = new_vmlinux_xz.ljust(len(vmlinux_xz), b'\0')
    new_data = data.replace(vmlinux_xz, new_vmlinux_xz)
    return new_data


def patch_netinstall(key_dict: dict, input_file, output_file=None):
    netinstall = open(input_file, 'rb').read()
    if netinstall[:2] == b'MZ':
        import pefile
        ROUTEROS_BOOT = {
            129: {'arch': 'power', 'name': 'Powerboot'},
            130: {'arch': 'e500', 'name': 'e500_boot'},
            131: {'arch': 'mips', 'name': 'Mips_boot'},
            135: {'arch': '400', 'name': '440__boot'},
            136: {'arch': 'tile', 'name': 'tile_boot'},
            137: {'arch': 'arm', 'name': 'ARM__boot'},
            138: {'arch': 'mmips', 'name': 'MMipsBoot'},
            139: {'arch': 'arm64', 'name': 'ARM64__boot'},
            143: {'arch': 'x86_64', 'name': 'x86_64boot'}
        }
        with pefile.PE(input_file) as pe:
            for resource in pe.DIRECTORY_ENTRY_RESOURCE.entries:
                if resource.id == pefile.RESOURCE_TYPE["RT_RCDATA"]:
                    for sub_resource in resource.directory.entries:
                        if sub_resource.id in ROUTEROS_BOOT:
                            bootloader = ROUTEROS_BOOT[sub_resource.id]
                            print(f'found {bootloader["arch"]}({sub_resource.id}) bootloader')
                            rva = sub_resource.directory.entries[0].data.struct.OffsetToData
                            size = sub_resource.directory.entries[0].data.struct.Size
                            data = pe.get_data(rva, size)
                            _size = struct.unpack('<I', data[:4])[0]
                            _data = data[4:4+_size]
                            try:
                                if _data[:2] == b'MZ':
                                    new_data = patch_pe(_data, key_dict)
                                elif _data[:4] == b'\x7FELF':
                                    new_data = patch_elf(_data, key_dict)
                                else:
                                    raise Exception(f'unknown bootloader format {_data[:4].hex().upper()}')
                            except Exception as e:
                                print(f'patch {bootloader["arch"]}({sub_resource.id}) bootloader failed {e}')
                                new_data = _data
                            new_data = struct.pack(
                                "<I", _size) + new_data.ljust(len(_data), b'\0')
                            new_data = new_data.ljust(size, b'\0')
                            pe.set_bytes_at_rva(rva, new_data)
            pe.write(output_file or input_file)
    elif netinstall[:4] == b'\x7FELF':
        import re
        # 83 00 00 00 C4 68 C4 0B  5A C2 04 08 10 9E 52 00
        # 8A 00 00 00 C3 68 C4 0B  6A 60 57 08 C0 3D 54 00
        # 81 00 00 00 D3 68 C4 0B  2A 9E AB 08 5C 1B 78 00
        # 82 00 00 00 E8 6B C4 0B  86 B9 23 09 78 01 82 00
        # 87 00 00 00 ED 6B C4 0B  FE BA A5 09 44 BF 7B 00
        # 89 00 00 00 0C 6A C4 0B  42 7A 21 0A C4 1D 3E 00
        # 8B 00 00 00 1E 69 C4 0B  06 98 5F 0A 28 95 5E 00
        # 8C 00 00 00 F1 6B C4 0B  2E 2D BE 0A 78 EA 5D 00
        # 88 00 00 00 03 69 C4 0B  A6 17 1C 0B 28 55 4A 00
        # 8F 00 00 00 FC 6B C4 0B  CE 6C 66 0B E0 E8 58 00
        SECTION_HEADER_OFFSET_IN_FILE = struct.unpack_from(
            b'<I', netinstall[0x20:])[0]
        SECTION_HEADER_ENTRY_SIZE = struct.unpack_from(
            b'<H', netinstall[0x2E:])[0]
        NUMBER_OF_SECTION_HEADER_ENTRIES = struct.unpack_from(
            b'<H', netinstall[0x30:])[0]
        STRING_TABLE_INDEX = struct.unpack_from(b'<H', netinstall[0x32:])[0]
        section_name_offset = SECTION_HEADER_OFFSET_IN_FILE + \
            STRING_TABLE_INDEX * SECTION_HEADER_ENTRY_SIZE + 16
        SECTION_NAME_BLOCK = struct.unpack_from(
            b'<I', netinstall[section_name_offset:])[0]
        for i in range(NUMBER_OF_SECTION_HEADER_ENTRIES):
            section_offset = SECTION_HEADER_OFFSET_IN_FILE + i * SECTION_HEADER_ENTRY_SIZE
            name_offset, _, _, addr, offset = struct.unpack_from(
                '<IIIII', netinstall[section_offset:])
            name = netinstall[SECTION_NAME_BLOCK+name_offset:].split(b'\0')[0]
            if name == b'.text':
                print(f'found .text section at {hex(offset)} addr {hex(addr)}')
                text_section_addr = addr
                text_section_offset = offset
                break
        offset = re.search(
            rb'\x83\x00\x00\x00.{12}\x8A\x00\x00\x00.{12}\x81\x00\x00\x00.{12}', netinstall).start()
        print(f'found bootloaders offset {hex(offset)}')
        for i in range(10):
            id, name_ptr, data_ptr, data_size = struct.unpack_from(
                '<IIII', netinstall[offset+i*16:offset+i*16+16])
            name = netinstall[text_section_offset +
                              name_ptr-text_section_addr:].split(b'\0')[0]
            data = netinstall[text_section_offset+data_ptr -
                              text_section_addr:text_section_offset+data_ptr-text_section_addr+data_size]
            print(f'found {name.decode()}({id}) bootloader offset {hex(text_section_offset+data_ptr-text_section_addr)} size {data_size}')
            try:
                if data[:2] == b'MZ':
                    new_data = patch_pe(data, key_dict)
                elif data[:4] == b'\x7FELF':
                    new_data = patch_elf(data, key_dict)
                else:
                    raise Exception(f'unknown bootloader format {data[:4].hex().upper()}')
            except Exception as e:
                print(f'patch {name.decode()}({id}) bootloader failed {e}')
                new_data = data
            new_data = new_data.ljust(len(data), b'\0')
            netinstall = netinstall.replace(data, new_data)
        open(output_file or input_file, 'wb').write(netinstall)


def patch_kernel(data: bytes, key_dict, stats: dict | None = None):
    if data[:2] == b'MZ':
        print('patching EFI Kernel')
        if data[56:60] == b'ARM\x64':
            print('patching arm64')
            return patch_elf(data, key_dict, stats)
        else:
            print('patching x86_64')
            return patch_bzimage(data, key_dict, stats)
    elif data[:4] == b'\x7FELF':
        print('patching ELF')
        return patch_elf(data, key_dict, stats)
    elif data[:5] == b'\xFD7zXZ':
        print('patching initrd')
        return patch_initrd_xz(data, key_dict, stats=stats)
    else:
        raise Exception('unknown kernel format')


def patch_squashfs(path, key_dict, stats: dict | None = None,
                   runtime_policy=None, license_public_key=None):
    required = {'nova/bin/loader', 'nova/bin/keyman', 'nova/bin/mode'}
    if runtime_policy:
        for relative in required:
            file = Path(path) / relative
            if (any(parent.is_symlink() for parent in (file, file.parent, file.parent.parent))
                    or not file.is_file() or file.stat().st_nlink != 1):
                raise ValueError('runtime policy requires regular unlinked files: ' + relative)
    license_counts = {}
    # Multiple directory entries can reference one inode: unsquashfs keeps
    # SquashFS hardlinks as hardlinked extracted files. Read and patch each
    # inode exactly once so an alias never re-reads bytes an earlier write
    # generated, while identical contents on distinct inodes still count
    # individually. Writing through one name updates the shared inode, so
    # hardlink identity survives into the repacked image.
    seen_inodes = set()
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in files:
            file = Path(root) / name
            if file.is_symlink() or not file.is_file():
                continue
            stat = file.stat()
            identity = (stat.st_dev, stat.st_ino)
            if identity in seen_inodes:
                continue
            seen_inodes.add(identity)
            data = file.read_bytes()
            relative = file.relative_to(path).as_posix()
            local_stats = {}
            preserve = license_public_key if runtime_policy and relative == 'nova/bin/loader' else None
            new_data = _replace_keys(data, key_dict, str(file), local_stats, preserve)
            if stats is not None:
                for key, count in local_stats.items():
                    stats[key] = stats.get(key, 0) + count
            if relative in required:
                license_counts[relative] = local_stats.get(license_public_key, 0)
            if new_data != data:
                file.write_bytes(new_data)
                if runtime_policy:
                    os.chmod(file, stat_module.S_IMODE(stat.st_mode))
                os.utime(file, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    if runtime_policy and any(license_counts.get(relative, 0) < 1
                              for relative in ('nova/bin/keyman', 'nova/bin/mode')):
        raise ValueError('runtime policy requires LICENSE replacement in keyman and mode')


def run_shell_command(command):
    process = subprocess.run(
        command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return process.stdout, process.stderr


def _run_tools(args, work_dir: Path, *, preserve_modes=False):
    """Run a SquashFS tool with literal argv in an isolated workspace."""
    options = {}
    if preserve_modes:
        if os.name != 'posix':
            raise ValueError('runtime policy mode-preserving extraction requires POSIX')
        # Non-root unsquashfs masks regular file modes with the inherited umask.
        # Set it in this child only; the parent and private workspace stay private.
        options['umask'] = 0
    process = subprocess.run(args, cwd=work_dir, check=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, **options)
    return process.stdout, process.stderr


def _validate_key_dict(key_dict):
    if not key_dict:
        raise ValueError('replacement mapping must not be empty')
    for old, new in key_dict.items():
        if not isinstance(old, bytes) or not isinstance(new, bytes):
            raise ValueError('replacement patterns must be bytes')
        if not old or len(old) != len(new) or old == new:
            raise ValueError('replacement patterns must be nonempty, equal-length and distinct')
    # Reject direct containment; _replace_keys uses original offsets to avoid
    # affix-generated matches and rejects overlapping original spans.
    if any(old in new for new in key_dict.values() for old in key_dict):
        raise ValueError('replacement patterns must not cascade into another mapping')


_CHR_RUNTIME_POLICY = 'chr-x86-7.24.4'


def _part(package, part_id, required=True):
    """Inspect parts without Package.__getitem__'s auto-creation side effect."""
    parts = [part for part in package if part.id == part_id]
    if len(parts) > 1 or (required and not parts):
        raise ValueError('missing or duplicate NPK part: ' + part_id.name)
    return parts[0] if parts else None


def _validate_runtime_policy(package, key_dict, runtime_policy, license_public_key):
    if runtime_policy != _CHR_RUNTIME_POLICY:
        raise ValueError('unsupported runtime policy')
    if getattr(package, '_packages', []):
        raise ValueError('runtime policy only supports single-package CHR system NPK')
    info = _part(package, NpkPartID.NAME_INFO).data
    if info.name != 'system' or info.version != '7.24.4.final':
        raise ValueError('runtime policy requires system 7.24.4.final')
    parts = list(package)
    signature = _part(package, NpkPartID.SIGNATURE)
    signature_index = parts.index(signature)
    architectures = [(index, part.data) for index, part in enumerate(parts)
                     if part.id == NpkPartID.ARCHITECTURE]
    # Real CHR has an authoritative i386 before SIGNATURE and a trailing I
    # marker of unknown meaning. Preserve it, but never accept arbitrary duplicates.
    if (not architectures or architectures[0][1] != b'i386'
            or architectures[0][0] >= signature_index
            or (len(architectures) != 1 and not (
                len(architectures) == 2 and architectures[1][1] == b'I'
                and architectures[1][0] > signature_index))):
        raise ValueError('runtime policy requires unambiguous i386 architecture')
    if (not isinstance(license_public_key, bytes) or len(license_public_key) != 32
            or license_public_key not in key_dict):
        raise ValueError('runtime policy requires explicit 32-byte LICENSE mapping')
    _validate_key_dict(key_dict)
    _part(package, NpkPartID.FILE_CONTAINER)
    _part(package, NpkPartID.SQUASHFS)


def _squashfs_time(data):
    if len(data) < 96 or data[:4] != b'hsqs' or struct.unpack_from('<HH', data, 28) != (4, 0):
        raise ValueError('runtime policy requires SquashFS v4 superblock')
    return struct.unpack_from('<I', data, 8)[0]


def _squashfs_metadata(image, work_dir):
    """Numeric on-image ownership, second-precision times, types and modes.

    Directory byte lengths are packing details, not filesystem metadata.
    Fail closed on unfamiliar listing formats rather than guess ownership.
    """
    output, _ = _run_tools(['unsquashfs', '-lln', '-full', str(image)], work_dir)
    entries = {}
    for line in output.decode('utf-8', errors='strict').splitlines():
        match = re.fullmatch(
            r'([drwxstSTlbcps-]{10})\s+(\d+)/(\d+)\s+([\d, ]+?)\s+'
            r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) (squashfs-root(?:/.*)?)', line)
        if not match:
            raise ValueError('unsupported SquashFS metadata listing')
        mode, uid, gid, size, mtime, path = match.groups()
        if uid != '0' or gid != '0':
            raise ValueError('runtime policy requires all-root source SquashFS')
        if path in entries:
            raise ValueError('duplicate SquashFS metadata path')
        entries[path] = (mode, uid, gid, None if mode[0] == 'd' else size.strip(), mtime)
    if 'squashfs-root' not in entries:
        raise ValueError('empty SquashFS metadata inventory')
    return entries


def _tree_metadata(root):
    """Verify extraction/repack parity including symlink targets and hardlinks."""
    entries, inodes = {}, {}
    paths = [root]
    for directory, dirs, files in os.walk(root, followlinks=False):
        paths.extend(Path(directory) / name for name in dirs + files)
    for path in paths:
        st = path.lstat()
        relative = path.relative_to(root).as_posix()
        link = os.readlink(path) if stat_module.S_ISLNK(st.st_mode) else None
        entries[relative] = (st.st_mode, st.st_mtime_ns, link, st.st_rdev)
        if not stat_module.S_ISDIR(st.st_mode):
            inodes.setdefault((st.st_dev, st.st_ino), []).append(relative)
    links = sorted(tuple(sorted(names)) for names in inodes.values())
    return entries, links


def patch_npk_package(package, key_dict, runtime_policy=None, license_public_key=None):
    if runtime_policy is not None:
        _validate_runtime_policy(package, key_dict, runtime_policy, license_public_key)
    name = package[NpkPartID.NAME_INFO].data.name
    report = {'package': name, 'status': 'not-system', 'replacements': [],
              'scope': 'literal replacement coverage only; boot and activation untested'}
    if name != 'system':
        return report
    _validate_key_dict(key_dict)
    kernel_stats = {key: 0 for key in key_dict}
    squashfs_stats = {key: 0 for key in key_dict}
    file_container = NpkFileContainer.unserialize_from(
        package[NpkPartID.FILE_CONTAINER].data)
    for item in file_container:
        if item.name in [b'boot/EFI/BOOT/BOOTX64.EFI', b'boot/kernel', b'boot/initrd.rgz']:
            print(f'patch {item.name} ...')
            item.data = bytes(patch_kernel(item.data, key_dict, kernel_stats))
    # Do not touch caller files or package parts until coverage and repacking
    # succeed. TemporaryDirectory also cleans up on a tool/coverage failure.
    with tempfile.TemporaryDirectory(prefix='ali-npk-') as directory:
        work_dir = Path(directory)
        squashfs_file = work_dir / 'source.sfs'
        extract_dir = work_dir / 'root'
        repacked_file = work_dir / 'repacked.sfs'
        source_squashfs = package[NpkPartID.SQUASHFS].data
        squashfs_file.write_bytes(source_squashfs)
        if runtime_policy:
            mkfs_time = _squashfs_time(source_squashfs)
            source_metadata = _squashfs_metadata(squashfs_file, work_dir)
        extract_args = ['unsquashfs', '-d', str(extract_dir), str(squashfs_file)]
        if runtime_policy:
            _run_tools(extract_args, work_dir, preserve_modes=True)
            tree_metadata = _tree_metadata(extract_dir)
            patch_squashfs(extract_dir, key_dict, squashfs_stats,
                           runtime_policy, license_public_key)
        else:
            _run_tools(extract_args, work_dir)
            patch_squashfs(extract_dir, key_dict, squashfs_stats)
        if runtime_policy and _tree_metadata(extract_dir) != tree_metadata:
            raise ValueError('metadata changed during runtime policy patch')
        report['replacements'] = [
            {'mapping_index': index, 'kernel': kernel_stats[key],
             'squashfs': squashfs_stats[key],
             'total': kernel_stats[key] + squashfs_stats[key]}
            for index, key in enumerate(key_dict, 1)]
        missing = [str(item['mapping_index']) for item in report['replacements']
                   if item['total'] == 0]
        if missing:
            raise ValueError('no replacement for required mapping(s) ' + ', '.join(missing)
                             + ' in system package; signing blocked')
        repack_args = ['mksquashfs', str(extract_dir), str(repacked_file),
                       '-quiet', '-noappend', '-comp', 'xz', '-no-xattrs', '-b', '256k']
        if runtime_policy:
            repack_args += ['-all-root', '-mkfs-time', str(mkfs_time)]
        _run_tools(repack_args, work_dir)
        new_squashfs = repacked_file.read_bytes()
        if not new_squashfs:
            raise ValueError('empty repacked SquashFS; signing blocked')
        if runtime_policy:
            if (_squashfs_time(new_squashfs) != mkfs_time
                    or _squashfs_metadata(repacked_file, work_dir) != source_metadata):
                raise ValueError('repacked SquashFS metadata mismatch; signing blocked')
            verify_dir = work_dir / 'verify'
            _run_tools(['unsquashfs', '-d', str(verify_dir), str(repacked_file)], work_dir,
                       preserve_modes=True)
            if _tree_metadata(verify_dir) != tree_metadata:
                raise ValueError('repacked SquashFS inode/link metadata mismatch; signing blocked')
            report['runtime_policy'] = runtime_policy
            report['preserved_anchors'] = [{'path': 'nova/bin/loader', 'role': 'LICENSE',
                                            'count': 1, 'counted_as_coverage': False}]
        new_container = file_container.serialize()
    package[NpkPartID.FILE_CONTAINER].data = new_container
    package[NpkPartID.SQUASHFS].data = new_squashfs
    report['status'] = 'coverage-passed'
    return report


def patch_npk_file(key_dict, kcdsa_private_key, eddsa_private_key, input_file, output_file=None,
                   runtime_policy=None, license_public_key=None):
    npk = NovaPackage.load(input_file)
    if runtime_policy is not None:
        _validate_runtime_policy(npk, key_dict, runtime_policy, license_public_key)
    reports = []
    if len(npk._packages) > 0:
        for package in npk._packages:
            reports.append(patch_npk_package(package, key_dict, runtime_policy, license_public_key))
    else:
        reports.append(patch_npk_package(npk, key_dict, runtime_policy, license_public_key))
    for report in reports:
        print(f"package {report['package']}: {report['status']}")
    npk.sign(kcdsa_private_key, eddsa_private_key)
    npk.save(output_file or input_file)
    return reports


if __name__ == '__main__':
    import argparse
    import os
    parser = argparse.ArgumentParser(description='MikroTik patcher')
    subparsers = parser.add_subparsers(dest="command")
    npk_parser = subparsers.add_parser('npk', help='patch and sign npk file')
    npk_parser.add_argument('input', type=str, help='Input file')
    npk_parser.add_argument('-O', '--output', type=str, help='Output file')
    npk_parser.add_argument('--runtime-policy', choices=[_CHR_RUNTIME_POLICY],
                            help='Explicit version-scoped CHR runtime policy')
    kernel_parser = subparsers.add_parser('kernel', help='patch kernel file')
    kernel_parser.add_argument('input', type=str, help='Input file')
    kernel_parser.add_argument('-O', '--output', type=str, help='Output file')
    block_parser = subparsers.add_parser('block', help='patch block file')
    block_parser.add_argument('dev', type=str, help='block device')
    block_parser.add_argument('file', type=str, help='file path')
    netinstall_parser = subparsers.add_parser(
        'netinstall', help='patch netinstall file')
    netinstall_parser.add_argument('input', type=str, help='Input file')
    netinstall_parser.add_argument(
        '-O', '--output', type=str, help='Output file')
    args = parser.parse_args()
    license_public_key = bytes.fromhex(os.environ['MIKRO_LICENSE_PUBLIC_KEY'])
    key_dict = {
        license_public_key: bytes.fromhex(os.environ['CUSTOM_LICENSE_PUBLIC_KEY']),
        bytes.fromhex(os.environ['MIKRO_NPK_SIGN_PUBLIC_KEY']): bytes.fromhex(os.environ['CUSTOM_NPK_SIGN_PUBLIC_KEY'])
    }
    kcdsa_private_key = bytes.fromhex(os.environ['CUSTOM_LICENSE_PRIVATE_KEY'])
    eddsa_private_key = bytes.fromhex(
        os.environ['CUSTOM_NPK_SIGN_PRIVATE_KEY'])
    if args.command == 'npk':
        print(f'patching {args.input} ...')
        patch_npk_file(key_dict, kcdsa_private_key,
                       eddsa_private_key, args.input, args.output,
                       runtime_policy=args.runtime_policy, license_public_key=license_public_key)
    elif args.command == 'kernel':
        print(f'patching {args.input} ...')
        data = patch_kernel(open(args.input, 'rb').read(), key_dict)
        open(args.output or args.input, 'wb').write(data)
    elif args.command == 'block':
        print(f'patching {args.file} in {args.dev} ...')
        patch_block(args.dev, args.file, key_dict)
    elif args.command == 'netinstall':
        print(f'patching {args.input} ...')
        patch_netinstall(key_dict, args.input, args.output)
    else:
        parser.print_help()
