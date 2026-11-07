#!/usr/bin/env python3
"""Build the owner-signed VerifiedRoot policy for the two SHNGROOT windows.

Format, from kits/VerifiedRoot/src/verified_root.c (read it before changing anything):

  header (160 B)  "VROOT01\0" | u32 version=1 | u32 160 | u32 4096 | u32 flags=0
                  | u64 image_bytes | u64 block_count | u8 volume_uuid[16]
                  | u8 image_sha256[32] | u8 hash_table_sha256[32]
                  | u8 key_sha256[32] | u64 generation
  signature (384 B) RSA-3072 PKCS#1 v1.5 over SHA-256 of the header
  hash table        block_count * SHA-256 of each 4096-byte block (header-only form
                    keeps it in a "<window>.vroot" object of the root image instead)

  key (395 B)     "VROOTKEY" | modulus[384] big endian | exponent 3 (0x010001)

vr_open checks: key magic, modulus top bit (key[8] & 0x80), modulus odd (key[391] & 1),
exponent 0x010001, SHA-256(key) == header[120:152], RSA signature over header[0:160],
block_count == ceil(image_bytes/4096), and generation >= the driver's minimum (1).

This board has no Apple-signed bundle, so the volume UUIDs are read out of the written
root image: the driver compares them against the UUID APFS reports for the media.
"""
import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

HEADER_BYTES = 160
SIGNATURE_BYTES = 384
KEY_BYTES = 395
BLOCK_BYTES = 4096
KEY_MAGIC = b'VROOTKEY'
HEADER_MAGIC = b'VROOT01\0'


def window_uuid(image, offset, size):
    """UUID of the APFS volume inside a window image (GPT partition or bare container)."""
    with open(image, 'rb') as source:
        source.seek(offset)
        head = source.read(0x400)
        start = offset
        if head[510:512] == b'\x55\xaa':
            source.seek(offset + 512)
            gpt = source.read(512)
            if gpt[:8] != b'EFI PART':
                raise SystemExit('window has an MBR but no GPT')
            entry_lba = struct.unpack_from('<Q', gpt, 72)[0]
            count = struct.unpack_from('<I', gpt, 80)[0]
            size_entry = struct.unpack_from('<I', gpt, 84)[0]
            source.seek(offset + entry_lba * 512)
            entries = source.read(count * size_entry)
            for index in range(count):
                entry = entries[index * size_entry:(index + 1) * size_entry]
                if entry[:16] != bytes.fromhex('ef57347c0000aa11aa1100306543ecac'):
                    continue
                start = offset + struct.unpack_from('<Q', entry, 32)[0] * 512
                break
            else:
                raise SystemExit('no APFS partition in the window GPT')
        # The volume superblock sits at an OID the container names; scanning for its magic
        # with the filesystem object type is what the other hosts do too.
        for chunk_start in range(0, min(size, 1 << 30), 64 << 20):
            source.seek(start + chunk_start)
            blob = source.read(64 << 20)
            position = blob.find(b'APSB')
            while position >= 0:
                base = start + chunk_start + position - 32
                source.seek(base)
                volume = source.read(0x200)
                object_type = struct.unpack_from('<I', volume, 24)[0]
                fs_index = struct.unpack_from('<I', volume, 0x24)[0]
                if object_type == 0xd and fs_index < 64:
                    return volume[0xF0:0x100]
                position = blob.find(b'APSB', position + 4)
    raise SystemExit('no APFS volume superblock in the window')


def block_hashes(image, offset, size, table_path):
    count = (size + BLOCK_BYTES - 1) // BLOCK_BYTES
    with open(image, 'rb') as source, open(table_path, 'wb') as table:
        source.seek(offset)
        left = size
        while left:
            take = min(BLOCK_BYTES, left)
            block = source.read(take)
            if len(block) != take:
                raise SystemExit('short read while hashing a window')
            table.write(hashlib.sha256(block).digest())
            left -= take
    return count


def load_key(path):
    modulus = subprocess.run(['openssl', 'rsa', '-in', str(path), '-noout', '-modulus'],
                             check=True, capture_output=True, text=True).stdout.strip()
    text = modulus.split('=', 1)[1]
    raw = bytes.fromhex(text)
    if len(raw) != 384 or not raw[0] & 0x80 or not raw[-1] & 1:
        raise SystemExit('unexpected RSA modulus from openssl')
    return KEY_MAGIC + raw + b'\x01\x00\x01'


def sign(key_path, header):
    return subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(key_path)],
                          input=header, check=True, capture_output=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True, help='userdata root image')
    parser.add_argument('--report', type=Path, required=True, help='userdata-root.json')
    parser.add_argument('--key', type=Path, help='RSA-3072 private key (created if absent); '
                                               'omit with --tables-only to stop before signing')
    parser.add_argument('--tables-only', action='store_true',
                        help='only compute the block hash tables and the window UUIDs')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    if args.tables_only:
        report = json.loads(args.report.read_text())
        for window in report['windows']:
            name, offset, size = window['name'], window['offset'], window['size']
            table_path = args.out / f'{name}.vroot'
            count = block_hashes(args.image, offset, size, table_path)
            uuid = window_uuid(args.image, offset, size)
            print(f'{name}: {size} bytes, {count} blocks, uuid {uuid.hex()}, '
                  f'table {(args.out / (name + ".vroot")).stat().st_size} B')
        return 0
    if not args.key:
        raise SystemExit('--key is required unless --tables-only is given')
    if not args.key.is_file():
        subprocess.run(['openssl', 'genrsa', '-out', str(args.key), '3072'], check=True)
        print(f'generated {args.key}')

    key_blob = load_key(args.key)
    key_path = args.out / 'verified-root-key.bin'
    key_path.write_bytes(key_blob)
    key_sha = hashlib.sha256(key_blob).digest()

    report = json.loads(args.report.read_text())
    windows = report['windows']
    summary = {'key_sha256': key_sha.hex(), 'key_bytes': len(key_blob), 'windows': []}

    for window in windows:
        name, offset, size = window['name'], window['offset'], window['size']
        table_path = args.out / f'{name}.vroot'
        count = block_hashes(args.image, offset, size, table_path)
        table = table_path.read_bytes()
        table_sha = hashlib.sha256(table).digest()
        uuid = window_uuid(args.image, offset, size)

        header = bytearray(HEADER_BYTES)
        header[0:8] = HEADER_MAGIC
        struct.pack_into('<IIII', header, 8, 1, HEADER_BYTES, BLOCK_BYTES, 0)
        struct.pack_into('<QQ', header, 24, size, count)
        header[40:56] = uuid
        header[56:88] = bytes.fromhex(window['sha256'])
        header[88:120] = table_sha
        header[120:152] = key_sha
        struct.pack_into('<Q', header, 152, 1)

        signature = sign(args.key, bytes(header))
        if len(signature) != SIGNATURE_BYTES:
            raise SystemExit(f'signature is {len(signature)} bytes, expected {SIGNATURE_BYTES}')
        policy_path = args.out / f'{name}.policy'
        policy_path.write_bytes(bytes(header) + signature)

        summary['windows'].append({'name': name, 'offset': offset, 'size': size,
                                   'block_count': count, 'uuid': uuid.hex(),
                                   'policy': str(policy_path), 'policy_bytes': policy_path.stat().st_size,
                                   'vroot': str(table_path), 'vroot_bytes': len(table),
                                   'image_sha256': window['sha256']})
        print(f"{name}: {size} bytes, {count} blocks, uuid {uuid.hex()}, "
              f"policy {policy_path.stat().st_size} B, table {len(table)} B")

    (args.out / 'verified-root-policy.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(f'wrote {args.out}/verified-root-policy.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
