"""D191 dedicated Windows-to-Linux transfer record.

This is an integrity-checked staging container, not encryption and not the
runtime transport-material v1 store format.
"""

from __future__ import annotations

import hashlib
import hmac
import struct

MAGIC = b"G5125XFR"
VERSION = 1
VID = 0x27C6
PID = 0x5125
SECRET_LENGTH = 32
HEADER_LENGTH = 24
RECORD_LENGTH = 88
_HEADER = struct.Struct("<8sHHHHHHI")


class TransferRecordError(ValueError):
    pass


def build(secret: bytes | bytearray) -> bytearray:
    if len(secret) != SECRET_LENGTH or not any(secret):
        raise TransferRecordError("secret must be exactly 32 non-zero bytes")
    prefix = bytearray(_HEADER.pack(
        MAGIC, VERSION, 0, VID, PID, SECRET_LENGTH, 0, SECRET_LENGTH
    ))
    prefix.extend(secret)
    prefix.extend(hashlib.sha256(prefix).digest())
    if len(prefix) != RECORD_LENGTH:
        raise AssertionError("transfer record construction length mismatch")
    return prefix


def parse(record: bytes | bytearray) -> bytearray:
    if len(record) != RECORD_LENGTH:
        raise TransferRecordError("transfer record length rejected")
    magic, version, flags, vid, pid, secret_len, reserved, payload_len = _HEADER.unpack_from(record)
    if magic != MAGIC:
        raise TransferRecordError("transfer magic rejected")
    if version != VERSION or flags != 0 or reserved != 0:
        raise TransferRecordError("transfer version/flags/reserved rejected")
    if vid != VID or pid != PID:
        raise TransferRecordError("transfer device rejected")
    if secret_len != SECRET_LENGTH or payload_len != SECRET_LENGTH:
        raise TransferRecordError("transfer bounded lengths rejected")
    expected = hashlib.sha256(record[:HEADER_LENGTH + SECRET_LENGTH]).digest()
    if not hmac.compare_digest(expected, record[-32:]):
        raise TransferRecordError("transfer digest rejected")
    secret = bytearray(record[HEADER_LENGTH:HEADER_LENGTH + SECRET_LENGTH])
    if not any(secret):
        secret[:] = bytes(len(secret))
        raise TransferRecordError("zero secret rejected")
    return secret
