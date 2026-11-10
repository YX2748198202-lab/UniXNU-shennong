#!/usr/bin/env python3
"""Read the sheng-log window that package/BootLog.c writes to userdata.

The kernel keeps a bounded log window in the last part of userdata: a 4096-byte
block 0 header (magic "SHLOG001"), ``LogMsgBlocks`` blocks holding the kernel
message buffer oldest byte first, then ``slot_count`` text slots of
``slot_blocks`` blocks each in a ring.  The writer is started by
``package/SourceStorage.cpp`` once the UFS storage stack is up and only when the
payload carries the boot argument ``sheng-log=1``.

Three ways to read it:

* ``--image FILE``  a dump that starts at the window's block 0
  (``dd if=/dev/block/by-name/userdata ...`` or a userdata image),
* ``--image FILE --scan``  any dump large enough to contain the window; the
  header is located by its magic on a 4096-byte boundary,
* ``--device [SERIAL]``  pull the tail of userdata over adb (a recovery/TWRP
  shell is enough, no Android needed).

Nothing here touches the medium: every path is read-only.
"""
import argparse
import json
import struct
import subprocess
import sys
from pathlib import Path

LOG_BLOCK = 4096
LOG_MSG_FIRST = 1
LOG_MSG_BLOCKS = 32
LOG_SLOT_FIRST = 33
LOG_SLOT_BLOCKS = 16
MAGIC = b'SHLOG001'
HEADER = struct.Struct('<8sIIQQ8I6I32s4II2I')
HEADER_FIELDS = (
    'magic', 'version', 'header_bytes', 'boot_id', 'first_lba',
    'window_blocks', 'msg_first', 'msg_blocks', 'msg_bytes',
    'slot_first', 'slot_blocks', 'slot_count', 'slots_written',
    'uptime_s', 'rounds', 'write_errors', 'gpt_open', 'gpt_last', 'state',
    'tag',
    'export_first', 'export_blocks', 'export_bytes', 'export_generation',
    'export_below', 'diag_first', 'diag_bytes',
)
STATE_TEXT = {
    0: 'off (sheng-log not set)',
    1: 'waiting for the window',
    2: 'writing',
    3: 'stopped after write errors',
    4: 'stopped (GPT changed)',
    5: 'header written by boot_log_panic_flush',
}


def parse_header(block):
    if len(block) < HEADER.size:
        raise ValueError(f'header block truncated: {len(block)} < {HEADER.size}')
    values = HEADER.unpack_from(block, 0)
    header = dict(zip(HEADER_FIELDS, values))
    header['magic'] = header['magic'].rstrip(b'\0').decode('ascii', 'replace')
    header['tag'] = header['tag'].split(b'\0', 1)[0].decode('ascii', 'replace')
    return header


def find_window(image, limit=None):
    """Locate the header block inside a dump; returns its offset."""
    if image[:len(MAGIC)] == MAGIC:
        return 0
    start = 0
    while True:
        index = image.find(MAGIC, start)
        if index < 0:
            raise ValueError('no SHLOG001 header in this dump '
                             '(the window was never written, or the dump does not reach it)')
        if index % LOG_BLOCK == 0:
            return index
        start = index + 1


def window_blocks(header):
    blocks = header['window_blocks']
    if blocks < LOG_SLOT_FIRST:
        raise ValueError(f'header window_blocks={blocks} is too small to hold the layout')
    return blocks


def reassemble_msgbuf(window, header):
    """Rebuild the kernel message buffer oldest byte first."""
    msgbuf_off = header['msg_first'] * LOG_BLOCK
    size = header['msg_bytes'] or (header['msg_blocks'] * LOG_BLOCK)
    size = min(size, header['msg_blocks'] * LOG_BLOCK)
    raw = window[msgbuf_off:msgbuf_off + size]
    if not raw:
        return b''
    # BootLog.c copies msgbufp->msg_bufc (a ring) oldest first, so no rotation
    # is needed here: the bytes are already ordered, NUL padded at the tail.
    return raw.split(b'\0', 1)[0]


def slot_texts(window, header):
    texts = []
    count = min(header['slot_count'], header['slots_written'])
    for index in range(count):
        off = (header['slot_first'] + index * header['slot_blocks']) * LOG_BLOCK
        blob = window[off:off + header['slot_blocks'] * LOG_BLOCK]
        text = blob.split(b'\0', 1)[0].decode('utf-8', 'replace')
        texts.append({'index': index, 'text': text})
    return texts


def summarise(window):
    header = parse_header(window)
    if header['magic'] != 'SHLOG001':
        raise ValueError(f'bad magic {header["magic"]!r}')
    blocks = window_blocks(header)
    summary = {
        'header': header,
        'state_text': STATE_TEXT.get(header['state'], f'unknown state {header["state"]}'),
        'window_bytes': blocks * LOG_BLOCK,
        'first_lba': header['first_lba'],
        'written': header['rounds'] > 0,
    }
    summary['msg'] = reassemble_msgbuf(window, header).decode('utf-8', 'replace')
    summary['slots'] = slot_texts(window, header)
    return summary


def read_image(path, scan):
    data = Path(path).read_bytes()
    offset = find_window(data) if scan else 0
    window = data[offset:offset + 64 * 1024 * 1024]
    if len(window) < LOG_SLOT_FIRST * LOG_BLOCK:
        raise ValueError('dump too small: it must reach the header and the msg buffer')
    if window[:len(MAGIC)] != MAGIC:
        # Without --scan the caller promised the dump starts at block 0; a
        # different magic means the offset is wrong, not that the run was quiet.
        raise ValueError('block 0 is not a SHLOG001 header; '
                         'pass --scan when the dump starts before the window')
    return window


def adb(serial, *command):
    prefix = ['adb'] + (['-s', serial] if serial else [])
    result = subprocess.run(prefix + ['shell'] + list(command), capture_output=True, text=False)
    if result.returncode:
        raise RuntimeError(f'adb shell {" ".join(command)} failed: {result.stderr.decode("utf-8", "replace").strip()}')
    return result.stdout


def partition_bytes(serial, node):
    """Size of a block device when the shell can answer, else None."""
    for command in (['blockdev', '--getsize64', node],
                    ['cat', f'/sys/class/block/{Path(node).name}/size']):
        try:
            out = adb(serial, *command).strip()
        except RuntimeError:
            continue
        if out.isdigit():
            value = int(out)
            return value if command[0] == 'blockdev' else value * 512
    return None


def read_device(serial, node, span):
    """Read ``span`` bytes from the end of ``node`` and locate the window."""
    total = partition_bytes(serial, node)
    if total is None:
        raise RuntimeError(f'cannot size {node}; pass --image with a dump instead')
    start = max(0, total - span)
    skip = start // LOG_BLOCK
    count = (total - start) // LOG_BLOCK
    data = adb(serial, 'dd', f'if={node}', f'bs={LOG_BLOCK}', f'skip={skip}',
               f'count={count}', '2>/dev/null')
    offset = find_window(data)
    return data[offset:offset + 64 * 1024 * 1024]


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_argument_group('where to read the window')
    source.add_argument('--image', type=Path, help='dump/image file containing the window')
    source.add_argument('--scan', action='store_true', help='--image: find the header by its magic')
    source.add_argument('--device', nargs='?', const='', metavar='SERIAL',
                        help='read the tail of userdata over adb (no Android needed)')
    source.add_argument('--partition', default='/dev/block/bootdevice/by-name/userdata',
                        help='block device to read with --device')
    source.add_argument('--span-mib', type=int, default=32,
                        help='how much of the partition tail --device reads (default 32)')
    parser.add_argument('--json', action='store_true', help='print the parsed window as JSON')
    parser.add_argument('--msg', action='store_true', help='print the kernel message buffer only')
    args = parser.parse_args()

    if not args.image and args.device is None:
        parser.error('one of --image or --device is required')

    try:
        if args.image:
            window = read_image(args.image, args.scan)
        else:
            window = read_device(args.device or None, args.partition, args.span_mib * 1024 * 1024)
        result = summarise(window)
    except (ValueError, RuntimeError) as error:
        print(f'sheng-log: {error}', file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    header = result['header']
    print(f"sheng-log window: {result['window_bytes']} B, first_lba {header['first_lba']}, "
          f"boot_id {header['boot_id']:#x}")
    print(f"state {header['state']} ({result['state_text']}), rounds {header['rounds']}, "
          f"uptime {header['uptime_s']} s, write_errors {header['write_errors']}, tag {header['tag']!r}")
    if not result['written']:
        print('the writer never completed a round: the payload either lacked sheng-log=1, '
              'or the storage stack did not reach SourceStorage.cpp')
        return 0
    if args.msg or not result['slots']:
        print('--- kernel message buffer ---')
        print(result['msg'])
        return 0
    print('--- kernel message buffer ---')
    print(result['msg'])
    for slot in result['slots']:
        print(f"--- slot {slot['index']} ---")
        print(slot['text'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
