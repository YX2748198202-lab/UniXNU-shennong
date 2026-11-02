#!/usr/bin/env python3
"""Stop the original AppleARMCPU driver from claiming the /cpus nodes.

Why this patch
--------------
AppleARMPlatform.kext ships a CPU class whose personality carries
``IONameMatch = "cpu"``. IODTPlatformExpert compares IONameMatch by prefix, so
that personality also matches ``cpu0`` (and the ``cpus`` container node). When
it wins the match it runs its own Apple device-tree validation and panics:

    "CPU configuration in device tree is invalid" @AppleARMCPU.cpp:111

That validation wants /cpus/max_cpus and the per-CPU cpu-id, interrupts and
function-* properties of a real Apple device tree, which a Qualcomm ADT does not
carry and which the native ArmCpu component replaces. Rewriting the
personality's IONameMatch from ``cpu`` to ``xpu`` makes the Apple class match
nothing while the native ArmCpu keeps the nubs. ``cpu`` and ``xpu`` are the same
length, so the patch is a three-byte, in-place substitution: no offset, load
command, prelink index or code byte moves.

Other UniXNU ports use the same fix (rmx1971, mondrian, sirius); citations are in
docs/handoff/BRINGUP-STATUS.md.

What it operates on
-------------------
``--image``    v0 Android boot image (the shippable artifact). The payload FAT
               volume is extracted, ``::/EFI/UniXNU/Payloads/kernel.macho`` is
               patched inside it, and the image is repacked with its own header
               and kernel area. Output size equals input size.
``--payload``  payload FAT volume produced by ``unixnu payload``.
``--macho``    a bare kernel.macho (prelink output).

The prelink metadata in kernel.macho is ElementTree-serialised (root ``<dict>``,
no ``<plist>`` wrapper), so it is parsed with ElementTree, not plistlib. Every
mode re-reads and re-parses its result before reporting success.

Requires mtools (``mcopy``) for the ``--payload`` and ``--image`` modes.

Usage
-----
    # dry run on the artifact that is already on the phone
    python3 scripts/patch-applearmcpu-ioname.py --image Mu-shennong-smp.img --check

    # produce the patched boot image (same size, only the personality changed)
    python3 scripts/patch-applearmcpu-ioname.py \
        --image Mu-shennong-smp.img --out Mu-shennong-xpu.img \
        --report Mu-shennong-xpu.json

    # patch a payload before packing it
    python3 scripts/patch-applearmcpu-ioname.py --payload payload.img --out payload-xpu.img

    # reproduce the offline verification without any artifact
    python3 scripts/patch-applearmcpu-ioname.py --self-test
"""

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

MH_MAGIC_64 = 0xFEEDFACF
CPU_TYPE_ARM64 = 0x0100000C
LC_SEGMENT_64 = 0x19
PRELINK_SEGMENT = '__PRELINK_INFO'
KEXTS_KEY = '_PrelinkInfoDictionary'
ARM_PLATFORM = 'com.apple.driver.AppleARMPlatform'
CPU_CLASS = 'AppleARMCPU'
KERNEL_IN_PAYLOAD = '::/EFI/UniXNU/Payloads/kernel.macho'
OLD_MATCH = 'cpu'
NEW_MATCH = 'xpu'
OLD_BYTES = OLD_MATCH.encode()
NEW_BYTES = NEW_MATCH.encode()
# "cpu" -> "xpu" shares two bytes; only the first character changes.
EXPECTED_CHANGED_BYTES = sum(1 for one, two in zip(OLD_BYTES, NEW_BYTES) if one != two)

IO_CLASS_PATTERN = re.compile(
    rb'<key>IOClass</key>\s*<string>([A-Za-z0-9_]+)</string>')
IO_NAME_MATCH_PATTERN = re.compile(
    rb'<key>IONameMatch</key>\s*<string>([A-Za-z0-9_,.\- ]*)</string>')
IO_NAME_MATCH_ARRAY = re.compile(
    rb'<key>IONameMatch</key>\s*<array>\s*<string>([A-Za-z0-9_,.\- ]*)</string>\s*</array>')
DICT_TOKEN = re.compile(rb'<dict>|</dict>')


class Error(Exception):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# Mach-O
# ---------------------------------------------------------------------------

def macho_segments(data):
    """Return {'segments': [{'name', 'va', 'size', 'fileoff', 'filesize', ...}]}."""
    if len(data) < 32:
        raise Error('image is shorter than a Mach-O header')
    magic, cputype, _cpusubtype, kind, ncmds, sizeofcmds = struct.unpack_from('<6I', data, 0)
    if magic != MH_MAGIC_64:
        raise Error('not a little-endian 64-bit Mach-O (magic %#x)' % magic)
    if cputype != CPU_TYPE_ARM64:
        raise Error('not an ARM64 Mach-O (cputype %#x)' % cputype)
    if 32 + sizeofcmds > len(data):
        raise Error('load commands run past the end of the file')
    segments = []
    offset = 32
    end = 32 + sizeofcmds
    for _ in range(ncmds):
        if offset + 8 > end:
            raise Error('truncated load command')
        command, length = struct.unpack_from('<II', data, offset)
        if length < 8 or offset + length > end:
            raise Error('invalid load command extent at %#x' % offset)
        if command == LC_SEGMENT_64:
            if length < 72:
                raise Error('truncated segment command at %#x' % offset)
            (name, va, size, fileoff, filesize,
             _maxprot, _initprot, nsects, _flags) = struct.unpack_from('<16s4Q4I', data, offset + 8)
            if length != 72 + 80 * nsects:
                raise Error('segment command length does not match its section count')
            if filesize > size:
                raise Error('segment %r filesize exceeds vmsize' % name.rstrip(b'\0'))
            sections = []
            for index in range(nsects):
                at = offset + 72 + index * 80
                sectname = data[at:at + 16].rstrip(b'\0').decode('ascii', 'replace')
                addr, sect_size, sect_off = struct.unpack_from('<QQI', data, at + 32)
                sections.append({'name': sectname, 'va': addr, 'size': sect_size,
                                 'fileoff': sect_off})
            segments.append({'name': name.rstrip(b'\0').decode('ascii', 'replace'),
                             'va': va, 'size': size, 'fileoff': fileoff,
                             'filesize': filesize, 'sections': sections})
        offset += length
    if offset != end:
        raise Error('load command sizes do not add up to sizeofcmds')
    return {'kind': kind, 'segments': segments}


def prelink_xml_span(data):
    """Return (start, end) of the prelink metadata inside the image."""
    for segment in macho_segments(data)['segments']:
        if segment['name'] != PRELINK_SEGMENT:
            continue
        start = segment['fileoff']
        end = start + segment['filesize']
        if end > len(data):
            raise Error('__PRELINK_INFO segment runs past the end of the file')
        return start, end
    raise Error('image has no __PRELINK_INFO segment')


def parse_prelink_xml(blob):
    """Parse the prelink metadata. Accepts the ElementTree form and <plist>."""
    root = ET.fromstring(blob)
    if root.tag == 'plist':
        children = list(root)
        if len(children) != 1:
            raise Error('<plist> wrapper does not hold exactly one object')
        root = children[0]
    if root.tag != 'dict':
        raise Error('prelink metadata root is <%s>, expected <dict>' % root.tag)
    return root


def xml_value(element):
    if element.tag in ('string', 'key'):
        return element.text or ''
    if element.tag == 'integer':
        return int(element.text or '0', 0)
    if element.tag in ('true', 'false'):
        return element.tag == 'true'
    raise Error('unexpected <%s> where a scalar was expected' % element.tag)


def dict_of(element):
    if element.tag != 'dict':
        raise Error('expected <dict>, got <%s>' % element.tag)
    children = list(element)
    if len(children) % 2:
        raise Error('odd number of children in a <dict>')
    return {xml_value(children[index]): children[index + 1]
            for index in range(0, len(children), 2)}


def kext_entries(root):
    dictionary = dict_of(root)
    value = dictionary.get(KEXTS_KEY)
    if value is None or value.tag != 'array':
        raise Error('prelink metadata has no %s array' % KEXTS_KEY)
    return list(value)


def apple_platform_entry(root):
    for entry in kext_entries(root):
        identifier = dict_of(entry).get('CFBundleIdentifier')
        if identifier is not None and xml_value(identifier) == ARM_PLATFORM:
            return entry
    raise Error('%s is not in the prelink metadata' % ARM_PLATFORM)


def personality_report(entry):
    """List {personality, IOClass, IONameMatch} for one kext's personalities."""
    personalities = dict_of(entry).get('IOKitPersonalities')
    if personalities is None or personalities.tag != 'dict':
        return []
    found = []
    for name, body in dict_of(personalities).items():
        if body.tag != 'dict':
            continue
        props = dict_of(body)
        io_class = xml_value(props['IOClass']) if 'IOClass' in props else None
        match = props.get('IONameMatch')
        if match is None:
            value = None
        elif match.tag == 'string':
            value = xml_value(match)
        elif match.tag == 'array':
            value = [xml_value(child) for child in match]
        else:
            value = None
        found.append({'personality': name, 'IOClass': io_class, 'IONameMatch': value})
    return found


def diff_trees(before, after, path=()):
    """Return [(path, before_value, after_value)] for every structural change."""
    changes = []
    if before.tag != after.tag:
        return [(path + ('tag',), before.tag, after.tag)]
    if before.tag == 'dict':
        left, right = dict_of(before), dict_of(after)
        if list(left) != list(right):
            return [(path + ('keys',), list(left), list(right))]
        for key in left:
            changes += diff_trees(left[key], right[key], path + (key,))
    elif before.tag == 'array':
        left, right = list(before), list(after)
        if len(left) != len(right):
            return [(path + ('len',), len(left), len(right))]
        for index, (one, two) in enumerate(zip(left, right)):
            changes += diff_trees(one, two, path + (index,))
    elif before.tag == 'data':
        one = ''.join((before.text or '').split())
        two = ''.join((after.text or '').split())
        if one != two:
            changes.append((path, one, two))
    else:
        one, two = xml_value(before), xml_value(after)
        if one != two:
            changes.append((path, one, two))
    return changes


def _enclosing_dict(blob, position):
    """Bounds of the innermost <dict> that contains `position`."""
    stack = []
    for match in DICT_TOKEN.finditer(blob, 0, position):
        if match.group(0) == b'<dict>':
            stack.append(match.start())
        elif stack:
            stack.pop()
    if not stack:
        raise Error('no enclosing <dict> for offset %#x' % position)
    start = stack[-1]
    depth = 0
    for match in DICT_TOKEN.finditer(blob, start):
        depth += 1 if match.group(0) == b'<dict>' else -1
        if depth == 0:
            return start, match.start()
    return start, len(blob)


def locate_cpu_match(xml):
    """Find the IONameMatch "cpu" of the AppleARMCPU personality.

    The scan is scoped to the <dict> that holds ``IOClass AppleARMCPU`` so a
    "cpu" string belonging to another kext or personality is never touched; the
    structural re-parse after patching proves the choice was the right one.
    """
    hits = []
    for match in IO_CLASS_PATTERN.finditer(xml):
        if match.group(1).decode() != CPU_CLASS:
            continue
        scope_start, scope_end = _enclosing_dict(xml, match.start())
        scope = xml[scope_start:scope_end]
        for pattern in (IO_NAME_MATCH_PATTERN, IO_NAME_MATCH_ARRAY):
            for candidate in pattern.finditer(scope):
                if candidate.group(1).decode() != OLD_MATCH:
                    continue
                hits.append({'offset': scope_start + candidate.start(1),
                             'IOClass': CPU_CLASS, 'value': OLD_MATCH})
    return hits


def patch_kernel_macho(data):
    """Patch kernel.macho bytes. Returns (patched_bytes, report)."""
    start, end = prelink_xml_span(data)
    xml = data[start:end].split(b'\0', 1)[0]
    if not xml:
        raise Error('__PRELINK_INFO is empty')
    root = parse_prelink_xml(xml)

    personalities = personality_report(apple_platform_entry(root))
    cpu = [item for item in personalities if item['IOClass'] == CPU_CLASS]
    if not cpu:
        raise Error('kext %s has no %s personality' % (ARM_PLATFORM, CPU_CLASS))
    if cpu[0]['IONameMatch'] in (NEW_MATCH, [NEW_MATCH]):
        return data, {'status': 'already-patched', 'changed': False,
                      'personalities': personalities, 'patches': []}

    hits = locate_cpu_match(xml)
    if not hits:
        raise Error('found the %s personality but not an IONameMatch "%s" string; '
                    'nothing was changed. Personalities: %r'
                    % (CPU_CLASS, OLD_MATCH, personalities))
    if len(hits) != 1:
        raise Error('expected exactly one %s IONameMatch, found %d; refusing to guess'
                    % (CPU_CLASS, len(hits)))

    absolute = start + hits[0]['offset']
    if data[absolute:absolute + len(OLD_BYTES)] != OLD_BYTES:
        raise Error('internal offset check failed for the IONameMatch value')
    patched = bytearray(data)
    patched[absolute:absolute + len(NEW_BYTES)] = NEW_BYTES

    if len(patched) != len(data):
        raise Error('the patch changed the image length')
    new_start, new_end = prelink_xml_span(patched)
    if (new_start, new_end) != (start, end):
        raise Error('the patch moved the __PRELINK_INFO segment')
    new_root = parse_prelink_xml(bytes(patched[new_start:new_end]).split(b'\0', 1)[0])

    changes = diff_trees(root, new_root)
    expected_path = ('_PrelinkInfoDictionary', None, 'IOKitPersonalities',
                     CPU_CLASS, 'IONameMatch')
    if len(changes) != 1:
        raise Error('read-back found %d metadata changes, expected 1: %r'
                    % (len(changes), changes))
    path, before_value, after_value = changes[0]
    if before_value != OLD_MATCH or after_value != NEW_MATCH:
        raise Error('read-back change is %r -> %r, expected %r -> %r'
                    % (before_value, after_value, OLD_MATCH, NEW_MATCH))
    if 'IONameMatch' not in path or CPU_CLASS not in path:
        raise Error('read-back did not touch the %s IONameMatch' % CPU_CLASS)

    changed = sum(1 for one, two in zip(data, patched) if one != two)
    if changed != EXPECTED_CHANGED_BYTES:
        raise Error('expected %d changed bytes, found %d'
                    % (EXPECTED_CHANGED_BYTES, changed))

    hits[0]['offset_in_image'] = absolute
    return bytes(patched), {
        'status': 'patched',
        'changed': True,
        'personalities': personalities,
        'patches': [{'IOClass': CPU_CLASS, 'from': OLD_MATCH, 'to': NEW_MATCH,
                     'offset_in_image': absolute,
                     'offset_in_prelink_xml': hits[0]['offset']}],
        'changed_bytes': changed,
        'metadata_path': list(path),
        'prelink_xml': {'offset': start, 'size': end - start},
    }


# ---------------------------------------------------------------------------
# Containers: payload FAT volume, v0 boot image
# ---------------------------------------------------------------------------

def run(command):
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise Error('%s failed: %s'
                    % (command[0], (result.stderr or result.stdout).strip()))
    return result


def read_kernel_from_payload(volume, out_path):
    # -m keeps the FAT modification time on the extracted file so the write-back
    # below can restore it, and -p keeps the attributes.
    run(['mcopy', '-o', '-p', '-m', '-i', volume, KERNEL_IN_PAYLOAD, out_path])
    blob = open(out_path, 'rb').read()
    if not blob:
        raise Error('kernel.macho extracted from the payload is empty')
    return blob, os.stat(out_path).st_mtime


def write_kernel_to_payload(volume, blob, mtime=None):
    work = tempfile.mkdtemp(prefix='ioname-mcopy-')
    try:
        staged = os.path.join(work, 'kernel.macho')
        with open(staged, 'wb') as handle:
            handle.write(blob)
        if mtime is not None:
            os.utime(staged, (mtime, mtime))
        run(['mcopy', '-o', '-p', '-m', '-i', volume, staged, KERNEL_IN_PAYLOAD])
        readback = os.path.join(work, 'readback.macho')
        run(['mcopy', '-o', '-p', '-m', '-i', volume, KERNEL_IN_PAYLOAD, readback])
        return open(readback, 'rb').read()
    finally:
        shutil.rmtree(work, ignore_errors=True)


def parse_v0_header(data):
    if data[:8] != b'ANDROID!':
        raise Error('not an Android boot image (magic is %r)' % data[:8])
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr,
     second_size, second_addr, tags_addr, page) = struct.unpack_from('<8I', data, 8)
    version = struct.unpack_from('<I', data, 40)[0]
    if version != 0:
        raise Error('header version %d is not v0; BootShim needs the v0 ramdisk_addr'
                    % version)
    return {'kernel_size': kernel_size, 'kernel_addr': kernel_addr,
            'ramdisk_size': ramdisk_size, 'ramdisk_addr': ramdisk_addr,
            'second_size': second_size, 'second_addr': second_addr,
            'tags_addr': tags_addr, 'page': page, 'header_version': version}


HEADER_FIELDS = ('kernel_size', 'kernel_addr', 'ramdisk_size', 'ramdisk_addr',
                 'second_size', 'tags_addr', 'page', 'header_version')


def image_payload(image_bytes, header):
    page = header['page']
    offset = page + (header['kernel_size'] + page - 1) // page * page
    payload = image_bytes[offset:offset + header['ramdisk_size']]
    if len(payload) != header['ramdisk_size']:
        raise Error('image is truncated: wanted %d payload bytes at %d, got %d'
                    % (header['ramdisk_size'], offset, len(payload)))
    if payload[:1] != b'\xeb' or b'FAT' not in payload[:0x40]:
        raise Error('ramdisk does not look like a FAT volume')
    return offset, payload


def repack(image_bytes, header, payload):
    page = header['page']
    offset = page + (header['kernel_size'] + page - 1) // page * page
    if len(payload) != header['ramdisk_size']:
        raise Error('new payload is %d bytes, the header declares %d'
                    % (len(payload), header['ramdisk_size']))
    out = image_bytes[:offset] + payload
    if len(out) != len(image_bytes):
        raise Error('repacked image length changed')
    check = parse_v0_header(out)
    for key in HEADER_FIELDS:
        if check[key] != header[key]:
            raise Error('repacked header field %s changed' % key)
    _, check_payload = image_payload(out, check)
    if check_payload != payload:
        raise Error('repacked payload does not round-trip')
    return out


def verify_image(path, header, expected_size, expected_payload):
    data = open(path, 'rb').read()
    if len(data) != expected_size:
        raise Error('%s is %d bytes, expected %d' % (path, len(data), expected_size))
    check = parse_v0_header(data)
    for key in HEADER_FIELDS:
        if check[key] != header[key]:
            raise Error('%s header field %s changed' % (path, key))
    _, payload = image_payload(data, check)
    if payload != expected_payload:
        raise Error('%s payload does not match the patched volume' % path)


def write_atomic(path, blob):
    tmp = path + '.tmp'
    with open(tmp, 'wb') as handle:
        handle.write(blob)
    os.replace(tmp, path)


def default_out(path):
    root, ext = os.path.splitext(path)
    return root + '-xpu' + ext


# ---------------------------------------------------------------------------
# Modes
# ---------------------------------------------------------------------------

def patch_bytes(data, label):
    patched, report = patch_kernel_macho(data)
    report['input'] = {'label': label, 'bytes': len(data), 'sha256': sha256(data)}
    report['output'] = {'bytes': len(patched), 'sha256': sha256(patched)}
    return patched, report


def mode_macho(args):
    data = open(args.macho, 'rb').read()
    patched, report = patch_bytes(data, args.macho)
    report['mode'] = 'macho'
    report['wrote'] = False
    if report['changed'] and not args.check:
        out = args.out or default_out(args.macho)
        write_atomic(out, patched)
        if open(out, 'rb').read() != patched:
            raise Error('%s does not match the patched bytes' % out)
        report['output']['path'] = out
        report['wrote'] = True
    return report


def mode_payload(args):
    if not os.path.isfile(args.payload):
        raise Error('no such payload: %s' % args.payload)
    report = {'mode': 'payload', 'input_payload': {
        'path': args.payload, 'bytes': os.path.getsize(args.payload),
        'sha256': sha256(open(args.payload, 'rb').read())}, 'wrote': False}
    work = tempfile.mkdtemp(prefix='ioname-payload-')
    try:
        before, mtime = read_kernel_from_payload(
            args.payload, os.path.join(work, 'kernel.macho'))
        patched, kernel_report = patch_bytes(before, 'kernel.macho')
        report['kernel'] = kernel_report
        if not kernel_report['changed'] or args.check:
            return report
        out = args.out or default_out(args.payload)
        shutil.copyfile(args.payload, out)
        readback = write_kernel_to_payload(out, patched, mtime)
        if readback != patched:
            raise Error('payload read-back differs from the patched kernel')
        if os.path.getsize(out) != os.path.getsize(args.payload):
            raise Error('payload size changed')
        report['output_payload'] = {'path': out, 'bytes': os.path.getsize(out),
                                    'sha256': sha256(open(out, 'rb').read())}
        report['readback_ok'] = True
        report['wrote'] = True
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


def mode_image(args):
    data = open(args.image, 'rb').read()
    header = parse_v0_header(data)
    payload_offset, payload = image_payload(data, header)
    report = {'mode': 'image', 'wrote': False,
              'input_image': {'path': args.image, 'bytes': len(data), 'sha256': sha256(data)},
              'header': header, 'payload_offset': payload_offset,
              'payload_bytes': len(payload), 'payload_sha256': sha256(payload)}
    work = tempfile.mkdtemp(prefix='ioname-image-')
    try:
        volume = os.path.join(work, 'payload.img')
        with open(volume, 'wb') as handle:
            handle.write(payload)
        before, mtime = read_kernel_from_payload(
            volume, os.path.join(work, 'kernel.macho'))
        patched, kernel_report = patch_bytes(before, 'kernel.macho')
        report['kernel'] = kernel_report
        if not kernel_report['changed'] or args.check:
            return report
        readback = write_kernel_to_payload(volume, patched, mtime)
        if readback != patched:
            raise Error('payload read-back differs from the patched kernel')
        new_payload = open(volume, 'rb').read()
        if len(new_payload) != len(payload):
            raise Error('payload size changed to %d bytes' % len(new_payload))
        image = repack(data, header, new_payload)
        out = args.out or default_out(args.image)
        write_atomic(out, image)
        verify_image(out, header, len(data), new_payload)
        report['output_payload_sha256'] = sha256(new_payload)
        report['output_image'] = {'path': out, 'bytes': os.path.getsize(out),
                                  'sha256': sha256(open(out, 'rb').read())}
        report['readback_ok'] = True
        report['wrote'] = True
        return report
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------------------
# Self test: synthetic prelinked kernel, no artifact needed
# ---------------------------------------------------------------------------

def wrap_macho(xml, decoy=None):
    """Put prelink metadata into a minimal ARM64 Mach-O with a decoy __TEXT."""
    text = decoy if decoy is not None else b'<key>IONameMatch</key><string>cpu</string>PADDING!'

    def segment_command(name, va, size, fileoff, section_name):
        body = struct.pack('<16s4Q4I', name.encode(), va, size, fileoff, size, 0, 0, 1, 0)
        section = struct.pack('<16s16sQQI', section_name.encode(), name.encode(), va,
                              size, fileoff)
        section += b'\0' * (80 - len(section))
        return struct.pack('<II', LC_SEGMENT_64, 72 + 80) + body + section

    commands_size = 2 * (72 + 80)
    text_at = 32 + commands_size
    info_at = text_at + len(text) + 64
    commands = (segment_command('__TEXT', 0x1000, len(text), text_at, '__text') +
                segment_command(PRELINK_SEGMENT, 0x4000, len(xml), info_at, '__info'))
    image = bytearray(struct.pack('<8I', MH_MAGIC_64, CPU_TYPE_ARM64, 0, 2, 2,
                                  commands_size, 0, 0))
    image += commands
    if len(image) != text_at:
        raise Error('fixture layout drift')
    image += text + b'\0' * 64
    if len(image) != info_at:
        raise Error('fixture layout drift (info)')
    image += xml
    return bytes(image), {'text_at': text_at, 'text_len': len(text)}


def build_fixture_macho():
    """Hand-written metadata in the exact shape emit_prelink.py writes."""
    kext = ('<dict>'
            '<key>CFBundleIdentifier</key><string>%s</string>'
            '<key>IOKitPersonalities</key><dict>'
            '<key>AppleARMCPU</key><dict>'
            '<key>IOClass</key><string>AppleARMCPU</string>'
            '<key>IOProviderClass</key><string>IOPlatformDevice</string>'
            '<key>IONameMatch</key><string>cpu</string>'
            '<key>IOProbeScore</key><integer size="64">0x1770</integer>'
            '</dict>'
            '<key>AppleARMPlatform</key><dict>'
            '<key>IOClass</key><string>AppleARMPlatform</string>'
            '<key>IONameMatch</key><string>arm-io</string>'
            '</dict>'
            '</dict></dict>' % ARM_PLATFORM)
    decoy = ('<dict>'
             '<key>CFBundleIdentifier</key><string>com.example.DecoyCPU</string>'
             '<key>IOKitPersonalities</key><dict>'
             '<key>Decoy</key><dict>'
             '<key>IOClass</key><string>IAMADecoyCPU</string>'
             '<key>IONameMatch</key><string>cpu</string>'
             '</dict></dict></dict>')
    metadata = ('<dict><key>%s</key><array>%s%s</array>'
                '<key>_PrelinkLinkKASLROffsets</key><data>AAAAAA==</data></dict>'
                % (KEXTS_KEY, kext, decoy))
    return wrap_macho(metadata.encode('utf-8') + b'\0')


def to_xml(value):
    """Same serialiser emit_prelink.py uses for the prelink metadata."""
    if isinstance(value, dict):
        node = ET.Element('dict')
        for key, child in value.items():
            ET.SubElement(node, 'key').text = key
            node.append(to_xml(child))
    elif isinstance(value, list):
        node = ET.Element('array')
        node.extend(to_xml(child) for child in value)
    elif isinstance(value, bool):
        node = ET.Element('true' if value else 'false')
    elif isinstance(value, int):
        node = ET.Element('integer', {'size': '64'})
        node.text = hex(value)
    elif isinstance(value, bytes):
        node = ET.Element('data')
        node.text = base64.b64encode(value).decode('ascii')
    else:
        node = ET.Element('string')
        node.text = value
    return node


def build_serialized_fixture(wrap_plist=False, array_form=False):
    """A realistic AppleARMPlatform entry serialised by ElementTree."""
    cpu_personality = {'IOProbeScore': 20000, 'IOProviderClass': 'IOPlatformDevice'}
    if array_form:
        # IONameMatch first, array value: order and shape must not matter.
        cpu_personality['IONameMatch'] = ['cpu']
        cpu_personality['IOClass'] = 'AppleARMCPU'
    else:
        cpu_personality['IOClass'] = 'AppleARMCPU'
        cpu_personality['IONameMatch'] = 'cpu'
    metadata = {
        KEXTS_KEY: [
            {'CFBundleIdentifier': ARM_PLATFORM,
             '_PrelinkExecutableLoadAddr': 0xfffffff007000000,
             '_PrelinkExecutableSize': 0x1000,
             'OSBundleLibraries': {'com.apple.kpi.iokit': '23.0.0'},
             'IOKitPersonalities': {
                 'AppleARMCPU': cpu_personality,
                 'AppleARMPlatform': {'IOClass': 'AppleARMPlatform',
                                      'IONameMatch': 'arm-io'}}},
            {'CFBundleIdentifier': 'com.example.Decoy',
             'IOKitPersonalities': {
                 'Decoy': {'IONameMatch': 'cpu', 'IOClass': 'DecoyCPU'}}},
        ],
        '_PrelinkLinkKASLROffsets': b'\x02\x00\x00\x00\x80\x00\x00\x00\x88\x00\x00\x00',
    }
    root = to_xml(metadata)
    if wrap_plist:
        wrapper = ET.Element('plist', {'version': '1.0'})
        wrapper.append(root)
        root = wrapper
    return wrap_macho(ET.tostring(root) + b'\0')


def check_patch(image, spans=None, label='fixture'):
    """Patch one fixture and return (patched, report, problems)."""
    problems = []
    patched, report = patch_kernel_macho(image)
    if report['status'] != 'patched':
        problems.append('%s: status is %r' % (label, report['status']))
    if report.get('changed_bytes') != EXPECTED_CHANGED_BYTES:
        problems.append('%s: changed_bytes is %r' % (label, report.get('changed_bytes')))
    if len(patched) != len(image):
        problems.append('%s: length changed' % label)

    diff = [index for index, (one, two) in enumerate(zip(image, patched)) if one != two]
    expected = [report['patches'][0]['offset_in_image'] + offset
                for offset in range(len(NEW_BYTES))
                if OLD_BYTES[offset] != NEW_BYTES[offset]]
    if diff != expected:
        problems.append('%s: unexpected byte diff %r' % (label, diff))

    if spans is not None:
        text = (spans['text_at'], spans['text_at'] + spans['text_len'])
        if image[text[0]:text[1]] != patched[text[0]:text[1]]:
            problems.append('%s: __TEXT decoy bytes were modified' % label)
    # Exactly one "<string>cpu</string>" may disappear: the CPU personality's.
    if patched.count(b'<string>cpu</string>') + 1 != image.count(b'<string>cpu</string>'):
        problems.append('%s: expected exactly one "cpu" string to change, saw %d -> %d'
                        % (label, image.count(b'<string>cpu</string>'),
                           patched.count(b'<string>cpu</string>')))

    start, end = prelink_xml_span(patched)
    root = parse_prelink_xml(patched[start:end].split(b'\0', 1)[0])
    flat = [item for entry in kext_entries(root) for item in personality_report(entry)]
    if not any(item['IOClass'] == CPU_CLASS and
               item['IONameMatch'] in (NEW_MATCH, [NEW_MATCH]) for item in flat):
        problems.append('%s: AppleARMCPU IONameMatch is not xpu' % label)
    if not any(item['IOClass'] in ('IAMADecoyCPU', 'DecoyCPU') and
               item['IONameMatch'] in (OLD_MATCH, [OLD_MATCH]) for item in flat):
        problems.append('%s: the decoy personality was changed' % label)
    if not any(item['IOClass'] == 'AppleARMPlatform' and item['IONameMatch'] == 'arm-io'
               for item in flat):
        problems.append('%s: the AppleARMPlatform personality was changed' % label)

    again, second = patch_kernel_macho(patched)
    if second['status'] != 'already-patched' or again != patched:
        problems.append('%s: second run was not a no-op (%r)' % (label, second['status']))
    return patched, report, problems


def self_test():
    image, spans = build_fixture_macho()
    patched, report, problems = check_patch(image, spans, 'hand-written')

    broken = build_fixture_macho()[0].replace(
        ARM_PLATFORM.encode(), b'com.apple.driver.SomethingElse')
    try:
        patch_kernel_macho(broken)
    except Error:
        pass
    else:
        problems.append('hand-written: a kernel without AppleARMPlatform was not reported')

    cases = [
        ('emit_prelink form', build_serialized_fixture(wrap_plist=False, array_form=False)),
        ('plist wrapper + array IONameMatch',
         build_serialized_fixture(wrap_plist=True, array_form=True)),
    ]
    for label, (fixture, fixture_spans) in cases:
        _, _, problems_here = check_patch(fixture, fixture_spans, label)
        problems += problems_here

    for problem in problems:
        print('self-test FAIL: ' + problem)
    if problems:
        return 1
    print('self-test PASS: %d fixtures patched, %d byte changed, decoys untouched, '
          'second run is a no-op' % (len(cases) + 1, EXPECTED_CHANGED_BYTES))
    print('  fixture %d bytes sha256 %s' % (len(image), sha256(image)))
    print('  patched %d bytes sha256 %s' % (len(patched), sha256(patched)))
    print('  offset %#x  %s -> %s  path %s'
          % (report['patches'][0]['offset_in_image'], OLD_MATCH, NEW_MATCH,
             ' / '.join(str(part) for part in report['metadata_path'])))
    return 0


# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--image', help='v0 Android boot image (extract, patch, repack)')
    source.add_argument('--payload', help='payload FAT volume from `unixnu payload`')
    source.add_argument('--macho', help='bare kernel.macho (prelink output)')
    source.add_argument('--self-test', action='store_true', help='offline fixture test')
    parser.add_argument('--out', help='output path (default: <input>-xpu.<ext>)')
    parser.add_argument('--check', action='store_true', help='report only, write nothing')
    parser.add_argument('--report', help='also write the JSON report here')
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    try:
        if args.image:
            report = mode_image(args)
        elif args.payload:
            report = mode_payload(args)
        else:
            report = mode_macho(args)
    except Error as error:
        sys.exit('error: %s' % error)

    report['tool'] = 'patch-applearmcpu-ioname.py'
    print(json.dumps(report, indent=2))
    if args.report:
        with open(args.report, 'w') as handle:
            handle.write(json.dumps(report, indent=2) + '\n')

    kernel = report.get('kernel', report)
    if kernel.get('status') == 'already-patched':
        print('nothing to do: AppleARMCPU IONameMatch is already xpu')
        return 0
    if not kernel.get('changed'):
        print('nothing changed')
        return 0
    if not report.get('wrote'):
        print('checked only; no file written (--check)')
        return 0
    target = report.get('output_image') or report.get('output_payload') or report['output']
    print('patched: AppleARMCPU IONameMatch %s -> %s, %d byte, image length unchanged'
          % (OLD_MATCH, NEW_MATCH, EXPECTED_CHANGED_BYTES))
    print('result:  %s  %d bytes  sha256 %s'
          % (target['path'], target['bytes'], target['sha256']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
