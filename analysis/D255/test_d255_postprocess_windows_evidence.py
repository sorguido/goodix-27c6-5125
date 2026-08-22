#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import datetime as dt
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(__file__).with_name("d255_postprocess_windows_evidence.py")
POWERSHELL_PATH = REPOSITORY / "operator_kit/d255-windows-evidence-capture.ps1"
SPEC = importlib.util.spec_from_file_location("d255_postprocessor", MODULE_PATH)
assert SPEC and SPEC.loader
D255 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = D255
SPEC.loader.exec_module(D255)


def powershell_without_literals(source: str) -> str:
    """Small fail-closed fallback lexer used when pwsh is unavailable."""
    output: list[str] = []
    index = 0
    quote: str | None = None
    while index < len(source):
        char = source[index]
        if quote:
            if char == "`":
                index += 2
                continue
            if char == quote:
                if index + 1 < len(source) and source[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            output.append(" ")
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            output.append(" ")
            index += 1
            continue
        if char == "#":
            newline = source.find("\n", index)
            if newline < 0:
                break
            output.append(" " * (newline - index))
            index = newline
            continue
        output.append(char)
        index += 1
    if quote:
        raise AssertionError("unterminated PowerShell string")
    return "".join(output)


def assert_balanced_powershell(testcase: unittest.TestCase, source: str) -> None:
    stripped = powershell_without_literals(source)
    pairs = {")": "(", "]": "[", "}": "{"}
    stack: list[str] = []
    for char in stripped:
        if char in "([{":
            stack.append(char)
        elif char in pairs:
            testcase.assertTrue(stack, f"unexpected closing {char}")
            testcase.assertEqual(stack.pop(), pairs[char])
    testcase.assertEqual(stack, [], "unclosed PowerShell delimiter")


class D255PostprocessorTests(unittest.TestCase):
    def fixture(self, **kwargs):
        temporary = tempfile.TemporaryDirectory(prefix="d255-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        run = root / "run"
        manifest, digest = D255.create_synthetic_fixture(run, **kwargs)
        return root, run, manifest, digest

    def analyze_fixture(self, **kwargs):
        root, run, manifest, digest = self.fixture(**kwargs)
        output = root / "sanitized"
        result = D255.analyze(run, manifest, digest, output)
        return result, output

    def test_complete_synthetic_fixture(self):
        result, _ = self.analyze_fixture()
        self.assertEqual(result["target"]["CAPTURE_FIRMWARE"], D255.EXPECTED_FIRMWARE)
        self.assertTrue(result["target"]["D255_EVIDENCE_TARGET_SPECIFIC"])
        self.assertEqual(result["seed_correlation"]["SEED_SOURCE_CLASS"],
                         "CACHE_AND_LOG_WIRE_MATCH")
        self.assertFalse(result["seed_correlation"]["CAUSALITY_PROVEN"])
        self.assertEqual(result["restore_cancel"]["REENTRY_PROOF_CLASS"],
                         "REENTRY_WITHOUT_FINGER")
        self.assertEqual(result["vm_boundary"]["D255_BOOTSTRAP_EVIDENCE_VALIDITY"],
                         "VALID_COLD_ATTACH")
        self.assertEqual(result["vm_boundary"]["VM_USB_ATTACH_COUNT"], 1)
        self.assertTrue(result["vm_boundary"]["CAPTURE_STARTED_BEFORE_VM_USB_ATTACH"])
        self.assertTrue(result["vm_boundary"]["A8_APP12509_PROVEN"])
        self.assertEqual(result["zero_finger"], {
            "FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS": 0,
            "POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS": 0,
            "FINGER_IMAGE_PATH_COUNT_IN_OPERATOR_WINDOWS": 0,
            "FINGER_INTERACTION_DETECTED": False,
        })
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIMESTAMP_FORMATS"],
                         ["GOODIX_MMDD_LOCAL"])
        self.assertEqual(result["oem_log_time"]["OEM_LOG_UNTIMED_EVENT_COUNT"], 0)
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"],
                         "EXACT_ANCHORED")
        events = {row["event"]: row for row in result["oem_log_events"]}
        self.assertEqual(events["HOST_CANCEL"]["time_window"], "CANCEL")
        self.assertEqual(events["D0_EXIT"]["time_window"], "CANCEL")
        self.assertEqual(events["D0_ENTRY"]["time_window"], "REENTRY")
        self.assertTrue(all(row["timestamp_utc"] is not None
                            for row in result["oem_log_events"]))
        contract = result["physical_fdt36_contract"]
        self.assertEqual(contract["FDT36_COUNT"], 1)
        self.assertEqual(contract["FDT36_LOGICAL_LENGTHS"], [22])
        self.assertEqual(contract["FDT36_PHYSICAL_LENGTHS"], [64])

    def test_wrong_size_cache_is_not_promoted(self):
        result, _ = self.analyze_fixture(cache_size=127)
        self.assertFalse(any(row["LAYOUT_13520_COMPATIBLE"]
                             for row in result["cache_candidates"]))
        self.assertEqual(result["seed_correlation"]["CACHE_FDT12_MATCH"], "unknown")

    def test_crc_failure_is_reported(self):
        result, _ = self.analyze_fixture(crc_valid=False)
        compatible = [row for row in result["cache_candidates"]
                      if row["LAYOUT_13520_COMPATIBLE"]]
        self.assertTrue(compatible)
        self.assertTrue(all(row["CRC_VALID"] is False for row in compatible))

    def test_mismatched_seed(self):
        result, _ = self.analyze_fixture(seed_match=False)
        self.assertFalse(result["seed_correlation"]["CACHE_FDT12_MATCH"])
        self.assertFalse(result["seed_correlation"]["OEM_LOG_FDT12_MATCH"])
        self.assertEqual(result["seed_correlation"]["SEED_SOURCE_CLASS"], "NO_MATCH")

    def test_missing_firmware_a8_fails_target_gate(self):
        root, run, manifest, digest = self.fixture(firmware=False)
        with self.assertRaisesRegex(D255.EvidenceError, "A8 APP12509 proof is absent"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_capture_without_target_enumeration_is_invalid(self):
        root, run, manifest, digest = self.fixture(enumeration=False)
        with self.assertRaisesRegex(D255.EvidenceError, "enumeration/attach is absent"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_guest_target_must_be_absent_before_attach(self):
        root, run, manifest, digest = self.fixture(guest_before_count=1)
        with self.assertRaisesRegex(D255.EvidenceError,
                                    "guest_topology_before target presence count is not 0"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_guest_target_presence_is_required_after_attach(self):
        root, run, manifest, digest = self.fixture(guest_after_count=0)
        with self.assertRaisesRegex(D255.EvidenceError,
                                    "guest_topology_after_attach target presence count is not 1"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_attach_before_capture_is_invalid_bootstrap(self):
        root, run, manifest, digest = self.fixture(attach_before_capture=True)
        with self.assertRaisesRegex(D255.EvidenceError, "INVALID_DEVICE_ALREADY_ATTACHED"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_second_attach_or_device_address_is_invalid_topology(self):
        root, run, manifest, digest = self.fixture(second_attach=True)
        with self.assertRaisesRegex(D255.EvidenceError, "INVALID_VM_USB_TOPOLOGY_CHANGE"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_single_finger_irq_invalidates_zero_finger_evidence(self):
        result, _ = self.analyze_fixture(finger_irq=True)
        self.assertEqual(result["zero_finger"]["FINGER_DOWN_IRQ_COUNT_IN_OPERATOR_WINDOWS"], 1)
        self.assertTrue(result["zero_finger"]["FINGER_INTERACTION_DETECTED"])
        self.assertEqual(result["vm_boundary"]["D255_EVIDENCE_VALIDITY"],
                         "INVALID_FINGER_INTERACTION")
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

    def test_cmd22_invalidates_zero_finger_evidence(self):
        result, _ = self.analyze_fixture(cmd22=True)
        self.assertEqual(result["zero_finger"]["POST_IRQ2_0x22_COUNT_IN_OPERATOR_WINDOWS"], 1)
        self.assertTrue(result["zero_finger"]["FINGER_INTERACTION_DETECTED"])
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

    def test_image_path_invalidates_zero_finger_evidence(self):
        result, _ = self.analyze_fixture(image_path=True)
        self.assertEqual(result["zero_finger"]["FINGER_IMAGE_PATH_COUNT_IN_OPERATOR_WINDOWS"], 1)
        self.assertTrue(result["zero_finger"]["FINGER_INTERACTION_DETECTED"])
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

    def test_cancel_marker_missing(self):
        root, run, manifest, digest = self.fixture(cancel_marker=False)
        with self.assertRaisesRegex(D255.EvidenceError, "CANCEL_NO_FINGER_BEGIN"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_cancel_before_arm(self):
        root, run, manifest, digest = self.fixture(cancel_before_arm=True)
        with self.assertRaisesRegex(D255.EvidenceError, "before any observed 0x32"):
            D255.analyze(run, manifest, digest, root / "out")

    def test_reentry_missing_is_inconclusive(self):
        result, _ = self.analyze_fixture(reentry=False)
        self.assertFalse(result["restore_cancel"]["DETERMINISTIC_REENTRY_PROVEN"])
        self.assertEqual(result["restore_cancel"]["REENTRY_PROOF_CLASS"],
                         "REENTRY_NOT_PROVEN")

    def test_unknown_new_control_is_preserved_as_metadata(self):
        result, _ = self.analyze_fixture(unknown_control=True)
        self.assertEqual(result["unknown_controls"], ["0x66"])
        self.assertIn("0x66", result["restore_cancel"]["CANCEL_NO_FINGER_DEVICE_COMMANDS"])

    def test_raw_biometric_otp_and_secret_are_redacted(self):
        secret = "SYNTHETIC_PSK_BIOMETRIC_OTP_NEVER_EXPORT"
        result, output = self.analyze_fixture(secret_marker=secret)
        serialized = json.dumps(result)
        disk_output = "\n".join(path.read_text(errors="replace") for path in output.iterdir())
        self.assertNotIn(secret, serialized)
        self.assertNotIn(secret, disk_output)
        self.assertNotIn(bytes(range(64)).hex(), serialized)
        self.assertFalse(result["safety"]["raw_biometric_exported"])
        self.assertFalse(result["safety"]["otp_raw_exported"])
        self.assertFalse(result["safety"]["psk_or_secret_exported"])

    def test_input_manifest_hash_gate(self):
        root, run, manifest, _ = self.fixture()
        with self.assertRaisesRegex(D255.EvidenceError, "manifest hash mismatch"):
            D255.analyze(run, manifest, "0" * 64, root / "out")

    def test_output_collision_fails_closed(self):
        root, run, manifest, digest = self.fixture()
        output = root / "out"
        output.mkdir()
        with self.assertRaisesRegex(D255.EvidenceError, "output collision"):
            D255.analyze(run, manifest, digest, output)

    def test_synthetic_fixture_collision(self):
        root, _, _, _ = self.fixture()
        existing = root / "existing"
        existing.mkdir()
        with self.assertRaisesRegex(D255.EvidenceError, "fixture output collision"):
            D255.create_synthetic_fixture(existing)

    def test_powershell_static_syntax_and_safety_contract(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        assert_balanced_powershell(self, source)
        required = (
            "[switch]$SelfTestOnly",
            "[switch]$PreflightOnly",
            "$ExpectedAuthorization = \"--i-authorize-one-d255-windows-oem-evidence-capture\"",
            "if ($Authorization -cne $ExpectedAuthorization)",
            "if (-not (Test-D255PathAvailable -Path $script:RunDirectory))",
            "D255_REPEAT_FORBIDDEN_WITHOUT_NEW_AUTHORIZATION=true",
            "CANCEL_NO_FINGER_BEGIN",
            "REENTRY_WAITING_NO_FINGER",
            "REENTRY_CANCEL_BEGIN",
            "REENTRY_CANCEL_END",
            "VM_GUEST_READY",
            "GUEST_TOPOLOGY_BEFORE",
            "VM_USB_ATTACH_BEGIN",
            "VM_USB_ATTACH_END",
            "GUEST_27C6_5125_PRESENT",
            "OEM_SESSION_BEGIN",
            "OEM_WAITING_NO_FINGER",
            "WINDOWS_HELLO_SETUP_NO_FINGER",
            "SETUP_NO_FINGER_PATH_VERIFIED_NO_NEW_PIN",
            "USBPCAP_INTERFACE_SELECTION=AMBIGUOUS",
            "duration:$CaptureDurationSeconds",
            "D255_POWERSHELL_SELFTEST=PASS",
            "D255_AUTHORIZATION_CONSUMED=false",
            "function Get-D255Sha256HexForString",
            "[Security.Cryptography.SHA256]::Create()",
            "function Get-D255RelativePath",
            "function Test-D255PathAvailable",
            "function New-D255ClockAnchor",
            'Write-OperatorMarker -Event "CLOCK_ANCHOR"',
            'schema = "D255_WINDOWS_EVIDENCE_INPUT_MANIFEST_V3"',
        )
        for token in required:
            self.assertIn(token, source)
        self.assertNotRegex(source, r"(?im)^\s*(?:Invoke-Expression|Remove-Item|Format-Volume|Clear-Disk)\b")
        self.assertNotRegex(source, r"(?i)Start-Service\s+.*(?:provision|firmware|flash)")
        for unsupported in (
            "[Convert]::ToHexString",
            "[Security.Cryptography.SHA256]::HashData",
            "[System.IO.Path]::GetRelativePath",
        ):
            self.assertNotIn(unsupported, source)
        self.assertNotIn("AllowReentryFinger", source)
        self.assertNotIn("recognition prompt", source.lower())
        self.assertNotRegex(source, r"(?i)\b(?:virsh|virt-manager|qemu|spice|hostdev)\b")

    def test_powershell_authorization_gate_follows_all_pre_hardware_setup(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        gate = source.index('if ($Authorization -cne $ExpectedAuthorization)')
        consumed = source.index('$script:AuthorizationConsumed = $true')
        start_capture = source.index('$script:CaptureProcess = Start-Process')
        required_before_gate = (
            '$initialTargets = @(Get-TargetDevices)',
            'New-D255ClockAnchor -Phase "BEFORE_CAPTURE"',
            'Write-OemLogSnapshot -Stage "before"',
            'Write-FileSnapshot -Stage "before"',
            '$preflight["runtime"] = Get-D255RuntimeInfo',
            '$captureArguments =',
        )
        for token in required_before_gate:
            position = (source.rindex(token) if token == '$preflight["runtime"] = Get-D255RuntimeInfo'
                        else source.index(token))
            self.assertLess(position, gate, token)
        self.assertLess(source.index('Write-FileSnapshot -Stage "before"'),
                        source.rindex('$preflight["runtime"] = Get-D255RuntimeInfo'))
        self.assertLess(gate, consumed)
        self.assertLess(consumed, start_capture)

    def test_usbpcap_single_interface_is_unambiguous(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn('if ($usbPcapCandidates.Count -eq 1) { "UNAMBIGUOUS" }', source)
        self.assertIn('$usbPcapCandidates = @($interfaceLines | Where-Object', source)

    def test_usbpcap_multi_interface_requires_capture_all(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn('[string[]]$CaptureInterface = @()', source)
        self.assertIn('$interfaceMatches.Count -ne $usbPcapCandidates.Count', source)
        self.assertIn('"CAPTURE_ALL"', source)
        self.assertIn('$captureSelectors = @($CaptureInterface | ForEach-Object', source)

    def test_iso_timestamp_regression(self):
        result, _ = self.analyze_fixture(oem_timestamp_format="iso")
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIMESTAMP_FORMATS"], ["ISO8601"])
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"],
                         "EXACT_ANCHORED")
        self.assertNotEqual(result["restore_cancel"]["RESTORE_MODEL"],
                            "INCONCLUSIVE_OEM_TIME_CORRELATION")

    def test_goodix_mmdd_same_day(self):
        result, _ = self.analyze_fixture()
        critical = [row for row in result["oem_log_events"]
                    if row["event"] in {"HOST_CANCEL", "D0_EXIT", "D0_ENTRY"}]
        self.assertEqual(len(critical), 3)
        self.assertTrue(all(row["timestamp_source"] == "GOODIX_MMDD_LOCAL"
                            and row["time_correlation_quality"] == "EXACT_ANCHORED"
                            for row in critical))

    def test_goodix_midnight_rollover(self):
        base = dt.datetime(2026, 8, 22, 21, 59, 56, tzinfo=dt.timezone.utc).timestamp()
        result, _ = self.analyze_fixture(base_timestamp=base, clock_offset_minutes=120)
        events = {row["event"]: row for row in result["oem_log_events"]}
        self.assertEqual(events["HOST_CANCEL"]["time_window"], "CANCEL")
        self.assertEqual(events["D0_ENTRY"]["time_window"], "REENTRY")
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"],
                         "EXACT_ANCHORED")

    def test_goodix_year_rollover(self):
        base = dt.datetime(2026, 12, 31, 22, 59, 56, tzinfo=dt.timezone.utc).timestamp()
        result, _ = self.analyze_fixture(base_timestamp=base, clock_offset_minutes=60)
        events = {row["event"]: row for row in result["oem_log_events"]}
        self.assertTrue(events["HOST_CANCEL"]["timestamp_utc"].startswith("2026-12-31T23:00:00"))
        self.assertEqual(events["D0_ENTRY"]["time_window"], "REENTRY")

    def test_goodix_malformed_mmdd_is_ambiguous(self):
        clock = D255.ClockContext(2026, 120, "W. Europe Standard Time", 0, 2_000_000_000, True)
        timestamp, source, quality = D255._oem_timestamp(
            "[1332-08:14:10:100] gfOnCancel", clock)
        self.assertIsNone(timestamp)
        self.assertEqual(source, "GOODIX_MMDD_LOCAL")
        self.assertEqual(quality, "AMBIGUOUS")

    def test_goodix_offset_change_fails_closed(self):
        result, _ = self.analyze_fixture(end_clock_offset_minutes=60)
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"], "AMBIGUOUS")
        self.assertEqual(result["restore_cancel"]["RESTORE_MODEL"],
                         "INCONCLUSIVE_OEM_TIME_CORRELATION")
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])
        self.assertEqual(result["restore_cancel"]["CANCEL_IS_HOST_ONLY"], "unknown")
        self.assertEqual(result["restore_cancel"]["USB_CLOSE_AFTER_CANCEL"], "unknown")

    def test_goodix_ambiguous_mapping_fails_closed(self):
        result, _ = self.analyze_fixture(goodix_month_day=(1, 1))
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"], "AMBIGUOUS")
        self.assertEqual(result["restore_cancel"]["RESTORE_MODEL"],
                         "INCONCLUSIVE_OEM_TIME_CORRELATION")
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

    def test_oem_log_unchanged(self):
        result, _ = self.analyze_fixture(log_change="unchanged")
        self.assertTrue(result["oem_log_state"]["LOG_UNCHANGED"])
        self.assertFalse(result["oem_log_state"]["LOG_GREW"])
        self.assertFalse(result["oem_log_state"]["LOG_ROTATED_OR_TRUNCATED"])

    def test_oem_log_growth(self):
        result, _ = self.analyze_fixture(log_change="growth")
        self.assertTrue(result["oem_log_state"]["LOG_GREW"])
        self.assertTrue(result["oem_log_state"]["WINDOW_RECONSTRUCTIBLE"])

    def test_oem_log_truncate_fails_closed(self):
        result, _ = self.analyze_fixture(log_change="truncate")
        self.assertEqual(result["oem_log_state"]["sources"][0]["change"], "TRUNCATED")
        self.assertTrue(result["oem_log_state"]["LOG_ROTATED_OR_TRUNCATED"])
        self.assertEqual(result["restore_cancel"]["RESTORE_MODEL"],
                         "INCONCLUSIVE_OEM_TIME_CORRELATION")
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

    def test_oem_log_replace_fails_closed(self):
        result, _ = self.analyze_fixture(log_change="replace")
        self.assertEqual(result["oem_log_state"]["sources"][0]["change"],
                         "REPLACED_OR_ROTATED")
        self.assertTrue(result["oem_log_state"]["LOG_ROTATED_OR_TRUNCATED"])
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"], "AMBIGUOUS")

    def test_powershell_authorization_missing_and_wrong_are_rejected_by_exact_contract(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        match = re.search(r'\$ExpectedAuthorization\s*=\s*"([^"]+)"', source)
        self.assertIsNotNone(match)
        expected = match.group(1)
        accepted = lambda supplied: supplied == expected
        self.assertFalse(accepted(""))
        self.assertFalse(accepted(expected.upper()))
        self.assertFalse(accepted(expected + "-again"))
        self.assertTrue(accepted(expected))


if __name__ == "__main__":
    unittest.main(verbosity=2)
