#!/usr/bin/env python3
"""Build a synthetic sheng-log window and check that the reader parses it.

The real window only exists after a boot with ``sheng-log=1`` on a device whose
storage stack reached ``package/SourceStorage.cpp``.  Until then the reader can
still be pinned by a fixture whose layout is copied field for field from
``struct boot_log_header`` in ``package/BootLog.c``.

Usage: scripts/test-read-sheng-log.py
"""
import importlib.util
import io
import struct
import sys
import tempfile
from contextlib import redirect_stderr
from pathlib import Path

HERE = Path(__file__).resolve().parent
READER = HERE / 'read-sheng-log.py'


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_window(reader, *, msg=b'kernel: hello from the trampoline\n',
                 slots=('slot one text', 'slot two text'), written=None,
                 rounds=3, state=2):
    blocks = reader.LOG_SLOT_FIRST + len(slots) * reader.LOG_SLOT_BLOCKS
    window = bytearray(blocks * reader.LOG_BLOCK)
    tag = b'diag'
    header = reader.HEADER.pack(
        reader.MAGIC + b'\0' * (8 - len(reader.MAGIC)), 4, reader.HEADER.size,
        0x1234ABCD, 0x2A0000,
        blocks, reader.LOG_MSG_FIRST, reader.LOG_MSG_BLOCKS, len(msg),
        reader.LOG_SLOT_FIRST, reader.LOG_SLOT_BLOCKS, len(slots),
        len(slots) if written is None else written,
        42, rounds, 0, 1, 0, state,
        tag + b'\0' * (32 - len(tag)),
        0, 0, 0, 0, 0, 0, 0,
    )
    assert len(header) == reader.HEADER.size, (len(header), reader.HEADER.size)
    window[0:len(header)] = header
    msg_off = reader.LOG_MSG_FIRST * reader.LOG_BLOCK
    window[msg_off:msg_off + len(msg)] = msg
    for index, text in enumerate(slots):
        off = (reader.LOG_SLOT_FIRST + index * reader.LOG_SLOT_BLOCKS) * reader.LOG_BLOCK
        raw = text.encode()
        window[off:off + len(raw)] = raw
    return bytes(window)


def main():
    reader = load(READER, 'read_sheng_log')
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(name)
            print(f'FAIL {name}: got {got!r}, want {want!r}')
        else:
            print(f'ok   {name}')

    window = build_window(reader)
    result = reader.summarise(window)
    check('magic', result['header']['magic'], 'SHLOG001')
    check('version', result['header']['version'], 4)
    check('tag', result['header']['tag'], 'diag')
    check('state text', result['state_text'], 'writing')
    check('window bytes', result['window_bytes'], len(window))
    check('written', result['written'], True)
    check('msg text', result['msg'], 'kernel: hello from the trampoline\n')
    check('slot count', len(result['slots']), 2)
    check('slot 0', result['slots'][0]['text'], 'slot one text')

    # A window that was opened but never written must say so instead of
    # printing an empty log as if the kernel had been silent.
    quiet = reader.summarise(build_window(reader, msg=b'', slots=(), written=0, rounds=0, state=1))
    check('never written', quiet['written'], False)
    check('state waiting', quiet['state_text'], 'waiting for the window')

    # --scan must find the header when the dump starts earlier than the window.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'userdata-tail.img'
        prefix = b'\x5a' * (7 * reader.LOG_BLOCK)
        path.write_bytes(prefix + window)
        scanned = reader.summarise(reader.read_image(path, scan=True))
        check('scan msg', scanned['msg'], 'kernel: hello from the trampoline\n')
        try:
            reader.read_image(path, scan=False)
            failures.append('unscanned read accepted a shifted window')
            print('FAIL unscanned read accepted a shifted window')
        except ValueError:
            print('ok   unscanned read rejects a shifted window')

    stderr = io.StringIO()
    with redirect_stderr(stderr), tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'random.img'
        path.write_bytes(b'\x00' * (reader.LOG_SLOT_FIRST * reader.LOG_BLOCK))
        code = reader.main.__wrapped__() if hasattr(reader.main, '__wrapped__') else None
        del code
        try:
            reader.read_image(path, scan=True)
            failures.append('a dump without a header was accepted')
            print('FAIL a dump without a header was accepted')
        except ValueError as error:
            check('missing header message', 'SHLOG001' in str(error), True)

    print()
    if failures:
        print(f'{len(failures)} failure(s)')
        return 1
    print('sheng-log reader: all checks passed')
    return 0


if __name__ == '__main__':
    sys.exit(main())
