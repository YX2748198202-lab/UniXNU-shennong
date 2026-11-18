import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


seed = load('adt_seed', 'patch-adt-randseed.py')
generator = load('adt_generator', 'make-shennong-adt.py')
node = generator.node


def fixture(value=b'A' * 64):
    return node('device-tree', [('model', b'shennong\0')], [
        node('other', [('opaque', b'chosen\0random-seed\0' + b'x' * 41),
                       ('random-seed', b'DECOY')]),
        node('chosen', [('random-seed', value), ('opaque', b'\x01\x02\x03')],
             [node('memory-map', [('TrustCache', bytes(16)), ('RootPolicies', bytes(16))])])])


class SeedTests(unittest.TestCase):
    def test_grow_preserves_other_records(self):
        before = fixture()
        after, changed = seed.update_seed(before, rng=lambda n: b'B' * n)
        self.assertTrue(changed)
        self.assertEqual(len(after) - len(before), 192)
        old, new = seed.parse_adt(before), seed.validate(after)
        self.assertEqual(old['nodes'], new['nodes'])
        self.assertEqual(seed.other_records(before, old), seed.other_records(after, new))
        r = new['seed']
        self.assertEqual(after[r['value']:r['value'] + 256], b'B' * 256)

    def test_existing_seed_is_unchanged_without_refresh(self):
        data = fixture(b'C' * 256)
        rng = mock.Mock(side_effect=AssertionError('RNG should not run'))
        self.assertEqual(seed.update_seed(data, rng=rng), (data, False))
        rng.assert_not_called()

    def test_refresh_replaces_complete_value(self):
        data = fixture(b'C' * 256)
        result, changed = seed.update_seed(data, refresh=True, rng=lambda n: b'D' * n)
        self.assertTrue(changed)
        r = seed.validate(result)['seed']
        self.assertEqual(result[r['value']:r['value'] + 256], b'D' * 256)

    def test_real_system_rng_refreshes(self):
        a, _ = seed.update_seed(fixture())
        b, _ = seed.update_seed(a, refresh=True)
        ar, br = seed.validate(a)['seed'], seed.validate(b)['seed']
        self.assertNotEqual(a[ar['value']:ar['value'] + 256], b[br['value']:br['value'] + 256])

    def test_check_rejects_old_length(self):
        with self.assertRaisesRegex(ValueError, '64 bytes; expected 256'):
            seed.validate(fixture())

    def test_short_old_seed_alignment(self):
        before = fixture(b'A' * 65)
        after, _ = seed.update_seed(before, rng=lambda n: b'B' * n)
        self.assertEqual(len(after) - len(before), 188)
        seed.validate(after)

    def test_missing_seed(self):
        data = node('root', children=[node('chosen')])
        with self.assertRaisesRegex(ValueError, 'exactly one /chosen/random-seed'):
            seed.parse_adt(data)

    def test_duplicate_seed(self):
        data = node('root', children=[node('chosen', [('random-seed', b'A' * 64), ('random-seed', b'B' * 64)])])
        with self.assertRaisesRegex(ValueError, 'exactly one /chosen/random-seed'):
            seed.parse_adt(data)

    def test_duplicate_chosen(self):
        data = node('root', children=[node('chosen', [('random-seed', b'A' * 64)]), node('chosen')])
        with self.assertRaisesRegex(ValueError, 'exactly one direct /chosen'):
            seed.parse_adt(data)

    def test_nested_chosen_is_not_direct_chosen(self):
        data = node('root', children=[node('other', children=[node('chosen', [('random-seed', b'A' * 64)])])])
        with self.assertRaisesRegex(ValueError, 'exactly one direct /chosen'):
            seed.parse_adt(data)

    def test_truncation_and_trailing_bytes(self):
        for data in [fixture()[:7], fixture()[:-1], fixture() + b'\0']:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                seed.parse_adt(data)

    def test_property_header_must_be_terminated(self):
        data = bytearray(fixture());data[8:40] = b'X' * 32
        with self.assertRaisesRegex(ValueError, 'Unterminated'):
            seed.parse_adt(data)

    def test_invalid_property_length(self):
        data = bytearray(fixture());struct.pack_into('<I', data, 40, 0xffffffff)
        with self.assertRaisesRegex(ValueError, 'exceeds ADT'):
            seed.parse_adt(data)

    def test_missing_alignment_padding(self):
        data = node('root', children=[node('chosen', [('random-seed', b'X')])])[:-1]
        with self.assertRaisesRegex(ValueError, 'alignment'):
            seed.parse_adt(data)

    def test_invalid_counts(self):
        for offset in [0, 4]:
            data = bytearray(fixture());struct.pack_into('<I', data, offset, 0xffffffff)
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                seed.parse_adt(data)

    def test_excessive_depth(self):
        child = node('leaf')
        for _ in range(66):child = node('nested', children=[child])
        data = node('root', children=[node('chosen', [('random-seed', b'A' * 64)]), child])
        with self.assertRaisesRegex(ValueError, 'depth'):
            seed.parse_adt(data)

    def test_duplicate_node_name_property(self):
        data = node('root', children=[node('chosen', [('name', b'chosen\0'), ('random-seed', b'A' * 64)])])
        with self.assertRaisesRegex(ValueError, 'duplicate node name'):
            seed.parse_adt(data)

    def test_invalid_target_sizes(self):
        for n in [-4, 0, 64, 255, 257, 0x100000000]:
            with self.subTest(size=n), self.assertRaises(ValueError):
                seed.update_seed(fixture(), n)

    def test_invalid_entropy_results(self):
        for value in [b'X' * 255, bytes(256), b'C' * 256, None]:
            with self.subTest(kind=type(value).__name__), self.assertRaises(ValueError):
                seed.update_seed(fixture(b'C' * 256), refresh=True, rng=lambda n: value)

    def invoke(self, path, *flags):
        with mock.patch.object(sys, 'argv', ['patch-adt-randseed.py', str(path), *flags]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return seed.main()

    def test_check_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';p.write_bytes(fixture(b'C' * 256))
            before = p.stat().st_mtime_ns
            self.assertEqual(self.invoke(p, '--check'), 0)
            self.assertEqual(p.stat().st_mtime_ns, before)

    def test_rng_failure_preserves_input(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';data = fixture();p.write_bytes(data)
            with mock.patch.object(seed.os, 'urandom', side_effect=OSError('test entropy failure')):
                self.assertEqual(self.invoke(p), 1)
            self.assertEqual(p.read_bytes(), data)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_malformed_input_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';data = fixture()[:-1];p.write_bytes(data)
            self.assertEqual(self.invoke(p), 1)
            self.assertEqual(p.read_bytes(), data)

    def test_atomic_write_readback_and_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';p.write_bytes(fixture());p.chmod(0o640)
            self.assertEqual(self.invoke(p), 0)
            seed.validate(p.read_bytes());self.assertEqual(p.stat().st_mode & 0o777, 0o640)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_atomic_failure_preserves_file(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';data = fixture();p.write_bytes(data)
            after, _ = seed.update_seed(data)
            with mock.patch.object(seed.os, 'replace', side_effect=OSError('test replace failure')):
                with self.assertRaises(OSError):seed.atomic_replace(p, data, after)
            self.assertEqual(p.read_bytes(), data)
            self.assertEqual(len(list(Path(directory).iterdir())), 1)

    def test_concurrent_preimage_change_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';before = fixture();p.write_bytes(b'concurrent writer')
            after, _ = seed.update_seed(before)
            with self.assertRaisesRegex(ValueError, 'Input changed'):
                seed.atomic_replace(p, before, after)
            self.assertEqual(p.read_bytes(), b'concurrent writer')

    def test_symlink_input_is_not_modified(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'tree.adt';data = fixture();p.write_bytes(data)
            link = Path(directory) / 'link.adt';link.symlink_to(p)
            self.assertEqual(self.invoke(link), 1)
            self.assertEqual(p.read_bytes(), data)


class GeneratorWorkflowTests(unittest.TestCase):
    def test_generator_requests_256_and_preserves_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'generated.adt'
            with mock.patch.object(sys, 'argv', ['make-shennong-adt.py', '--output', str(p), '--dram-size', '0x10000000', '--trust-cache', '--root-policies']), mock.patch.object(generator.os, 'urandom', return_value=b'G' * 256) as rng, contextlib.redirect_stdout(io.StringIO()):
                generator.main()
            rng.assert_called_once_with(256)
            tree = seed.validate(p.read_bytes())
            slots = [r['name'] for r in tree['records'] if r['path'] == ('chosen', 'memory-map')]
            self.assertIn('TrustCache', slots);self.assertIn('RootPolicies', slots)

    def test_generator_rng_failure_has_no_output(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'generated.adt'
            with mock.patch.object(sys, 'argv', ['make-shennong-adt.py', '--output', str(p), '--dram-size', '0x10000000']), mock.patch.object(generator.os, 'urandom', side_effect=OSError('test entropy failure')):
                with self.assertRaises(OSError):generator.main()
            self.assertFalse(p.exists())

    def test_ci_checks_generated_and_roundtrip_seed(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/kernel.yml').read_text())
        block = next(s['run'] for s in workflow['jobs']['kernel']['steps'] if 'make-shennong-adt.py' in s.get('run', ''))
        self.assertEqual(block.count('patch-adt-randseed.py'), 2)
        first = block.index('patch-adt-randseed.py')
        write = block.index('mcopy -o -i "$PAY" "$ADT"')
        second = block.index('patch-adt-randseed.py', first + 1)
        self.assertLess(first, write);self.assertGreater(second, write)
        self.assertEqual(block.count('--check'), 2)

    def test_workflow_shell_blocks_parse(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/kernel.yml').read_text())
        blocks = [s['run'] for s in workflow['jobs']['kernel']['steps'] if 'run' in s]
        for n, block in enumerate(blocks):
            result = subprocess.run(['bash', '-n'], input=block, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, f'block {n}: {result.stderr}')


if __name__ == '__main__':unittest.main()
