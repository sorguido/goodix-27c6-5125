#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic-only tests for the D274 offline postprocessor and operator kit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import struct
import sys
import tempfile
import unittest
import copy
from pathlib import Path

try:
    import jsonschema  # type: ignore
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "analysis/D274/d274_postprocess_multiframe_evidence.py"
SPEC = importlib.util.spec_from_file_location("d274_postprocessor", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
D274 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = D274
SPEC.loader.exec_module(D274)


def a0(control: int, body: bytes = b"") -> bytes:
    inner_len = len(body) + 1
    checksum = (0xAA - ((control & 0xFE) + (inner_len & 0xFF)
                       + (inner_len >> 8) + sum(body))) & 0xFF
    inner = body + bytes([checksum])
    raw = bytes([0xA0, 0, 0, 0, control]) + inner_len.to_bytes(2, "little") + inner
    declared = len(raw) - 4
    return raw[:1] + declared.to_bytes(2, "little") + raw[3:]


def b0(total_outer_length: int = 7726) -> bytes:
    # Fingerprint-image B0: device-to-host outer 0xB0, total outer 7726 bytes,
    # carrying a TLS application-data record (17 03 03) whose declared length
    # (network byte order / big-endian) plus the 5-byte record header equals the
    # declared B0 length (7722). Goodix B0 outer length stays little-endian.
    declared_b0 = total_outer_length - 4
    tls_inner_len = declared_b0 - 5
    tls = b"\x17\x03\x03" + tls_inner_len.to_bytes(2, "big") + bytes(tls_inner_len)
    return b"\xB0" + declared_b0.to_bytes(2, "little") + b"\x00" + tls


def b0_alert() -> bytes:
    # Short B0 carrying a TLS alert (15 03 03); structurally NOT a fingerprint.
    body = b"\x15\x03\x03" + (2).to_bytes(2, "big") + b"\x02\x01"
    return b"\xB0" + len(body).to_bytes(2, "little") + b"\x00" + body


def b0_wrong_length(total_outer_length: int = 4000) -> bytes:
    declared_b0 = total_outer_length - 4
    tls_inner_len = declared_b0 - 5
    tls = b"\x17\x03\x03" + tls_inner_len.to_bytes(2, "big") + bytes(tls_inner_len)
    return b"\xB0" + declared_b0.to_bytes(2, "little") + b"\x00" + tls


def b0_incoherent_tls_length() -> bytes:
    # Total outer 7726 / declared 7722 but TLS declared length off by one.
    declared_b0 = 7722
    tls_inner_len = declared_b0 - 5 - 1
    tls = b"\x17\x03\x03" + tls_inner_len.to_bytes(2, "big") + bytes(tls_inner_len + 1)
    return b"\xB0" + declared_b0.to_bytes(2, "little") + b"\x00" + tls


def b0_little_endian_tls(total_outer_length: int = 7726) -> bytes:
    # Intentionally WRONG: a synthetic fixture that encodes the TLS record length
    # in little-endian (17 03 03 25 1e) while the record layer is big-endian.
    # This must NOT be accepted as a fingerprint B0; it guards against the
    # synthetic fixture redefining TLS semantics.
    declared_b0 = total_outer_length - 4
    tls_inner_len = declared_b0 - 5
    tls = b"\x17\x03\x03" + tls_inner_len.to_bytes(2, "little") + bytes(tls_inner_len)
    return b"\xB0" + declared_b0.to_bytes(2, "little") + b"\x00" + tls


def nav(control: int = 0x50) -> bytes:
    return a0(control, bytes(2409))


def descriptor() -> bytes:
    return b"\x12\x01\x00\x02\x00\x00\x00\x40\xc6\x27\x25\x51\x00\x01\x01\x02\x03\x01"


def usbpcap(payload: bytes, bus: int, device: int, endpoint: int,
            transfer: int = 3, info: int | None = None) -> bytes:
    raw = bytearray(27)
    struct.pack_into("<H", raw, 0, 27)
    struct.pack_into("<H", raw, 14, 9)
    raw[16] = (1 if endpoint & 0x80 else 0) if info is None else info
    struct.pack_into("<H", raw, 17, bus)
    struct.pack_into("<H", raw, 19, device)
    raw[21] = endpoint
    raw[22] = transfer
    struct.pack_into("<I", raw, 23, len(payload))
    return bytes(raw) + payload


def block(block_type: int, body: bytes) -> bytes:
    padding = bytes((-len(body)) % 4)
    length = 12 + len(body) + len(padding)
    return struct.pack("<II", block_type, length) + body + padding + struct.pack("<I", length)


def pcapng(rows: list[tuple[float, bytes]]) -> bytes:
    shb = block(0x0A0D0D0A, b"\x4d\x3c\x2b\x1a\x01\x00\x00\x00" + b"\xff" * 8)
    idb = block(1, struct.pack("<HHI", 249, 0, 65535) + struct.pack("<HH", 0, 0))
    epbs = []
    for timestamp, raw in rows:
        ticks = int(round(timestamp * 1_000_000))
        body = struct.pack("<IIIII", 0, ticks >> 32, ticks & 0xFFFFFFFF,
                           len(raw), len(raw)) + raw
        epbs.append(block(6, body))
    return shb + idb + b"".join(epbs)


def canonical_frames() -> list[tuple[str, bytes, int]]:
    # label, raw, endpoint
    return [
        ("a8", a0(0xA8, b"GF_ST411SEC_APP_12509\0"), 0x81),
        ("first_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("first_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("first_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("first_image_b0", b0(), 0x81),
        ("first_0x34", a0(0x34, b"\x0a\x01" + bytes(12)), 0x01),
        ("first_0x34_ack", a0(0xB0, b"\x34\x01"), 0x81),
        ("first_irq0200", a0(0x34, b"\x00\x02" + bytes(12)), 0x81),
        ("post_up_0x20", a0(0x20, b"\x01\x00"), 0x01),
        ("post_up_0x20_ack", a0(0xB0, b"\x20\x01"), 0x81),
        ("post_up_b0", b0(), 0x81),
        ("post_up_0x50", a0(0x50), 0x01),
        ("post_up_0x50_ack", a0(0xB0, b"\x50\x01"), 0x81),
        ("post_0x50_nav", nav(), 0x81),
        ("rearm_0x32", a0(0x32, bytes(14)), 0x01),
        ("rearm_0x32_ack", a0(0xB0, b"\x32\x01"), 0x81),
        ("second_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81),
        ("second_0x22", a0(0x22, b"\x01\x00"), 0x01),
        ("second_0x22_ack", a0(0xB0, b"\x22\x01"), 0x81),
        ("second_b0", b0(), 0x81),
    ]


def _load_schema() -> dict:
    return json.loads((ROOT / "analysis/D274/D274_01_evidence_schema.json").read_text())


def _local_validate(document: dict, schema: dict) -> None:
    """Strict local JSON-Schema validator for the D274 evidence subset.

    It does not depend on the jsonschema library and fails closed on any
    additional property or type/constraint violation inside frame metadata.
    """
    defs = schema.get("$defs", {})

    def resolve(subschema: dict) -> dict:
        while "$ref" in subschema:
            name = subschema["$ref"].rpartition("/")[2]
            subschema = defs[name]
        return subschema

    def validate(node, subschema) -> None:
        subschema = resolve(subschema)
        if "enum" in subschema:
            if node not in subschema["enum"]:
                raise D274.EvidenceError("SCHEMA_ENUM")
            return
        if "const" in subschema:
            if node != subschema["const"]:
                raise D274.EvidenceError("SCHEMA_CONST")
            return
        if "anyOf" in subschema:
            ok = False
            for sub in subschema["anyOf"]:
                try:
                    validate(node, sub)
                    ok = True
                    break
                except D274.EvidenceError:
                    continue
            if not ok:
                raise D274.EvidenceError("SCHEMA_ANYOF")
            return
        t = subschema.get("type")
        types = t if isinstance(t, list) else ([t] if t is not None else [])
        if types and not any(_schema_type_matches(node, tt) for tt in types):
            raise D274.EvidenceError("SCHEMA_TYPE")
        if isinstance(node, dict):
            ap = subschema.get("additionalProperties", True)
            allowed = set(subschema.get("properties", {}))
            for key in node:
                if key not in allowed:
                    if ap is False:
                        raise D274.EvidenceError("SCHEMA_ADDITIONAL_PROPERTY")
                    if isinstance(ap, dict):
                        validate(node[key], ap)
            for req in subschema.get("required", []):
                if req not in node:
                    raise D274.EvidenceError("SCHEMA_REQUIRED")
            for key, prop in subschema.get("properties", {}).items():
                if key in node:
                    validate(node[key], prop)
            return
        if isinstance(node, str):
            if "pattern" in subschema and not re.fullmatch(subschema["pattern"], node):
                raise D274.EvidenceError("SCHEMA_PATTERN")
            return
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            return
        if node is None:
            return
        if isinstance(node, list):
            return
        raise D274.EvidenceError("SCHEMA_UNHANDLED")
    validate(document, schema)


def _schema_type_matches(node, t: str) -> bool:
    if t == "object":
        return isinstance(node, dict)
    if t == "string":
        return isinstance(node, str)
    if t == "integer":
        return isinstance(node, int) and not isinstance(node, bool)
    if t == "number":
        return isinstance(node, (int, float)) and not isinstance(node, bool)
    if t == "boolean":
        return isinstance(node, bool)
    if t == "null":
        return node is None
    if t == "array":
        return isinstance(node, list)
    return False


def _validate_instance_ok(document: dict, schema: dict) -> bool:
    if JSONSCHEMA_AVAILABLE:
        try:
            jsonschema.validate(document, schema)
            return True
        except jsonschema.ValidationError:
            return False
    try:
        _local_validate(document, schema)
        return True
    except D274.EvidenceError:
        return False


def make_capture(mutator=None, duration_scale: float = 1.0,
                 extra_descriptors: list[tuple[float, int, int]] | None = None) -> bytes:
    frames = canonical_frames()
    if mutator:
        frames = mutator(list(frames))
    rows = [(0.0, usbpcap(descriptor(), 1, 2, 0x80, transfer=2))]
    for timestamp, (label, raw, endpoint) in enumerate(frames, 1):
        del label
        rows.append((timestamp * 0.05 * duration_scale,
                     usbpcap(raw, 1, 2, endpoint)))
    for timestamp, bus, device in extra_descriptors or []:
        rows.append((timestamp, usbpcap(descriptor(), bus, device, 0x80, transfer=2)))
    rows.sort(key=lambda item: item[0])
    return pcapng(rows)


def replace_label(frames, label: str, raw: bytes, endpoint: int):
    index = next(i for i, row in enumerate(frames) if row[0] == label)
    frames[index] = (label, raw, endpoint)
    return frames


def remove_label(frames, label: str):
    return [row for row in frames if row[0] != label]


class D274Tests(unittest.TestCase):
    def run_capture(self, data: bytes, markers: Path | None = None):
        with tempfile.TemporaryDirectory(prefix="d274-test-") as directory:
            path = Path(directory) / "fixture.pcapng"
            path.write_bytes(data)
            return D274.process_capture(path, hashlib.sha256(data).hexdigest(),
                                        "SYNTHETIC_TEST", markers, "SYNTHETIC")

    def failure(self, data: bytes) -> str:
        try:
            result = self.run_capture(data)
            return result["failure_class"]
        except D274.EvidenceError as exc:
            return str(exc)

    def test_01_happy_path_synthetic_pcap(self):
        result = self.run_capture(make_capture())
        self.assertEqual(result["result_class"], "SYNTHETIC_FIXTURE_PASS")
        self.assertIsNone(result["failure_class"])
        self.assertFalse(result["second_cycle_target_observed"])
        self.assertFalse(result["privacy_payload_exported"])
        serialized = json.dumps(result).lower()
        self.assertNotIn('"raw"', serialized)
        self.assertNotIn('"body"', serialized)

    def test_02_missing_second_irq2(self):
        self.assertEqual(self.failure(make_capture(lambda f: remove_label(f, "second_irq2"))),
                         "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_03_second_irq2_missing_0x22(self):
        self.assertEqual(self.failure(make_capture(lambda f: remove_label(f, "second_0x22"))),
                         "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_04_wrong_0x20(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_up_0x20", a0(0x21, b"\x01\x00"), 0x01))),
            "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_05_wrong_0x50(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_up_0x50", a0(0x52), 0x01))),
            "PROTOCOL_SEQUENCE_OUT_OF_ALLOWLIST")

    def test_06_0x51_is_not_nav(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_0x50_nav", nav(0x51), 0x81))),
            "WIRE_0X51_IS_NOT_NAV")

    def test_07_ack_wrong_echo(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22_ack", a0(0xB0, b"\x20\x01"), 0x81))),
            "ACK_ECHO_MISMATCH")

    def test_08_ack_wrong_status(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22_ack", a0(0xB0, b"\x22\x07"), 0x81))),
            "ACK_STATUS_NOT_EXACT_0X01")

    def test_09_b0_before_second_0x22(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_0x22", b0(), 0x81))),
            "B0_BEFORE_SECOND_0X22")

    def test_10_third_cycle(self):
        def mutate(frames):
            frames.append(("third_irq2", a0(0x32, b"\x02\x00" + bytes(12)), 0x81))
            return frames
        self.assertEqual(self.failure(make_capture(mutate)), "THIRD_CYCLE_OBSERVED")

    def test_11_duplicate_0x22(self):
        def mutate(frames):
            index = next(i for i, row in enumerate(frames) if row[0] == "second_0x22_ack")
            frames.insert(index, ("duplicate_0x22", a0(0x22, b"\x01\x00"), 0x01))
            return frames
        self.assertEqual(self.failure(make_capture(mutate)), "DUPLICATE_SECOND_0X22")

    def test_12_duplicate_b0(self):
        self.assertEqual(self.failure(make_capture(
            lambda f: f + [("duplicate_b0", b0(), 0x81)])), "DUPLICATE_SECOND_B0")

    def test_13_reenumeration(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(3.1, 1, 2)])),
                         "TARGET_REENUMERATION_OBSERVED")

    def test_14_second_target(self):
        self.assertEqual(self.failure(make_capture(extra_descriptors=[(0.1, 1, 3)])),
                         "SECOND_TARGET_OBSERVED")

    def test_15_truncated_pcap_metadata(self):
        self.assertEqual(self.failure(make_capture()[:-3]), "TRUNCATED_PCAP_METADATA")

    def test_16_malformed_a0(self):
        def mutate(frames):
            bad = bytearray(a0(0x22, b"\x01\x00")); bad[-1] ^= 1
            return replace_label(frames, "second_0x22", bytes(bad), 0x01)
        self.assertEqual(self.failure(make_capture(mutate)), "MALFORMED_A0")

    def test_17_malformed_b0(self):
        def mutate(frames):
            bad = bytearray(b0())
            bad[1:3] = (len(bad) + 50).to_bytes(2, "little")
            return replace_label(frames, "second_b0", bytes(bad), 0x81)
        self.assertEqual(self.failure(make_capture(mutate)), "MALFORMED_B0")

    def test_18_capture_deadline(self):
        self.assertEqual(self.failure(make_capture(duration_scale=200)),
                         "CAPTURE_DEADLINE_EXCEEDED")

    def test_19_marker_out_of_order(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n2026-01-01T00:00:00Z\tVM_USB_ATTACH_END\n"
                              "2026-01-01T00:00:01Z\tVM_USB_ATTACH_BEGIN\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker), "MARKER_OUT_OF_ORDER")

    def failure_with_markers(self, data: bytes, marker: Path) -> str:
        try:
            self.run_capture(data, marker)
        except D274.EvidenceError as exc:
            return str(exc)
        return "NO_FAILURE"

    def test_20_ui_terminal_before_second_finger(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n"
                              "2026-01-01T00:00:00Z\tPREFLIGHT_COMPLETE\n"
                              "2026-01-01T00:00:01Z\tENROLLMENT_COMMIT_UI\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker), "UI_TERMINAL_CONDITION")

    def test_21_hash_gate(self):
        with tempfile.TemporaryDirectory(prefix="d274-hash-") as directory:
            path = Path(directory) / "fixture.pcapng"
            path.write_bytes(make_capture())
            with self.assertRaisesRegex(D274.EvidenceError, "CAPTURE_HASH_MISMATCH"):
                D274.process_capture(path, "0" * 64, "UNKNOWN")

    def test_22_schema_and_powershell_static_contract(self):
        schema = json.loads((ROOT / "analysis/D274/D274_01_evidence_schema.json").read_text())
        self.assertIn("second_b0_frame", schema["required"])
        self.assertIn("frameMetadata", schema.get("$defs", {}))
        self.assertFalse(schema["$defs"]["frameMetadata"]["additionalProperties"])
        script = (ROOT / "operator_kit/d274-windows-multiframe-evidence.ps1").read_text()
        script_lower = script.lower()
        self.assertIn("$script:D274RealCaptureCapability = 0", script)
        self.assertIn("$script:D274HardDisabled = $true", script)
        self.assertIn("HARD_DISABLED_D274_01", script)
        self.assertNotIn("Start-Process", script)
        self.assertNotIn(" -w ", script)
        # Privacy contract: ACL evaluable, no reparse/junction/symlink, no ACL mutation.
        self.assertIn("get-acl", script_lower)
        self.assertIn("reparsepoint", script_lower)
        # D274 Defect B: ACL privacy must not depend on AceType; it must use
        # AccessControlType, normalize identity to a SID via Translate, reject
        # Read/ReadAndExecute too, and enumerate the four canonical well-known
        # SIDs. Nominal principal names are not robust on localized Windows.
        self.assertNotIn(".acetype", script_lower)
        self.assertIn("accesscontroltype", script_lower)
        self.assertIn("[system.security.accesscontrol.filesystemrights]::read", script_lower)
        self.assertIn("translate(", script_lower)
        self.assertIn("securityidentifier", script_lower)
        for sid in ("S-1-1-0", "S-1-5-32-545", "S-1-5-11", "S-1-5-32-546"):
            self.assertIn(sid, script)
        self.assertNotIn("set-acl", script_lower)
        self.assertNotIn("icacls", script_lower)
        self.assertIn("output_root_privacy", script_lower)
        parameters = script.split("param(", 1)[1].split(")", 1)[0]
        for name in ("SelfTestOnly", "PreflightOnly", "PreAuthorizationSimulationOnly",
                     "IUnderstandAndAuthorizeOneD274WindowsMultiframeCapture"):
            self.assertIn("$" + name, parameters)

    def _historical_sanitized(self) -> dict:
        p = ROOT / "analysis/D230/work/GoodixExport/rilevamento.pcapng"
        data = p.read_bytes()
        return D274.process_capture(p, hashlib.sha256(data).hexdigest(),
                                    "SYNTHETIC", origin="SYNTHETIC")

    def test_23_generic_b0_is_not_fingerprint(self):
        # Positive: a correctly shaped fingerprint B0 closes the second cycle.
        result = self.run_capture(make_capture())
        self.assertIsNone(result["failure_class"])
        # Negative 1: short TLS-alert B0 after the second 0x22 ACK must NOT close.
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_alert(), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        # Negative 2: TLS app-data B0 with wrong total length must NOT close.
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_wrong_length(4000), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        # Negative 3: 7726-byte B0 with incoherent TLS declared length fails closed.
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_incoherent_tls_length(), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        # Negative 4: host->device B0 in the second-image position fails closed.
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0(), 0x01))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        # The generic-B0 shape also fails for the first and post-up positions.
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "first_image_b0", b0_alert(), 0x81))),
            "FIRST_B0_NOT_FINGERPRINT_SHAPE")
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "post_up_b0", b0_alert(), 0x81))),
            "POST_UP_B0_NOT_FINGERPRINT_SHAPE")

    def test_24_classify_b0_direct(self):
        fp = D274.Frame(0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0,
                        b0(), len(b0()))
        self.assertEqual(D274.classify_b0(fp), "FINGERPRINT_B0")
        alert = D274.Frame(0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0,
                           b0_alert(), len(b0_alert()))
        self.assertEqual(D274.classify_b0(alert), "B0_OTHER")
        host = D274.Frame(0, 0.0, 1, 2, "host_to_device", 0x01, 0xB0,
                          b0(), len(b0()))
        self.assertEqual(D274.classify_b0(host), "B0_OTHER")

    def test_25_credential_mutation_ui_terminal(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n"
                              "2026-01-01T00:00:00Z\tPREFLIGHT_COMPLETE\n"
                              "2026-01-01T00:00:01Z\tCREDENTIAL_MUTATION_UI\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker),
                             "UI_TERMINAL_CONDITION")

    def test_26_unknown_marker_fail_closed(self):
        with tempfile.TemporaryDirectory(prefix="d274-markers-") as directory:
            marker = Path(directory) / "markers.tsv"
            marker.write_text("timestamp_utc\tevent\n"
                              "2026-01-01T00:00:00Z\tPREFLIGHT_COMPLETE\n"
                              "2026-01-01T00:00:01Z\tSOMETHING_UNKNOWN\n", encoding="utf-8")
            self.assertEqual(self.failure_with_markers(make_capture(), marker),
                             "UNKNOWN_MARKER")

    def test_27_schema_instance_validation(self):
        schema = _load_schema()
        happy = self.run_capture(make_capture())
        self.assertTrue(_validate_instance_ok(happy, schema))
        historical = self._historical_sanitized()
        self.assertTrue(_validate_instance_ok(historical, schema))
        # Negative: extra arbitrary property inside a frame metadata object.
        bad_raw = copy.deepcopy(happy)
        bad_raw["second_b0_frame"]["raw"] = "deadbeef"
        self.assertFalse(_validate_instance_ok(bad_raw, schema))
        # Negative: wrong type on a required scalar.
        bad_type = copy.deepcopy(happy)
        bad_type["target_vid"] = 27
        self.assertFalse(_validate_instance_ok(bad_type, schema))
        # Negative: missing required field.
        bad_missing = copy.deepcopy(happy)
        del bad_missing["second_b0_frame"]
        self.assertFalse(_validate_instance_ok(bad_missing, schema))


    def test_28_tls_record_length_endianness(self):
        # The TLS record length is network byte order (big-endian), distinct from
        # the Goodix B0 outer length which is little-endian. The realistic header
        # 17 03 03 1e 25 (7717 = 0x1e25) must close as FINGERPRINT_B0; the
        # little-endian-encoded variant 17 03 03 25 1e must NOT, so a synthetic
        # fixture cannot redefine TLS semantics.
        declared_b0 = 7722
        tls_inner = declared_b0 - 5
        base = b"\xB0" + declared_b0.to_bytes(2, "little") + b"\x00" + b"\x17\x03\x03"
        big = D274.Frame(0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0,
                         base + tls_inner.to_bytes(2, "big") + bytes(tls_inner),
                         declared_b0 + 4)
        self.assertEqual(big.raw[4:9], b"\x17\x03\x03\x1e\x25")
        self.assertEqual(D274.classify_b0(big), "FINGERPRINT_B0")
        little = D274.Frame(0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0,
                            base + tls_inner.to_bytes(2, "little") + bytes(tls_inner),
                            declared_b0 + 4)
        self.assertEqual(D274.classify_b0(little), "B0_OTHER")
        # Fixture-level: the little-endian TLS fixture must not close either.
        le = b0_little_endian_tls()
        le_frame = D274.Frame(0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0, le, len(le))
        self.assertEqual(D274.classify_b0(le_frame), "B0_OTHER")
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_little_endian_tls(), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        # Negative controls still hold.
        self.assertEqual(D274.classify_b0(D274.Frame(
            0, 0.0, 1, 2, "device_to_host", 0x81, 0xB0, b0_alert(), len(b0_alert()))),
            "B0_OTHER")
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_wrong_length(4000), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0_incoherent_tls_length(), 0x81))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")
        self.assertEqual(self.failure(make_capture(
            lambda f: replace_label(f, "second_b0", b0(), 0x01))),
            "SECOND_B0_NOT_FINGERPRINT_SHAPE")

    def test_29_local_validator_integer_vs_number(self):
        # Force the local strict validator (independent of jsonschema presence).
        schema = _load_schema()
        happy = self.run_capture(make_capture())
        try:
            _local_validate(happy, schema)
        except D274.EvidenceError:
            self.fail("local strict validator rejected a valid document")
        # Positive type cases: integer frame and float relative_timestamp_ms.
        self.assertIsInstance(happy["second_b0_frame"]["frame"], int)
        self.assertIsInstance(happy["second_b0_frame"]["relative_timestamp_ms"], float)
        # Negative: float where schema requires integer must be rejected.
        neg_float = copy.deepcopy(happy)
        neg_float["second_b0_frame"]["frame"] = 1.5
        with self.assertRaises(D274.EvidenceError):
            _local_validate(neg_float, schema)
        # Negative: non-integer physical length must be rejected.
        neg_len = copy.deepcopy(happy)
        neg_len["second_b0_frame"]["physical_length"] = 7726.5
        with self.assertRaises(D274.EvidenceError):
            _local_validate(neg_len, schema)
        # Negative: string where schema requires integer must be rejected.
        neg_decl = copy.deepcopy(happy)
        neg_decl["second_b0_frame"]["declared_outer_length"] = "7726"
        with self.assertRaises(D274.EvidenceError):
            _local_validate(neg_decl, schema)
        # Negative: extra (private) property inside a frame must be rejected.
        neg_extra = copy.deepcopy(happy)
        neg_extra["second_b0_frame"]["raw"] = "deadbeef"
        with self.assertRaises(D274.EvidenceError):
            _local_validate(neg_extra, schema)
        # Negative: missing required field inside a frame must be rejected.
        neg_missing = copy.deepcopy(happy)
        neg_missing["second_b0_frame"].pop("direction")
        with self.assertRaises(D274.EvidenceError):
            _local_validate(neg_missing, schema)

    def test_30_runtime_evidence_contract_validation(self):
        # The production module enforces a fail-closed structural contract before
        # serialization (Section 5), with strict integer typing and a privacy
        # forbid-list.
        result = self.run_capture(make_capture())
        try:
            D274.validate_evidence_document_strict(result)
        except D274.EvidenceError:
            self.fail("runtime strict evidence contract rejected a valid document")
        # Float where schema requires integer must fail closed before serialization.
        bad_int = copy.deepcopy(result)
        bad_int["second_b0_frame"]["frame"] = 1.5
        with self.assertRaises(D274.EvidenceError):
            D274.validate_evidence_document_strict(bad_int)
        # A forbidden privacy-sensitive field must fail closed.
        bad_priv = copy.deepcopy(result)
        bad_priv["second_b0_frame"]["raw"] = "deadbeef"
        with self.assertRaises(D274.EvidenceError):
            D274.validate_evidence_document_strict(bad_priv)


if __name__ == "__main__":
    unittest.main(verbosity=2)
