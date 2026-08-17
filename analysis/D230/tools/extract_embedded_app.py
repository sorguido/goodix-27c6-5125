#!/usr/bin/env python3
"""Extract the repeated ST411/12509 mapped APP code from the pinned DLL.

This is an offline parser.  Outputs are proprietary working files and must stay
under analysis/D230/work; they are deliberately excluded from the final bundle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path


NAME = b"GF_ST411SEC_APP_12509"
CODE_LENGTH = 128384
MAPPED_START = 0x0802C000


def make_arm_elf(code: bytes) -> bytes:
    # Minimal ELF32 little-endian ARM executable with one RX PT_LOAD segment.
    ehsize = 52
    phentsize = 32
    phoff = ehsize
    data_off = 0x1000
    ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + bytes(8)
    shstr = b"\x00.text\x00.shstrtab\x00"
    shstr_off = data_off + len(code)
    shoff = (shstr_off + len(shstr) + 3) & ~3
    elf_header = ident + struct.pack(
        "<HHIIIIIHHHHHH",
        2,  # ET_EXEC
        40,  # EM_ARM
        1,
        MAPPED_START,
        phoff,
        shoff,
        0x05000200,  # EABI5, soft-float compatible marker
        ehsize,
        phentsize,
        1,
        40,
        3,
        2,
    )
    program_header = struct.pack(
        "<IIIIIIII",
        1,  # PT_LOAD
        data_off,
        MAPPED_START,
        MAPPED_START,
        len(code),
        len(code),
        5,  # PF_R | PF_X
        0x1000,
    )
    prefix = elf_header + program_header
    section_null = bytes(40)
    section_text = struct.pack(
        "<IIIIIIIIII", 1, 1, 0x6, MAPPED_START, data_off, len(code), 0, 0, 2, 0
    )
    section_shstr = struct.pack(
        "<IIIIIIIIII", 7, 3, 0, 0, shstr_off, len(shstr), 0, 0, 1, 0
    )
    body = prefix + bytes(data_off - len(prefix)) + code + shstr
    return body + bytes(shoff - len(body)) + section_null + section_text + section_shstr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dll", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    dll = args.dll.read_bytes()
    starts = []
    pos = 0
    while True:
        pos = dll.find(bytes([len(NAME)]) + NAME, pos)
        if pos < 0:
            break
        code_start = pos + 1 + len(NAME)
        candidate = dll[code_start : code_start + CODE_LENGTH]
        if len(candidate) == CODE_LENGTH:
            initial_sp, reset = struct.unpack_from("<II", candidate, 0)
            if 0x20000000 <= initial_sp < 0x20100000 and reset & 1:
                starts.append((pos, code_start, candidate, initial_sp, reset))
        pos += 1
    if not starts:
        raise SystemExit("no embedded ST411/12509 code record found")
    digests = {hashlib.sha256(item[2]).hexdigest() for item in starts}
    if len(digests) != 1:
        raise SystemExit(f"embedded copies disagree: {sorted(digests)}")
    code = starts[0][2]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    code_path = args.output_dir / "GF_ST411SEC_APP_12509_mapped_code.bin"
    elf_path = args.output_dir / "GF_ST411SEC_APP_12509_mapped_code.elf"
    code_path.write_bytes(code)
    elf_path.write_bytes(make_arm_elf(code))
    manifest = {
        "record_count": len(starts),
        "record_offsets": [f"0x{item[0]:x}" for item in starts],
        "code_offsets": [f"0x{item[1]:x}" for item in starts],
        "name": NAME.decode(),
        "mapped_start": f"0x{MAPPED_START:08x}",
        "mapped_code_length": len(code),
        "mapped_code_sha256": hashlib.sha256(code).hexdigest(),
        "initial_sp": f"0x{starts[0][3]:08x}",
        "reset_vector": f"0x{starts[0][4]:08x}",
        "proprietary_outputs_bundle_allowed": False,
    }
    (args.output_dir / "embedded_app_extraction.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
