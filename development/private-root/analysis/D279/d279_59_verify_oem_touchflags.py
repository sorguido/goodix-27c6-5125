#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the OEM six-channel touchflag semantics without executing the DLL."""

from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DLL = ROOT / "analysis/D230/work/GoodixExport/gfusb.dll"
DISASSEMBLY = ROOT / "analysis/D230/work/GoodixExport/gfusb_static_refs/gfusb_disasm.txt"
ROCKY = ROOT / "Rockytkg/src/goodix_base.c"
EXPECTED_SHA256 = {
    DLL: "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2",
    DISASSEMBLY: "d661afb78f60bd1ae45a5ca7bf708abd0e2a3fdd7e3cd5805bb2a3883fb7c743",
    ROCKY: "950525231aa506a7082e2048fbda33568d3c42ecfce1eb85f469bfb3380f1972",
}


class StaticEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StaticEvidenceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_pe_va(data: bytes, virtual_address: int, length: int) -> bytes:
    require(data[:2] == b"MZ", "OEM_DLL_DOS_HEADER")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    require(data[pe_offset:pe_offset + 4] == b"PE\0\0", "OEM_DLL_PE_HEADER")
    coff = pe_offset + 4
    section_count = struct.unpack_from("<H", data, coff + 2)[0]
    optional_size = struct.unpack_from("<H", data, coff + 16)[0]
    optional = coff + 20
    require(struct.unpack_from("<H", data, optional)[0] == 0x20B,
            "OEM_DLL_NOT_PE32_PLUS")
    image_base = struct.unpack_from("<Q", data, optional + 24)[0]
    rva = virtual_address - image_base
    sections = optional + optional_size
    for index in range(section_count):
        section = sections + index * 40
        virtual_size, virtual_start, raw_size, raw_start = struct.unpack_from(
            "<IIII", data, section + 8)
        span = max(virtual_size, raw_size)
        if virtual_start <= rva and rva + length <= virtual_start + span:
            offset = raw_start + rva - virtual_start
            require(offset + length <= len(data), "OEM_DLL_VA_OUT_OF_FILE")
            return data[offset:offset + length]
    raise StaticEvidenceError("OEM_DLL_VA_NOT_MAPPED")


def disassembly_range(text: str, start: int, end: int) -> str:
    selected = []
    for line in text.splitlines():
        match = re.match(r"\s*([0-9a-f]+):", line)
        if match and start <= int(match.group(1), 16) < end:
            selected.append(line)
    require(selected, f"DISASSEMBLY_RANGE_EMPTY_{start:x}_{end:x}")
    return "\n".join(selected)


def require_fragments(text: str, fragments: tuple[str, ...], label: str) -> None:
    for fragment in fragments:
        require(fragment in text, f"{label}_MISSING_{fragment}")


def verify(root: Path = ROOT) -> dict:
    paths = {
        path.relative_to(ROOT): root / path.relative_to(ROOT)
        for path in EXPECTED_SHA256
    }
    for relative, path in paths.items():
        require(path.is_file(), f"MISSING_{relative}")
        require(sha256(path) == EXPECTED_SHA256[ROOT / relative],
                f"SHA256_MISMATCH_{relative}")

    dll_data = paths[DLL.relative_to(ROOT)].read_bytes()
    raw_table_length = struct.unpack(
        "<I", read_pe_va(dll_data, 0x180576DF4, 4))[0]
    require(raw_table_length == 12, "OEM_FDT_RAW_LENGTH_NOT_12")
    channel_count = raw_table_length // 2
    require(channel_count == 6, "OEM_FDT_CHANNEL_COUNT_NOT_6")

    disassembly = paths[DISASSEMBLY.relative_to(ROOT)].read_text(
        encoding="utf-8", errors="strict")
    callsite = disassembly_range(disassembly, 0x180028815, 0x18002883A)
    handler = disassembly_range(disassembly, 0x180029314, 0x1800296D7)
    require_fragments(callsite, (
        "18002881a:", "imul   rax,rax,0x2",
        "18002882c:", "xor    edx,edx",
        "180028831:", "call   0x180029314",
    ), "OEM_IRQ2_CALLSITE")
    require_fragments(handler, (
        # The first two bytes at the handler input become one touchflag word.
        "18002939a:", "movzx  eax,BYTE PTR [rcx+rax*1]",
        "1800293af:", "movzx  ecx,BYTE PTR [rdx+rcx*1]",
        "1800293b3:", "imul   ecx,ecx,0x100",
        "1800293bb:", "mov    WORD PTR [rsp+0x68],ax",
        # Candidate active-channel value: (raw16 >> 1) + configured delta.
        "18002947e:", "movzx  eax,WORD PTR [rcx+rax*1+0x2]",
        "18002949d:", "sar    eax,1",
        "1800294ab:", "add    eax,ecx",
        # Mode zero enters the per-channel touchflag loop.
        "1800294f5:", "cmp    DWORD PTR [rsp+0xb8],0x0",
        # Loop bound is the 12-byte raw length divided by two.
        "18002951d:", "# 0x180576df4",
        "180029529:", "sar    eax,1",
        # The loop extracts bit i independently.
        "180029533:", "movzx  eax,WORD PTR [rsp+0x68]",
        "18002953d:", "sar    eax,cl",
        "18002953f:", "and    eax,0x1",
        # A clear bit overwrites only channel i with delta - 2.
        "18002955d:", "movzx  eax,WORD PTR [rax+0x51f6]",
        "180029564:", "sub    eax,0x2",
        "180029573:", "mov    WORD PTR [rsp+rcx*2+0x80],ax",
        # Default delta 0x15 has the encoded fallback (0x15 - 2) << 8 | 0x80.
        "180029582:", "mov    ecx,0x1380",
        "180029587:", "mov    WORD PTR [rsp+rax*2+0x80],cx",
        "18002958f:", "mov    al,BYTE PTR [rsp+0x61]",
    ), "OEM_TOUCHFLAG_HANDLER")

    rocky = paths[ROCKY.relative_to(ROOT)].read_text(encoding="utf-8")
    require_fragments(rocky, (
        "int gx_fdt_learn_up_base(struct goodix_dev *d, const uint8_t raw[12],",
        "for (int i = 0; i < 6; i++)",
        "if (!((touchflag >> i) & 1))",
        "((delta - 2) << 8) | 0x80",
        "delta + (v >> 1)",
    ), "ROCKY_CORROBORATION")

    return {
        "oem_authority": {
            "binary": str(DLL.relative_to(ROOT)),
            "binary_sha256": EXPECTED_SHA256[DLL],
            "canonical_disassembly": str(DISASSEMBLY.relative_to(ROOT)),
            "canonical_disassembly_sha256": EXPECTED_SHA256[DISASSEMBLY],
            "executed": False,
            "irq2_callsite": "0x180028815-0x180028839",
            "handler": "0x180029314-0x1800296d6",
            "touchflag_input": "FIRST_TWO_HANDLER_INPUT_BYTES_AS_U16_LE",
            "raw_input": "NEXT_12_BYTES",
            "raw_table_length_va": "0x180576df4",
            "raw_table_length": raw_table_length,
            "channel_count": channel_count,
            "mode": "IRQ2_CALLS_HANDLER_WITH_MODE_ZERO",
            "bit_rule": "FOR_EACH_CHANNEL_I_EXTRACT_TOUCHFLAG_BIT_I",
            "active_rule": "ENCODE_RAW16_SHIFT_RIGHT_1_PLUS_DELTA",
            "inactive_rule": "ENCODE_DELTA_MINUS_2",
            "status": "VERIFIED_STATICALLY",
        },
        "rockytkg_corroboration": {
            "source": str(ROCKY.relative_to(ROOT)),
            "source_sha256": EXPECTED_SHA256[ROCKY],
            "commit": "227eba219fa9e3fbac5bd59aca79f624f67cd11b",
            "matching_semantics": True,
            "role": "SEMANTIC_CORROBORATION_NOT_TARGET_USB_TRANSCRIPT_AUTHORITY",
        },
        "policy_consequence": {
            "all_low_six_bits_are_independently_interpreted": True,
            "all_physical_subsets_observed": False,
            "nonzero_contact_subset_acceptance": "DERIVED_FROM_VERIFIED_OEM_BIT_RULE_PLUS_OBSERVED_CONTACT_CONTEXTS",
            "zero_contact_rejection": "CONSERVATIVE_CONTEXT_RULE_FROM_OBSERVED_CONTACT_VS_NO_TOUCH_SEPARATION",
            "reserved_high_bits_rejection": "CONSERVATIVE_FAIL_CLOSED_BOUND_TO_SIX_VERIFIED_CHANNELS",
        },
    }


if __name__ == "__main__":
    import json
    print(json.dumps(verify(), indent=2, sort_keys=True))
