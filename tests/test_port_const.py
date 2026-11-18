#!/usr/bin/env python3
"""Count-checked source changes plus real-fileset layout regression tests.

Set PORT_CONST_LAYOUT_SOURCE and PORT_CONST_KERNEL for integration tests. No
Apple source/binary is vendored into this repository. Fixtures are read-only.
"""
import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('port_const', ROOT/'scripts/apply-port-const.py')
port = importlib.util.module_from_spec(spec)
spec.loader.exec_module(port)


def fixture_source():
    # Minimal exact contexts, plus lifecycle paths that must stay unchanged.
    return '\n\n'.join(old for _, old, _ in port.ARM_REPLACEMENTS) + '''
arm_vm_page_granular_RNX(segKLDDATAB, segSizeKLDDATA, 0);
for (vm_offset_t va = segKLDDATAB; va < (segKLDDATAB + segSizeKLDDATA); va += ARM_PGBYTES) {
    *pte = ARM_PTE_EMPTY;
}
flush_mmu_tlb();
'''


class SourceTests(unittest.TestCase):
    def test_complete_idempotent_transform(self):
        result = port.transform(fixture_source(), port.ARM_REPLACEMENTS)
        self.assertEqual(result, port.transform(result, port.ARM_REPLACEMENTS))
        for _, _, new in port.ARM_REPLACEMENTS:
            self.assertEqual(result.count(new), 1)

    def test_missing_context_fails(self):
        source = fixture_source().replace(port.ARM_REPLACEMENTS[0][1], 'changed upstream')
        with self.assertRaises(ValueError):
            port.transform(source, port.ARM_REPLACEMENTS)

    def test_ambiguous_context_fails(self):
        source = fixture_source() + port.ARM_REPLACEMENTS[0][1]
        with self.assertRaises(ValueError):
            port.transform(source, port.ARM_REPLACEMENTS)

    def test_preserves_kld_unmap_and_readonly(self):
        result = port.transform(fixture_source(), port.ARM_REPLACEMENTS)
        self.assertIn('arm_vm_page_granular_RNX(segKLDDATAB, segSizeKLDDATA, 0);', result)
        self.assertIn('va < (segKLDDATAB + segSizeKLDDATA)', result)
        self.assertNotIn('arm_vm_page_granular_RWNX(segKLDDATAB', result)
        self.assertLess(result.index('arm_vm_page_granular_RNX(segPORTCONSTB'), result.index('__builtin_arm_dsb'))
        self.assertIn('segPORTCONSTB, segSizePORTCONST, AP_RONA, 0', result)

    def test_prepare_uses_hidden_compile_tree_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = root/'.cache/xnu-work/osfmk/arm64/arm_vm_init.c'
            ref = root/'refer/xnu/osfmk/arm64/arm_vm_init.c'
            for path in [work, ref]:
                path.parent.mkdir(parents=True)
                path.write_text(fixture_source())
            make = root/'.cache/xnu-work/makedefs/MakeInc.def'
            make.parent.mkdir(parents=True)
            make.write_text(port.MAKEDEF_OLD + '\n')
            ledger = root/'.cache/xnu-work/osfmk/kern/ledger.c'
            ledger.parent.mkdir(parents=True)
            ledger.write_text(port.LEDGER_OLD + '\n')
            original = ref.read_bytes()
            port.run('prepare', root)
            first = work.read_bytes()
            self.assertNotEqual(first, original)
            self.assertEqual(ref.read_bytes(), original)
            port.run('prepare', root)
            self.assertEqual(work.read_bytes(), first)
            self.assertEqual(len(list((root/'build/shennong-port-const').glob('*.json'))), 2)

    def test_missing_compile_tree_never_falls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ref = root/'refer/xnu/osfmk/arm64/arm_vm_init.c'
            ref.parent.mkdir(parents=True)
            ref.write_text(fixture_source())
            with self.assertRaises(ValueError):
                port.run('prepare', root)
            self.assertEqual(ref.read_text(), fixture_source())

    def test_obsolete_hook_fails_closed(self):
        with self.assertRaises(ValueError):
            port.install_hook('def shennong_kld_writable(): pass')
        text = port.install_hook('print("headers restored")\n')
        self.assertEqual(text, port.install_hook(text))


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('port_audit', ROOT/'scripts/audit-port-const-kernel.py')
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def binary(self, protection=3, version=0x7f):
        # One non-executable custom segment, a real __const section, and v2 marker.
        offset, address = 0x1000, 0x100000000
        command = struct.pack('<II16sQQQQIIII', 0x19, 152, b'__PORT_CONST', address, 0x1000, offset, 0x1000, protection, protection, 1, 0)
        section = struct.pack('<16s16sQQIIIIIIII', b'__const', b'__PORT_CONST', address, 16, offset, 3, 0, 0, 0, 0, 0, 0)
        split = struct.pack('<IIII', 0x1e, 16, 0x2000, 2)
        header = struct.pack('<8I', 0xfeedfacf, 0x100000c, 0, 2, 2, len(command)+len(section)+len(split), 0, 0)
        data = header + command + section + split
        return data + bytes(0x2000-len(data)) + bytes([version, 0])

    def test_symbol_reader_ignores_unrelocated_stabs(self):
        image = self.module.MachO(self.binary())
        at = len(image.data)
        symoff, stroff = at + 24, at + 24 + 32
        strings = b'\0_local_state\0'
        records = (struct.pack('<IBBHQ', 1, 0x0e, 1, 0, 0x1110) +
                   struct.pack('<IBBHQ', 1, 0x26, 1, 0, 0x2220))
        image.data += struct.pack('<6I', 2, 24, symoff, 2, stroff, len(strings)) + records + strings
        image.commands[2] = at
        self.assertEqual(image.symbols()['_local_state'], 0x1110)

    def test_valid_segment_and_split_payload(self):
        image = self.module.MachO(self.binary())
        self.assertEqual(image.port_segment()['initprot'], 3)
        self.assertEqual(image.split_info()['size'], 2)

    def test_executable_segment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'RW/NX'):
            self.module.MachO(self.binary(7)).port_segment()

    def test_non_v2_split_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'v2'):
            self.module.MachO(self.binary(version=1)).split_info()

    def test_missing_split_is_rejected(self):
        image = self.module.MachO(self.binary())
        del image.commands[0x1e]
        with self.assertRaisesRegex(ValueError, 'Missing LC_SEGMENT'):
            image.split_info()

    def test_truncated_commands_are_rejected(self):
        with self.assertRaises(ValueError):
            self.module.MachO(self.binary()[:60])

    def test_original_fi135_has_no_new_segment(self):
        path = os.environ.get('PORT_CONST_KERNEL')
        if not path:
            self.skipTest('Set PORT_CONST_KERNEL')
        image = self.module.MachO(Path(path).read_bytes())
        with self.assertRaisesRegex(ValueError, 'Missing or empty'):
            image.port_segment()

    def test_segment_order_patch_is_idempotent(self):
        replacements = [('segment-order', port.MAKEDEF_OLD, port.MAKEDEF_NEW)]
        first = port.transform(port.MAKEDEF_OLD, replacements)
        self.assertEqual(first, port.transform(first, replacements))
        self.assertIn('__KLDDATA:__PORT_CONST:__DATA', first)

    def test_prepare_failure_does_not_partially_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'.cache/xnu-work/osfmk/arm64/arm_vm_init.c'
            source.parent.mkdir(parents=True)
            source.write_text(fixture_source())
            with self.assertRaises(FileNotFoundError):
                port.run('prepare', root)
            self.assertEqual(source.read_text(), fixture_source())


class LayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = os.environ.get('PORT_CONST_LAYOUT_SOURCE')
        kernel = os.environ.get('PORT_CONST_KERNEL')
        if not source or not kernel:
            raise unittest.SkipTest('Set PORT_CONST_LAYOUT_SOURCE and PORT_CONST_KERNEL for real-fileset tests')
        source = Path(source)
        sys.path.insert(0, str(source.parent))
        from kc_image import Image
        cls.source = source.read_text()
        cls.original = types.ModuleType('original_layout')
        cls.patched = types.ModuleType('patched_layout')
        exec(compile(cls.source, str(source), 'exec'), cls.original.__dict__)
        changed = port.transform(cls.source, [('layout', port.LAYOUT_OLD, port.LAYOUT_NEW)])
        exec(compile(changed, str(source)+'+port-const', 'exec'), cls.patched.__dict__)
        data = Path(kernel).read_bytes()
        cls.cache_image = Image(data)
        cls.native_image = Image(data, cls.cache_image.entries['com.apple.kernel'][1])

    def inputs(self, with_port=False):
        # Use actual retained kexts and segment geometry; irrelevant link-table
        # sizing is stubbed because these tests exercise placement/translation.
        cache = types.SimpleNamespace(data=self.cache_image.data, base=self.cache_image.base,
                                      segments=[dict(s) for s in self.cache_image.segments],
                                      entries=self.cache_image.entries, fixups=lambda: [])
        segs = [dict(s) for s in self.native_image.segments]
        sections = [dict(s) for s in self.native_image.sections]
        if with_port:
            end_va = max(s['va']+s['size'] for s in segs)
            end_file = max(s['fileoff']+s['filesize'] for s in segs)
            segs.append(dict(name=port.SEGMENT, va=self.patched.align(end_va),
                             size=0xc0000, fileoff=self.patched.align(end_file), filesize=0xc0000))
            sections.append(dict(name='__const', segment=port.SEGMENT, va=segs[-1]['va'], size=0xbe9a0))
        native = types.SimpleNamespace(segments=segs, sections=sections, base=self.native_image.base,
                                       fixups=lambda: [], function_starts=lambda: [])
        return cache, native

    def test_no_new_segment_is_exact_regression(self):
        cache, native = self.inputs()
        old = self.original.Layout(cache, native, None)
        new = self.patched.Layout(cache, native, None)
        self.assertEqual(old.describe(), new.describe())
        self.assertEqual(old.roots, new.roots)
        self.assertEqual(old.size, new.size)

    def test_resident_segment_precedes_bootdata_without_overlap(self):
        cache, native = self.inputs(True)
        layout = self.patched.Layout(cache, native, None)
        layout.validate()
        self.assertLessEqual(layout.end(port.SEGMENT), layout.placements['__KLDDATA'])
        self.assertLessEqual(layout.end('__KLDDATA'), layout.placements['__BOOTDATA'])
        self.assertIn(port.SEGMENT, layout.roots)
        self.assertEqual(layout.roots[port.SEGMENT]['fileoff'], layout.placements[port.SEGMENT]-cache.base)

    def test_translation_section_and_file_mapping(self):
        cache, native = self.inputs(True)
        layout = self.patched.Layout(cache, native, None)
        segment = next(s for s in native.segments if s['name'] == port.SEGMENT)
        for offset in [0, 0x281f0, 0xbe99f]:
            expected = layout.placements[port.SEGMENT] + offset
            self.assertEqual(layout.translate(segment['va']+offset), expected)
            self.assertEqual(layout.section_address(len(native.sections), offset, new=True), expected)
            self.assertEqual(layout.file(segment['fileoff']+offset), expected-cache.base)

    def test_overlap_is_rejected(self):
        cache, native = self.inputs(True)
        layout = self.patched.Layout(cache, native, None)
        layout.placements[port.SEGMENT] = layout.placements['__DATA']
        with self.assertRaisesRegex(ValueError, 'overlap'):
            layout.validate()

    def test_unclassified_segment_is_rejected(self):
        cache, native = self.inputs(True)
        native.segments[-1]['name'] = '__UNKNOWN_CONST'
        with self.assertRaisesRegex(ValueError, 'Unclassified native segment'):
            self.patched.Layout(cache, native, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
