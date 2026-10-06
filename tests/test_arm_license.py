"""Offline only. Synthetic ELFs/keys; opt-in cache reads, never firmware output.

MIKPATCH_ARM_FIXTURES contains arm/{mode,keyman,loader} and arm64 equivalents.
Actual source words are reconstructed privately; only derived word 3 changes
in memory. No configured key or key digest is read, saved or printed.
"""
import hashlib
import os
from pathlib import Path
import struct
import unittest
from unittest import mock

import arm_license as subject


OLD = struct.pack('<8I', 1, 2, 0xfffffffe, 4, 5, 6, 7, 8)
NEW = OLD[:12] + struct.pack('<I', 0x10004) + OLD[16:]
START = 272
POOLS = tuple(range(416, 444, 4))


def fixture():
    d = bytearray(1224)
    struct.pack_into('<16sHHIIIIIHHHHHH', d, 0,
                     b'\x7fELF\x01\x01\x01'+bytes(9), 2, 40, 1,
                     0x10000, 52, 1024, 0x05000200, 52, 32, 1, 40, 5, 2)
    struct.pack_into('<8I', d, 52, 1, 256, 0x10000, 0x10000, 256, 256, 5, 256)
    d[256:512] = struct.pack('<I', 0xe1a00000)*64
    # Independent A32 instruction encoder/layout: eight stores and one kill.
    words = [0xe59f3088, 0xe5043348, 0xe244ee37, 0xe59f3080,
             0xe1a0c004, 0xe5043344, 0xe59f3078, 0xe5043340,
             0xe2833001, 0xe2833002, 0xe2833003, 0xe504333c,
             0xe59f3064, 0xe5043338, 0xe59f3060, 0xe5043334,
             0xe59f305c, 0xe5043330, 0xe59f3058, 0xe504332c, 0xe8be000f]
    d[START:START+84] = struct.pack('<21I', *words)
    d[416:444] = OLD[:12]+OLD[16:]
    struct.pack_into('<10I', d, 1064, 0, 1, 6, 0x10000, 256, 256, 0, 0, 4, 0)
    struct.pack_into('<10I', d, 1104, 0, 3, 0, 0, 768, 1, 0, 0, 1, 0)
    struct.pack_into('<10I', d, 1144, 0, 9, 0, 0, 800, 8, 4, 1, 4, 8)
    struct.pack_into('<10I', d, 1184, 0, 2, 0, 0, 832, 16, 2, 0, 4, 16)
    return bytes(d), subject._Profile(START, POOLS)


def repin(data, profile):
    return mock.patch.dict(subject._PROFILES, {hashlib.sha256(data).hexdigest(): profile}, clear=True)


def apply(data, match):
    result = bytearray(data)
    for a, b, value in match.writes:
        result[a:b] = value
    return bytes(result)


def reconstruct(data, start):
    """Independent tiny raw A32 evaluator, including modulo arithmetic/stores.

    Only use on the already-validated known layout. Does not call matcher
    immediate decoder, solver, profiles, or key-bearing assertion formatting.
    """
    regs = {}
    stores = {}
    for pos in range(start, start+80, 4):
        w = int.from_bytes(data[pos:pos+4], 'little')
        rd = (w >> 12) & 15
        if w >> 16 == 0xe59f:
            regs[rd] = int.from_bytes(data[pos+8+(w & 4095):pos+12+(w & 4095)], 'little')
        elif w >> 12 == 0xe2833:
            value, rotate = w & 255, ((w >> 8) & 15)*2
            for _ in range(rotate):
                value = (value >> 1) | ((value & 1) << 31)
            regs[3] = (regs[3]+value) % (1 << 32)
        elif w >> 16 == 0xe504:
            stores[-(w & 4095)] = regs[rd]
    return b''.join(stores[-840+4*i].to_bytes(4, 'little') for i in range(8))


class ARMTests(unittest.TestCase):
    def matches(self, data, profile, old=OLD, new=NEW):
        with repin(data, profile):
            return subject.arm_license_matches(data, old, new)

    def reject_word(self, off, value):
        data, profile = fixture()
        altered = bytearray(data)
        struct.pack_into('<I', altered, off, value)
        self.assertEqual(self.matches(bytes(altered), profile), [])

    def test_positive_single_reconstruction_and_exact_footprint(self):
        data, profile = fixture()
        self.assertTrue(reconstruct(data, START) == OLD)
        matches = self.matches(data, profile)
        self.assertEqual(len(matches), 1)
        m = matches[0]
        self.assertEqual(m.count, 1)
        out = apply(data, m)
        self.assertEqual(len(out), len(data))
        self.assertTrue(reconstruct(out, START) == NEW)
        self.assertEqual(out[416:444], data[416:444])
        allowed = {START+i+j for i in (32, 36, 40) for j in (0, 1)}
        self.assertTrue({i for i, (a,b) in enumerate(zip(data,out)) if a != b} <= allowed)
        for offset in (32, 36, 40):
            self.assertEqual(int.from_bytes(out[START+offset:START+offset+4], 'little') & ~4095, 0xe2833000)
        self.assertNotIn('writes=', repr(m))

    def test_every_dependency_byte_is_overlap_protected(self):
        data, profile = fixture()
        m = self.matches(data, profile)[0]
        self.assertEqual(m.envelopes, ((272,356),)+tuple((p,p+4) for p in POOLS))
        for a,b in m.envelopes:
            for i in range(a,b):
                with self.assertRaisesRegex(ValueError, 'overlap'):
                    m.preflight([(i,i+1)])
        m.preflight([(271,272), (356,357), (415,416), (444,445)])
        with self.assertRaisesRegex(ValueError, 'invalid'):
            m.preflight([(3,3)])

    def test_whole_file_pin_and_repatch(self):
        data, profile = fixture()
        self.assertEqual(subject.arm_license_matches(data, OLD, NEW), [])
        with repin(data,profile):
            out = apply(data, subject.arm_license_matches(data, OLD, NEW)[0])
            self.assertEqual(subject.arm_license_matches(out, NEW, OLD), [])
            mutated = data[:-1]+b'X'
            self.assertEqual(subject.arm_license_matches(mutated, OLD, NEW), [])

    def test_no_pool_changes_or_arbitrary_full_key_mapping(self):
        data,profile = fixture()
        for i in list(range(12))+list(range(16,32)):
            new=bytearray(NEW);new[i]^=1
            self.assertEqual(self.matches(data,profile,new=bytes(new)), [])

    def test_wrong_old_and_invalid_types(self):
        data,profile=fixture()
        for old,new in ((NEW,OLD),(OLD,OLD),(None,NEW),(OLD[:-1],NEW),(OLD,NEW[:-1]),(OLD,bytearray(NEW))):
            self.assertEqual(self.matches(data,profile,old,new),[])
        self.assertEqual(subject.arm_license_matches(None,OLD,NEW),[])

    def test_all_truncated_prefixes(self):
        data,profile=fixture()
        for length in range(len(data)):
            self.assertEqual(self.matches(data[:length],profile),[])

    def test_class_endian_machine_flags_headers(self):
        data,profile=fixture()
        for off,value in ((4,2),(5,2),(6,2),(16,3),(18,183),(20,2),(36,1),(40,51),(42,31),(46,39)):
            altered=bytearray(data);altered[off]=value
            self.assertEqual(self.matches(bytes(altered),profile),[])

    def test_metadata_bounds_and_integer_overflow(self):
        for off,value in ((28,1024),(32,0xfffffff0),(32,52),(1064+16,40),
                          (1064+20,0xffffffff),(52+8,0xfffffff0),(52+20,0xffffffff)):
            self.reject_word(off,value)

    def test_executable_ownership_and_aliases(self):
        for off,value in ((1064+8,2),(52+24,4),(52+24,7),(52+8,0x20000),
                          (1064+12,0x20000),(52+16,8),(52+20,4)):
            self.reject_word(off,value)
        data,profile=fixture()
        altered=bytearray(data);altered[1144:1184]=data[1064:1104]
        self.assertEqual(self.matches(bytes(altered),profile),[])
        altered=bytearray(data);struct.pack_into('<H',altered,44,2);altered[84:116]=data[52:84]
        self.assertEqual(self.matches(bytes(altered),profile),[])

    def test_all_instruction_opcode_register_condition_and_flag_mutations(self):
        data,_=fixture()
        for off in range(START,START+84,4):
            word=int.from_bytes(data[off:off+4],'little')
            for bit in (12,16,20,24,28):
                self.reject_word(off,word^(1<<bit))

    def test_unknown_original_arithmetic_or_pool_word(self):
        self.reject_word(START+32,0xe2833004)
        self.reject_word(416,55)

    def test_kill_and_intermediate_value_escape_refused(self):
        self.reject_word(START+80,0xe1a00000)
        self.reject_word(START+36,0xe5833000)  # STR instead of ADD
        self.reject_word(START+36,0xeb000000)  # BL
        self.reject_word(START+36,0xe2933002)  # ADDS changes flags

    def test_shared_and_unaligned_pool_references(self):
        self.reject_word(256,0xe59f0098)  # PC+8+152 = first pool
        self.reject_word(256,0x159f0098)  # conditional LDR
        self.reject_word(256,0xe59f0097)  # overlapping unaligned pool
        self.reject_word(900,0x100a0)    # absolute pool pointer

    def test_branches_symbols_entry_relocations(self):
        for target in (START+4,START+32,START+80,416):
            for opcode in (0xea000000,0xeb000000,0xfa000000,0x1a000000):
                self.reject_word(256,opcode | ((target-264)//4))
        self.reject_word(24,0x10030)
        data,profile=fixture();altered=bytearray(data)
        struct.pack_into('<IIIBBH',altered,832,0,0x10030,4,2,0,1)
        self.assertEqual(self.matches(bytes(altered),profile),[])
        for target in (0x10010,0x1000e,0x10060,0x100a0,0x100a2):
            self.reject_word(800,target)
        for off,value in ((1144+36,12),(1144+20,7),(1144+28,9)):
            self.reject_word(off,value)

    def test_decoder_unavailable_partial_and_wrong_boundaries(self):
        data,profile=fixture()
        with repin(data,profile),mock.patch.dict('sys.modules',{'capstone':None}):
            self.assertEqual(subject.arm_license_matches(data,OLD,NEW),[])
        with repin(data,profile),mock.patch('capstone.Cs') as cs:
            cs.return_value.disasm.return_value=[]
            self.assertEqual(subject.arm_license_matches(data,OLD,NEW),[])
            cs.return_value.disasm.return_value=[mock.Mock(size=2,address=0)]*21
            self.assertEqual(subject.arm_license_matches(data,OLD,NEW),[])

    def test_modified_immediate_exhaustive_roundtrip(self):
        for bits in range(4096):
            value=bits & 255
            for _ in range(((bits>>8)&15)*2):
                value=(value>>1)|((value&1)<<31)
            self.assertEqual(subject._immediate(bits),value)

    def test_carry_wrap_zero_and_three_immediate_budget(self):
        data,profile=fixture()
        for delta in (0,1,2,0x80000000,0xffffff00,0x01020300,0xff0000ff):
            desired=(0xfffffffe+delta)&0xffffffff
            new=OLD[:12]+struct.pack('<I',desired)+OLD[16:]
            m=self.matches(data,profile,new=new)
            self.assertEqual(len(m),1)
            self.assertTrue(reconstruct(apply(data,m[0]),START)==new)
        self.assertIsNone(subject._solve(0x55555555))
        new=OLD[:12]+struct.pack('<I',(0xfffffffe+0x55555555)&0xffffffff)+OLD[16:]
        self.assertEqual(self.matches(data,profile,new=new),[])

    def test_production_is_detached(self):
        import contextlib
        import io
        import patch
        data,profile=fixture()
        stats={}
        with repin(data,profile),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(len(subject.arm_license_matches(data,OLD,NEW)),1)
            out=patch._replace_keys(data,{OLD:NEW},'synthetic',stats)
        self.assertEqual(data,out)
        self.assertFalse(stats)


class VendorReadOnlyTests(unittest.TestCase):
    def test_pinned_sources_in_memory_only(self):
        root=os.environ.get('MIKPATCH_ARM_FIXTURES')
        if not root:
            self.skipTest('MIKPATCH_ARM_FIXTURES unset; no real-source claim')
        data=(Path(root)/'arm'/'mode').read_bytes()
        profile=subject._PROFILES.get(hashlib.sha256(data).hexdigest())
        self.assertIsNotNone(profile,'source pin mismatch')
        old=reconstruct(data,profile.start)
        new=old[:12]+struct.pack('<I',(int.from_bytes(old[8:12],'little')+1)&0xffffffff)+old[16:]
        self.assertTrue(old!=new,'fixture needs a distinct synthetic derived word')
        matches=subject.arm_license_matches(data,old,new)
        self.assertEqual(len(matches),1)
        out=apply(data,matches[0])
        self.assertTrue(reconstruct(out,profile.start)==new)
        allowed={profile.start+o+j for o in (32,36,40) for j in (0,1)}
        self.assertTrue({i for i,(a,b) in enumerate(zip(data,out)) if a!=b} <= allowed)
        self.assertEqual(len(data),len(out))
        self.assertEqual(subject.arm_license_matches(out,new,old),[])
        # Changing even one direct word is unsupported, not a coverage hit.
        self.assertEqual(subject.arm_license_matches(data,old,bytes(range(32))),[])
        for arch in ('arm','arm64'):
            for name in ('keyman','mode','loader'):
                if (arch,name)==('arm','mode'):
                    continue
                other=(Path(root)/arch/name).read_bytes()
                self.assertEqual(subject.arm_license_matches(other,OLD,NEW),[])


if __name__=='__main__':
    unittest.main()
