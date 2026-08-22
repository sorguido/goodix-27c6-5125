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
sys.modules["d255_postprocess_windows_evidence"] = D255
RECOVERY_PATH = Path(__file__).with_name("d255_recover_existing_run.py")
RECOVERY_SPEC = importlib.util.spec_from_file_location("d255_recovery", RECOVERY_PATH)
assert RECOVERY_SPEC and RECOVERY_SPEC.loader
RECOVERY = importlib.util.module_from_spec(RECOVERY_SPEC)
RECOVERY_SPEC.loader.exec_module(RECOVERY)


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
        self.assertEqual(result["evidence_sources"], {
            "OEM_LOG_STATUS": "PRESENT",
            "OEM_LOG_SOURCE_COUNT": 1,
            "GOODIX_CACHE_STATUS": "PRESENT",
            "GOODIX_CACHE_SOURCE_COUNT": 1,
        })
        self.assertEqual(result["seed_correlation"]["SEED_SOURCE_CLASS"],
                         "CACHE_AND_LOG_WIRE_MATCH")
        self.assertFalse(result["seed_correlation"]["CAUSALITY_PROVEN"])
        self.assertEqual(result["restore_cancel"]["REENTRY_PROOF_CLASS"],
                         "REENTRY_WITHOUT_FINGER")
        self.assertTrue(result["restore_cancel"]["OEM_CANCEL_REENTRY_PROVEN"])
        self.assertTrue(result["restore_cancel"]["NEW_FDT_ARM_ACCEPTED_ON_REENTRY"])
        self.assertFalse(result["restore_cancel"]["DEVICE_FDT_DISARM_PROVEN"])
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

        self.assertEqual(result["restore_cancel"]["RESTORE_CLOSURE_DECISION"],
                         "AI_PM_REVIEW_REQUIRED")
        self.assertEqual(result["restore_cancel"]["PRIOR_ARM_LIFETIME_AFTER_CANCEL"],
                         "UNKNOWN_OR_NOT_DIRECTLY_OBSERVED")
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

    def test_zero_oem_logs_with_goodix_cache_is_accepted_and_reported(self):
        result, output = self.analyze_fixture(include_oem_log=False)
        self.assertEqual(result["evidence_sources"]["OEM_LOG_STATUS"], "ABSENT")
        self.assertEqual(result["evidence_sources"]["OEM_LOG_SOURCE_COUNT"], 0)
        self.assertEqual(result["evidence_sources"]["GOODIX_CACHE_STATUS"], "PRESENT")
        self.assertEqual(result["seed_correlation"]["CACHE_FDT12_MATCH"], True)
        self.assertEqual(result["seed_correlation"]["OEM_LOG_FDT12_MATCH"], "unknown")
        self.assertEqual(result["oem_log_time"]["OEM_LOG_TIME_CORRELATION"],
                         "UNAVAILABLE_NO_OEM_LOG")
        summary = (output / "D255_sanitized_summary.txt").read_text(encoding="ascii")
        self.assertIn("OEM_LOG_STATUS=ABSENT\n", summary)
        self.assertIn("GOODIX_CACHE_STATUS=PRESENT\n", summary)

    def test_absent_goodix_cache_is_distinguished_from_present_oem_log(self):
        result, output = self.analyze_fixture(include_cache=False)
        self.assertEqual(result["evidence_sources"]["OEM_LOG_STATUS"], "PRESENT")
        self.assertEqual(result["evidence_sources"]["GOODIX_CACHE_STATUS"], "ABSENT")
        self.assertEqual(result["evidence_sources"]["GOODIX_CACHE_SOURCE_COUNT"], 0)
        summary = (output / "D255_sanitized_summary.txt").read_text(encoding="ascii")
        self.assertIn("OEM_LOG_STATUS=PRESENT\n", summary)
        self.assertIn("GOODIX_CACHE_STATUS=ABSENT\n", summary)

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

    def test_partial_bootstrap_ui_unavailable_preserves_seed_without_restore(self):
        result, output = self.analyze_fixture(ui_result="UI_UNAVAILABLE")
        self.assertEqual(result["run_classification"]["D255_RUN_RESULT"],
                         "PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE")
        self.assertTrue(result["run_classification"]["BOOTSTRAP_EVIDENCE_PRESERVED"])
        self.assertFalse(result["run_classification"]["RESTORE_EVIDENCE_ACQUIRED"])
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])
        self.assertEqual(result["restore_cancel"]["RESTORE_EVIDENCE_CLASS"],
                         "NO_RESTORE_EVIDENCE")
        self.assertEqual(result["seed_correlation"]["FIRST_FDT36_SEED"],
                         "adadbdbda3a3b1b1a6a6b2b2")
        summary = (output / "D255_sanitized_summary.txt").read_text(encoding="ascii")
        self.assertIn("BOOTSTRAP_EVIDENCE_PRESERVED=true", summary)
        self.assertIn("RESTORE_EVIDENCE_ACQUIRED=false", summary)

    def test_partial_bootstrap_new_pin_required_is_terminal(self):
        result, _ = self.analyze_fixture(ui_result="NEW_PIN_REQUIRED")
        self.assertEqual(result["ui_gate"]["HELLO_SETUP_UI_RESULT"], "NEW_PIN_REQUIRED")
        self.assertFalse(result["restore_cancel"]["RESTORE_EVIDENCE_ACQUIRED"])

    def test_partial_bootstrap_unexpected_prerequisite_is_terminal(self):
        result, _ = self.analyze_fixture(ui_result="UNEXPECTED_PREREQUISITE")
        self.assertEqual(result["ui_gate"]["HELLO_SETUP_UI_RESULT"],
                         "UNEXPECTED_PREREQUISITE")
        self.assertFalse(result["restore_cancel"]["OEM_CANCEL_REENTRY_PROVEN"])

    def test_reentry_and_new_arm_never_close_restore(self):
        result, _ = self.analyze_fixture()
        restore = result["restore_cancel"]
        self.assertTrue(restore["OEM_CANCEL_REENTRY_PROVEN"])
        self.assertTrue(restore["NEW_FDT_ARM_ACCEPTED_ON_REENTRY"])
        self.assertFalse(restore["DEVICE_FDT_DISARM_PROVEN"])
        self.assertFalse(restore["RESTORE_CLOSED"])
        self.assertEqual(restore["RESTORE_EVIDENCE_CLASS"],
                         "REENTRY_ACCEPTS_NEW_ARM_PRIOR_ARM_STATUS_UNKNOWN")

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
            "[switch]$PreAuthorizationSimulationOnly",
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
            "ACCOUNT_PREREQUISITES_CHECKED",
            "PASSIVE_BOOTSTRAP_SETTLED",
            "HELLO_SETUP_UI_CHECK_BEGIN",
            "HELLO_SETUP_UI_READY",
            "HELLO_SETUP_UI_UNAVAILABLE",
            "HELLO_SETUP_NEW_PIN_REQUIRED",
            "HELLO_SETUP_UNEXPECTED_PREREQUISITE",
            "OEM_SESSION_BEGIN",
            "OEM_WAITING_NO_FINGER",
            "WINDOWS_HELLO_SETUP_NO_FINGER",
            "AccountPrerequisiteConfirmation",
            "SIGNIN_OPTIONS_CHECKED_NO_NEW_PIN_CHANGE",
            "WindowsHelloPinState",
            "NOT_REQUIRED_BY_CURRENT_ACCOUNT_POLICY",
            "FingerprintSetupPinRequirement",
            "SENSOR_DEPENDENT_UI_AVAILABILITY",
            "UNKNOWN_BEFORE_ATTACH",
            "PARTIAL_BOOTSTRAP_ONLY_UI_UNAVAILABLE",
            "PromptForChoice",
            "USBPCAP_INTERFACE_SELECTION=AMBIGUOUS",
            "duration:$DurationSeconds",
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
        self.assertNotIn("SETUP_NO_FINGER_PATH_" + "VERIFIED_NO_NEW_PIN", source)
        self.assertNotIn("UiPrerequisite" + "Confirmation", source)
        self.assertNotIn("recognition prompt", source.lower())
        self.assertNotRegex(source, r"(?i)\b(?:virsh|virt-manager|qemu|spice|hostdev)\b")

    def test_powershell_preattach_gate_is_account_only(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn('account_prerequisites_ready = $true', source)
        self.assertIn('sensor_dependent_ui_availability = "UNKNOWN_BEFORE_ATTACH"', source)
        self.assertIn('preattach_fingerprint_ui_required = $false', source)
        self.assertNotIn("SETUP_NO_FINGER_PATH_" + "VERIFIED_NO_NEW_PIN", source)
        confirmation = re.search(
            r'\$ExpectedAccountPrerequisiteConfirmation\s*=\s*"([^"]+)"', source)
        self.assertIsNotNone(confirmation)
        self.assertNotRegex(confirmation.group(1), r"(?i)finger|sensor|wizard|setup.*path")

    def test_powershell_preattach_capture_readiness_allows_missing_or_empty_file(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        readiness = source[source.index("function Test-D255PreAttachReadinessState"):
                           source.index("function Test-D255FinalCaptureValidationState")]
        self.assertIn("$ProcessAlive -and $GuestTargetCount -eq 0", readiness)
        self.assertNotRegex(readiness, r"(?i)Test-Path|Get-Item|Length|pcap")

        live_gate = source[source.index("Start-Sleep -Seconds 2"):
                           source.index('Write-OperatorMarker -Event "VM_USB_ATTACH_BEGIN"')]
        self.assertIn("$preAttachTargets = @(Get-TargetDevices)", live_gate)
        self.assertIn("Test-D255PreAttachReadinessState", live_gate)
        self.assertIn('Fail-D255Capture "capture process exited during the pre-attach grace period"',
                      live_gate)
        self.assertNotRegex(live_gate, r"(?i)Test-Path|Get-Item|\.Length")
        self.assertIn('Write-OperatorMarker -Event "CAPTURE_PROCESS_STARTED"', live_gate)
        self.assertIn("pcapng existence/nonempty state not asserted", live_gate)

    def test_powershell_selftest_covers_preattach_readiness_states_offline(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        selftest = source[source.index("function Invoke-D255SelfTest"):
                          source.index("$selectedModeCount = 0")]
        for token in (
                "missing.pcapng",
                "zero.pcapng",
                "-ProcessAlive $true -GuestTargetCount 0",
                "-ProcessAlive $false -GuestTargetCount 0",
                "-ProcessAlive $true -GuestTargetCount 1",
                "D255_CAPTURE_READINESS_SELFTEST=PASS"):
            self.assertIn(token, selftest)
        self.assertIn("hardware_action_count = 0", selftest)

    def test_powershell_postattach_materialization_and_final_validation_remain_strong(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        materialization = source.index(
            'Fail-D255Capture "capture output was not materialized after attach and passive bootstrap"')
        attach_end = source.index('Write-OperatorMarker -Event "VM_USB_ATTACH_END"')
        passive_settle = source.index('Write-OperatorMarker -Event "PASSIVE_BOOTSTRAP_SETTLED"')
        self.assertLess(attach_end, materialization)
        self.assertLess(materialization, passive_settle)
        self.assertIn('Write-OperatorMarker -Event "CAPTURE_OUTPUT_MATERIALIZED"', source)

        final_state = source[source.index("function Test-D255FinalCaptureValidationState"):
                             source.index("function ConvertTo-D255RedactedDiagnosticText")]
        for token in ("$null -eq $TsharkExitCode", "PASS_WITH_EXIT_CODE_UNAVAILABLE",
                      "$PcapngExists", "$PcapngLength -gt 0",
                      "$ReadableFrameCount -ge 1", "FAIL_CLOSED"):
            self.assertIn(token, final_state)
        final_path = source[source.index("Wait-Process -Id $script:CaptureProcess.Id"):]
        self.assertIn("Test-D255FinalCaptureValidationState", final_path)
        self.assertIn("$captureValidation -contains \"1\"", final_path)
        self.assertIn('Write-Output "TSHARK_EXIT_CODE=$tsharkExitCodeText"', final_path)
        self.assertIn("$script:CaptureProcess.HasExited", final_path)
        self.assertIn("D255_CAPTURE_RESULT=CAPTURED_PENDING_OFFLINE_VALIDATION", final_path)
        self.assertLess(final_path.index("Test-D255FinalCaptureValidationState"),
                        final_path.index("D255_CAPTURE_RESULT=CAPTURED_PENDING_OFFLINE_VALIDATION"))

    def test_powershell_capture_failure_diagnostics_are_redacted_and_useful(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        diagnostics = source[source.index("function ConvertTo-D255RedactedDiagnosticText"):
                             source.index("function Assert-CaptureActive")]
        for token in ("<run-directory>", "<capture-output>", "<tshark-executable>",
                      "process_state=", "exit_code=", "command_arguments=",
                      "output_path_state=", "stdout=", "stderr="):
            self.assertIn(token, diagnostics)
        start = source[source.index("$script:CaptureProcess = Start-Process"):
                       source.index("Start-Sleep -Seconds 2")]
        self.assertIn("-RedirectStandardOutput", start)
        self.assertIn("-RedirectStandardError", start)
        self.assertIn("$script:CaptureProcessHandle = $script:CaptureProcess.Handle", start)
        self.assertIn('Fail-D255Capture "capture process failed to start:', start)

    def test_powershell_finalization_matrix_covers_exitcode_cases(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        selftest = source[source.index("function Invoke-D255SelfTest"):
                          source.index("$selectedModeCount = 0")]
        cases = (
            '-TsharkExitCode 0 -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "PASS"',
            '-TsharkExitCode $null -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "PASS_WITH_EXIT_CODE_UNAVAILABLE"',
            '-TsharkExitCode $null -PcapngExists $false -PcapngLength 0 -ReadableFrameCount 0) -cne "FAIL_CLOSED"',
            '-TsharkExitCode $null -PcapngExists $true -PcapngLength 0 -ReadableFrameCount 0) -cne "FAIL_CLOSED"',
            '-TsharkExitCode $null -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 0) -cne "FAIL_CLOSED"',
            '-TsharkExitCode 7 -PcapngExists $true -PcapngLength 1 -ReadableFrameCount 1) -cne "FAIL_CLOSED"',
        )
        for case in cases:
            self.assertIn(case, selftest)

    def test_offline_recovery_preserves_raw_and_supports_postprocessing(self):
        temporary = tempfile.TemporaryDirectory(prefix="d255-recovery-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        run = root / RECOVERY.RUN_NAME
        D255.create_synthetic_fixture(run)
        (run / "input_manifest.json").unlink()
        for path in (
                run / "run_clock_end.json",
                run / "guest_topology_after_capture.json",
                run / "cache_after_metadata.json",
                run / "raw/cache_after/candidate.bin",
                run / "raw/oem_logs_after/oem_000.log"):
            path.unlink()
        for directory in (run / "raw/cache_after", run / "raw/oem_logs_after"):
            directory.rmdir()
        wire = run / "raw/wire.pcapng"
        before_hash = D255.sha256_file(wire)
        before_stat = wire.stat()

        report = RECOVERY.recover(run)
        self.assertEqual(report["result"],
                         "PASS_RECOVERED_READY_FOR_OFFLINE_POSTPROCESSING")
        self.assertFalse(report["pcap"]["modified"])
        self.assertEqual(report["safety"]["real_usb_open_count"], 0)
        self.assertEqual(report["safety"]["real_capture_count"], 0)
        self.assertEqual(report["safety"]["real_hardware_action_count"], 0)
        self.assertEqual(D255.sha256_file(wire), before_hash)
        self.assertEqual(wire.stat().st_mtime_ns, before_stat.st_mtime_ns)
        self.assertEqual(report["artifact_status"]["run_clock_end.json"],
                         "NOT_RECOVERABLE")

        output = root / "sanitized-recovery"
        result = D255.analyze(
            run, run / "recovery_manifest.json",
            report["postprocess"]["manifest_sha256"], output)
        provenance = result["artifact_provenance"]
        self.assertEqual(provenance["MANIFEST"], "RECOVERED_ARTIFACT")
        self.assertEqual(provenance["RUN_CLOCK_END"], "NOT_RECOVERABLE")
        self.assertEqual(provenance["GUEST_TOPOLOGY_AFTER_CAPTURE"],
                         "NOT_RECOVERABLE")
        self.assertEqual(provenance["POST_CAPTURE_STATE_SNAPSHOT"],
                         "NOT_RECOVERABLE_RETROACTIVELY")
        self.assertFalse(result["restore_cancel"]["DEVICE_FDT_DISARM_PROVEN"])
        self.assertFalse(result["restore_cancel"]["RESTORE_CLOSED"])

        recovery_manifest = run / "recovery_manifest.json"
        tampered = json.loads(recovery_manifest.read_text(encoding="utf-8"))
        tampered["created_by"] = "UNTRUSTED_RECOVERY"
        recovery_manifest.write_text(json.dumps(tampered), encoding="utf-8")
        with self.assertRaisesRegex(D255.EvidenceError,
                                    "invalid recovery manifest provenance"):
            D255.analyze(run, recovery_manifest, D255.sha256_file(recovery_manifest),
                         root / "tampered-recovery-output")

    def test_powershell_pin_required_without_pin_fails_before_authorization(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        pin_gate = source.index('$WindowsHelloPinState -ceq "NOT_CONFIGURED"')
        authorization_gate = source.index('if ($Authorization -cne $ExpectedAuthorization)')
        self.assertLess(pin_gate, authorization_gate)
        self.assertIn('$FingerprintSetupPinRequirement -ceq "REQUIRED"', source)
        self.assertIn("PIN creation/change is forbidden", source)
        self.assertNotRegex(source, r"(?i)Set-ItemProperty|New-ItemProperty|reg\.exe|net user")

    def test_powershell_postattach_ui_gate_is_structured_and_single_shot(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        gate_function = source[source.index("function Read-HelloSetupUiResult"):
                               source.index("function Get-TargetDevices")]
        self.assertIn("PromptForChoice", gate_function)
        self.assertNotIn("Read-Host", gate_function)
        for result in ("READY_WAITING_FOR_FINGER", "UI_UNAVAILABLE",
                       "NEW_PIN_REQUIRED", "UNEXPECTED_PREREQUISITE"):
            self.assertIn(result, gate_function)
        self.assertEqual(source.count("$helloUiResult = Read-HelloSetupUiResult"), 1)
        ui_gate = source.index('$helloUiResult = Read-HelloSetupUiResult')
        self.assertLess(source.index('Write-OperatorMarker -Event "PASSIVE_BOOTSTRAP_SETTLED"'),
                        ui_gate)
        self.assertLess(ui_gate, source.index('Write-OperatorMarker -Event "OEM_SESSION_BEGIN"'))

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
        interface_closed = source.index(
            '$usbPcapCandidates.Count -gt 1 -and $interfaceMatches.Count -ne')
        account_gate = source.index(
            'if ($AccountPrerequisiteConfirmation -cne $ExpectedAccountPrerequisiteConfirmation)')
        remaining_path_gates = source.index('foreach ($path in $OemLogPath)', account_gate)
        self.assertLess(interface_closed, account_gate)
        self.assertLess(account_gate, remaining_path_gates)
        self.assertLess(gate, consumed)
        self.assertLess(consumed, start_capture)

    def test_powershell_empty_collection_contract_horizontal_audit(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        targeted = source[source.index("function Get-TargetedFiles"):
                          source.index("function Resolve-OemLogCandidates")]
        file_snapshot = source[source.index("function Write-FileSnapshot"):
                               source.index("function Write-OemLogSnapshot")]
        log_snapshot = source[source.index("function Write-OemLogSnapshot"):
                              source.index("function Invoke-D255PreAuthorizationEvidenceSetup")]
        shared_setup = source[source.index("function Invoke-D255PreAuthorizationEvidenceSetup"):
                              source.index("function Invoke-D255PreAuthorizationSimulation")]
        self.assertIn("[AllowEmptyCollection()][string[]]$Roots = @()", targeted)
        self.assertIn(
            "[Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Roots",
            file_snapshot)
        self.assertIn(
            "[Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]$Candidates",
            log_snapshot)
        for parameter in ("$OemLogCandidates", "$CacheRoots", "$CaptureInterfaces"):
            self.assertRegex(
                shared_setup,
                re.escape("[Parameter(Mandatory = $true)][AllowEmptyCollection()][string[]]")
                + re.escape(parameter))
        self.assertIn('if ($CaptureInterfaces.Count -eq 0)', shared_setup)
        self.assertIn("pre-authorization setup requires at least one capture interface",
                      shared_setup)
        self.assertIn('if ($CaptureInterface.Count -eq 0)', source)
        self.assertIn('if ($usbPcapCandidates.Count -eq 0)', source)

    def test_powershell_preauthorization_simulation_reuses_live_setup(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        shared_setup = source[source.index("function Invoke-D255PreAuthorizationEvidenceSetup"):
                              source.index("function Invoke-D255PreAuthorizationSimulation")]
        simulation = source[source.index("function Invoke-D255PreAuthorizationSimulation"):
                            source.index("function Write-Manifest")]
        authorization_gate = source.index('if ($Authorization -cne $ExpectedAuthorization)')
        live_setup = source[source.index("# Pre-hardware setup:"):authorization_gate]
        for token in (
                'Write-OemLogSnapshot -Stage "before"',
                'Write-FileSnapshot -Stage "before"',
                '$Preflight["runtime"] = Get-D255RuntimeInfo',
                'capture_arguments ='):
            self.assertIn(token, shared_setup)
        self.assertNotIn("Start-Process", shared_setup)
        self.assertIn("$setup = Invoke-D255PreAuthorizationEvidenceSetup", simulation)
        self.assertIn("$preAuthorizationSetup = Invoke-D255PreAuthorizationEvidenceSetup",
                      live_setup)
        self.assertIn("-OemLogCandidates $oemLogCandidates", simulation)
        self.assertIn("-OemLogCandidates $oemLogCandidates", live_setup)
        for token in (
                "EMPTY_OEM_LOG_CANDIDATES_BINDING=PASS",
                "AUTHORIZATION_CONSUMED=false",
                "REAL_CAPTURE_STARTED=false",
                "REAL_USB_OPEN_COUNT=0",
                "REAL_HARDWARE_ACTION_COUNT=0",
                "EMPTY_CACHE_ROOTS_BINDING=PASS"):
            self.assertIn(token, simulation)
        self.assertNotIn("Start-Process", simulation)
        self.assertNotIn("Get-PnpDevice", simulation)
        self.assertLess(source.index("$preAuthorizationSetup = ",
                                     source.index("# Pre-hardware setup:")),
                        authorization_gate)

    def test_powershell_preauthorization_simulation_has_present_log_case(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        simulation = source[source.index("function Invoke-D255PreAuthorizationSimulation"):
                            source.index("function Write-Manifest")]
        self.assertIn('[ValidateSet("ABSENT", "PRESENT")]', source)
        self.assertIn('$SimulationOemLogState -ceq "PRESENT"', simulation)
        self.assertIn("goodix-synthetic.log", simulation)
        self.assertIn("PRESENT_OEM_LOG_SNAPSHOT=PASS", simulation)
        self.assertIn('oem_logs_before\\oem_000.log', simulation)
        self.assertIn("authorization must not be supplied", simulation)
        self.assertIn("TsharkPath must not be supplied", simulation)

    def test_powershell_preflight_accepts_zero_oem_logs_and_reports_sources(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        oem_resolution = source.index("$oemLogCandidates = @(Resolve-OemLogCandidates)")
        preflight = source.index("$preflight = [ordered]@{", oem_resolution)
        segment = source[oem_resolution:preflight]
        self.assertNotIn("$oemLogCandidates.Count -eq 0", segment)
        self.assertNotIn("no readable OEM/WBDI log source was identified", source)
        authorization_gate = source.index('if ($Authorization -cne $ExpectedAuthorization)')
        for failure in ("configured OEM log is unreadable",
                        "configured cache root is unreadable"):
            self.assertIn(failure, source)
            self.assertLess(source.index(failure), authorization_gate)
        self.assertIn("$cacheCandidates = @(Get-TargetedFiles -Roots $cacheRoots)", segment)
        cache_discovery = source[source.index("function Get-TargetedFiles"):
                                 source.index("function Resolve-OemLogCandidates")]
        self.assertIn('$_.Extension -notmatch "(?i)^\\.log$"', cache_discovery)
        for token in (
                "oem_log_status = $oemLogStatus",
                "goodix_cache_status = $cacheStatus",
                'Write-Output "OEM_LOG_STATUS=$oemLogStatus"',
                'Write-Output "GOODIX_CACHE_STATUS=$cacheStatus"',
                'Write-Output "D255_HARDWARE_ACTION_COUNT=0"',
                'Write-Output "D255_AUTHORIZATION_CONSUMED=false"'):
            self.assertIn(token, source)
        self.assertIn('Get-D255AvailabilityStatus -SourceCount 0', source)
        self.assertIn('Get-D255AvailabilityStatus -SourceCount 1', source)
        self.assertGreaterEqual(source.count("Write-D255JsonArray -Rows @($rows)"), 2)
        json_array = source[source.index("function Write-D255JsonArray"):
                            source.index("function Get-D255RuntimeInfo")]
        self.assertIn("[AllowEmptyCollection()][object[]]$Rows", json_array)
        self.assertIn('if ($Rows.Count -eq 0)', json_array)
        self.assertIn('Set-Content -LiteralPath $Path -Encoding UTF8 -Value "[]"',
                      json_array)

    def test_usbpcap_single_interface_is_unambiguous(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn('if ($usbPcapCandidates.Count -eq 1) { "UNAMBIGUOUS" }', source)
        self.assertIn('$usbPcapCandidates = @($interfaceLines | Where-Object', source)

    def test_usbpcap_multi_interface_requires_capture_all(self):
        source = POWERSHELL_PATH.read_text(encoding="utf-8")
        self.assertIn('[string[]]$CaptureInterface = @()', source)
        self.assertIn('$interfaceMatches.Count -ne $usbPcapCandidates.Count', source)
        self.assertIn('"CAPTURE_ALL"', source)
        self.assertIn('$captureSelectors = @($CaptureInterfaces | ForEach-Object', source)

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
