# SPDX-License-Identifier: GPL-2.0-or-later
"""A0 checksum/length validation reused unchanged from fa98461 shared parser."""
A0 = 0xa0
class ExtractError(ValueError):
    pass

def parse_a0(raw: bytes) -> tuple[int, int, bytes]:
    if len(raw) < 8 or raw[0] != A0:
        raise ExtractError("not A0")
    payload_length = int.from_bytes(raw[1:3], "little")
    if payload_length + 4 != len(raw):
        raise ExtractError("A0 outer length mismatch")
    tag = (raw[0] + (payload_length & 0xff) +
           ((payload_length >> 8) & 0xff)) & 0xff
    if raw[3] != tag:
        raise ExtractError("A0 outer tag mismatch")
    wire_control = raw[4]
    logical_control = wire_control & 0xfe
    inner_length = int.from_bytes(raw[5:7], "little")
    if inner_length == 0 or inner_length + 3 != payload_length:
        raise ExtractError("A0 inner length mismatch")
    body = raw[7:7 + inner_length - 1]
    if len(body) != inner_length - 1:
        raise ExtractError("A0 body truncated")
    checksum = (logical_control + len(body) + 1 + sum(body) + raw[-1]) & 0xff
    if checksum != 0xaa:
        raise ExtractError("A0 inner checksum mismatch")
    return wire_control, logical_control, body
