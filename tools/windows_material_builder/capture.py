# SPDX-License-Identifier: GPL-2.0-or-later
"""Bounded, read-only PCAP/pcapng USBPcap analysis. No packet library needed."""
from dataclasses import dataclass, field
import struct
from .diagnostics import Failure, require
from .files import read_regular
from .framing import parse_a0, ExtractError

LIMIT = 128 * 1024 * 1024
PACKET_LIMIT = 1024 * 1024
BAD = 'CAPTURE_TRUNCATED_OR_INVALID'
TARGET = (0x27c6, 0x5125)
APP = b'GF_ST411SEC_APP_12509'


def pcap_header(data):
    magic = {b'\xd4\xc3\xb2\xa1': ('<', 1000000), b'\xa1\xb2\xc3\xd4': ('>', 1000000),
             b'\x4d\x3c\xb2\xa1': ('<', 1000000000), b'\xa1\xb2\x3c\x4d': ('>', 1000000000)}
    require(len(data) >= 24 and data[:4] in magic, BAD)
    endian, resolution = magic[data[:4]]
    major, minor, zone, sig, snap, link = struct.unpack_from(endian + 'HHiIII', data, 4)
    require((major, minor) == (2, 4) and link == 249 and 27 <= snap <= PACKET_LIMIT, BAD)
    return endian, resolution, snap


def packets(data):
    require(0 < len(data) <= LIMIT, 'CAPTURE_EMPTY' if not data else BAD)
    if data[:4] != b'\x0a\x0d\x0d\x0a':
        endian, resolution, snap = pcap_header(data)
        offset, previous = 24, -1
        while offset < len(data):
            require(offset + 16 <= len(data), BAD)
            sec, fraction, captured, original = struct.unpack_from(endian + 'IIII', data, offset)
            offset += 16
            require(27 <= captured == original <= snap and fraction < resolution and
                    offset + captured <= len(data), BAD)
            stamp = sec * resolution + fraction
            require(stamp >= previous, BAD)
            previous = stamp
            yield 0, data[offset:offset + captured]
            offset += captured
        return
    offset, endian, interfaces, sections = 0, '<', [], 0
    previous = {}
    while offset < len(data):
        require(offset + 12 <= len(data), BAD)
        section = data[offset:offset + 4] == b'\x0a\x0d\x0d\x0a'
        if section:
            bom = data[offset + 8:offset + 12]
            require(bom in (b'\x4d\x3c\x2b\x1a', b'\x1a\x2b\x3c\x4d'), BAD)
            endian = '<' if bom[0] == 0x4d else '>'
        kind, length = struct.unpack_from(endian + 'II', data, offset)
        require(12 <= length <= PACKET_LIMIT + 4096 and length % 4 == 0 and offset + length <= len(data), BAD)
        require(struct.unpack_from(endian + 'I', data, offset + length - 4)[0] == length, BAD)
        body = data[offset + 8:offset + length - 4]
        if section:
            sections += 1
            require(sections == 1 and len(body) >= 16 and struct.unpack_from(endian + 'HH', body, 4) == (1, 0), BAD)
        elif kind == 1:
            require(sections == 1 and len(body) >= 8, BAD)
            link, reserved, snap = struct.unpack_from(endian + 'HHI', body)
            require(link == 249 and reserved == 0 and (snap == 0 or 27 <= snap <= PACKET_LIMIT), BAD)
            interfaces.append(snap or PACKET_LIMIT)
            require(len(interfaces) <= 32, BAD)
        elif kind == 6:
            require(len(body) >= 20, BAD)
            interface, hi, lo, captured, original = struct.unpack_from(endian + 'IIIII', body)
            require(interface < len(interfaces) and 27 <= captured == original <= interfaces[interface] and
                    20 + ((captured + 3) & ~3) <= len(body), BAD)
            stamp = (hi << 32) | lo
            require(stamp >= previous.get(interface, -1), BAD)
            previous[interface] = stamp
            yield interface, body[20:20 + captured]
        else:
            # ISB / name-resolution / custom non-packet metadata are harmless;
            # obsolete and simple packet blocks cannot establish ordering.
            require(kind in (4, 5, 0x00000bad, 0x40000bad), BAD)
        offset += length


@dataclass(frozen=True, repr=False)
class Packet:
    index: int
    interface: int
    bus: int
    device: int
    irp: int
    status: int
    function: int
    info: int
    endpoint: int
    transfer: int
    stage: int
    payload: bytes = field(repr=False)

    @property
    def key(self):
        return self.interface, self.bus, self.device


def decode(index, interface, raw):
    require(index < 200000 and len(raw) >= 27, BAD)
    hlen, irp, status, function, info, bus, device, endpoint, transfer, length = struct.unpack_from('<HQIHBHHBBI', raw)
    require(27 <= hlen <= len(raw) and hlen + length == len(raw) and info in (0, 1), BAD)
    if transfer in (1, 3):
        require(hlen == 27, BAD)
    elif transfer == 2:
        require(hlen == 28 and raw[27] in (0, 3), BAD)
    elif transfer == 0:
        require(hlen >= 39 and (hlen - 39) % 12 == 0, BAD)
    else:
        require(transfer == 0xfe, BAD)
    return Packet(index, interface, bus, device, irp, status, function, info, endpoint,
                  transfer, raw[27] if transfer == 2 else -1, raw[hlen:])


@dataclass(repr=False)
class Evidence:
    selected: dict = field(default_factory=dict, repr=False)
    codes: tuple = ()

    def require_complete(self):
        if self.codes:
            raise Failure(self.codes[0])
        require(set(self.selected) == {'CONFIG90', 'A2', 'CHIP82', 'A6'}, BAD)


def config_valid(body):
    return (len(body) == 224 and (sum(struct.unpack('<112H', body)) + 0xa5a5) & 65535 == 0 and
            all(struct.unpack_from('<H', body, offset)[0] == register for offset, register in
                ((117, 0x220), (121, 0x236), (125, 0x238), (129, 0x23a))))


def analyze(path):
    try:
        data = read_regular(path, LIMIT, 0)
    except Failure:
        raise Failure(BAD) from None
    return analyze_bytes(data)


def analyze_bytes(data):
    records = [decode(i, interface, raw) for i, (interface, raw) in enumerate(packets(data))]
    require(bool(records), 'CAPTURE_EMPTY')
    # Match USB setup/completion records, including device-descriptor requests.
    outstanding, identities, starts, bulk_seen = {}, {}, {}, set()
    accepted = []
    for p in records:
        if p.transfer not in (2, 3):
            continue
        irpkey = (p.interface, p.bus, p.irp)
        if p.info == 0:
            require(irpkey not in outstanding, BAD)
            outstanding[irpkey] = p
            if p.transfer == 3 and p.payload:
                bulk_seen.add(p.key)
        else:
            request = outstanding.pop(irpkey, None)
            # Some captures begin with completions for pre-existing unrelated
            # devices. They cannot contribute any accepted evidence.
            if request is None:
                continue
            require(request.key == p.key and request.transfer == p.transfer and
                    (request.endpoint & 0x7f) == (p.endpoint & 0x7f), BAD)
            if p.transfer == 3:
                require(request.endpoint == p.endpoint and request.function == p.function, BAD)
            if p.status:
                continue
            if p.transfer == 2:
                require(request.stage == 0 and p.stage == 3 and len(request.payload) >= 8, BAD)
                setup = request.payload[:8]
                requested_length = int.from_bytes(setup[6:8], 'little')
                if setup[0] & 0x80:
                    require(len(request.payload) == 8 and len(p.payload) <= requested_length, BAD)
                else:
                    require(len(request.payload) == 8 + requested_length and not p.payload, BAD)
                if p.key in bulk_seen and setup[1] in (5, 9):
                    # SET_ADDRESS / SET_CONFIGURATION after traffic starts is
                    # a new or ambiguous attachment epoch, never merge it.
                    require(False, 'TARGET_WRONG_IDENTITY')
                if setup[:4] == b'\x80\x06\x00\x01' and len(p.payload) >= 18:
                    require(p.payload[:2] == b'\x12\x01', BAD)
                    identity = struct.unpack_from('<HH', p.payload, 8)
                    if p.key in identities:
                        require(identities[p.key] == identity and p.key not in bulk_seen,
                                'TARGET_WRONG_IDENTITY')
                    identities[p.key] = identity
                    starts.setdefault(p.key, p.index)
            elif p.endpoint in (1, 0x81):
                if p.endpoint == 1:
                    require(not p.payload, BAD)
                    packet = request
                else:
                    require(not request.payload, BAD)
                    packet = p
                    if p.payload:
                        bulk_seen.add(p.key)
                if packet.payload:
                    accepted.append(packet)
    targets = [key for key, identity in identities.items() if identity == TARGET]
    require(bool(targets), 'TARGET_WRONG_IDENTITY' if identities else 'TARGET_NOT_OBSERVED')
    require(len(targets) == 1, 'TARGET_WRONG_IDENTITY')
    target = targets[0]
    # No successful/unsuccessful material OUT may be silently omitted.
    for p in outstanding.values():
        require(not (p.key == target and p.endpoint == 1 and p.payload), BAD)
    streams = {1: bytearray(), 0x81: bytearray()}
    groups = {name: set() for name in ('CONFIG90', 'A2', 'CHIP82', 'A6', 'APP')}
    # Submitted OUT order and completed IN order are the wire-evidence order.
    for p in sorted(accepted, key=lambda p: p.index):
        if p.key != target:
            continue
        require(p.index > starts[target], 'TARGET_WRONG_IDENTITY')
        buf = streams[p.endpoint]
        if not buf and p.payload[0] not in (0xa0, 0xb0):
            # Historical extractor ignores non-frame transfers, never scans
            # for a plausible protected body inside unrelated payloads.
            continue
        buf.extend(p.payload)
        while buf:
            # Canonical OEM physical requests are padded to 64 bytes after
            # the logical frame (TECHNICAL_MANUAL section 2.1).
            if len(p.payload) == 64 and len(buf) < 64 and not any(buf):
                buf.clear()
                break
            if buf[0] not in (0xa0, 0xb0):
                buf.clear()  # opaque physical tail, same historical rule
                break
            if len(buf) < 4:
                break
            wanted = 4 + int.from_bytes(buf[1:3], 'little')
            require((8 if buf[0] == 0xa0 else 4) <= wanted <= 65539, BAD)
            if len(buf) < wanted:
                break
            raw = bytes(buf[:wanted])
            del buf[:wanted]
            if raw[0] != 0xa0:
                continue
            try:
                wire, logical, body = parse_a0(raw)
            except ExtractError:
                continue
            name = None
            if p.endpoint == 1 and wire == 0x91 and config_valid(body):
                name = 'CONFIG90'
            if p.endpoint == 0x81:
                spec = {0xa2: ('A2', 3), 0x82: ('CHIP82', 4), 0xa6: ('A6', 64)}.get(wire)
                if spec and len(body) == spec[1]:
                    name = spec[0]
                elif wire == 0xa8:
                    name = 'APP'
            if name:
                # Two distinct values already prove ambiguity. Keep bounded
                # memory while still validating the remainder of the capture.
                if len(groups[name]) < 2:
                    groups[name].add(body)
    require(not any(streams.values()), BAD)
    require(len(groups['APP']) == 1 and next(iter(groups['APP'])) == APP + b'\0',
            'APP_ID_MISSING_OR_WRONG')
    selected, codes = {}, []
    for name in ('CONFIG90', 'A2', 'CHIP82', 'A6'):
        if len(groups[name]) == 1:
            selected[name] = next(iter(groups[name]))
        else:
            codes.append(name + ('_MISSING' if not groups[name] else '_AMBIGUOUS'))
    return Evidence(selected, tuple(codes))
