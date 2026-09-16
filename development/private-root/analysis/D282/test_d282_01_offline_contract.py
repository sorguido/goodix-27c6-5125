#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from analysis.D282 import d282_01_grant_ordering_model as grant_ordering
from analysis.D282 import d282_01_staging_probe_evidence_audit as probe_evidence


ROOT = Path(__file__).resolve().parents[2]
FPRINTD = ROOT / "reference/fprintd-fedora44-1.94.5/source/src/device.c"
VERIFY_UTILITY = ROOT / "reference/fprintd-fedora44-1.94.5/source/utils/verify.c"
FPRINTD_SPEC = ROOT / "reference/fprintd-fedora44-1.94.5/fprintd.spec"
CORE = ROOT / "reference/libfprint-fedora44-1.94.100/source/libfprint"
ROCKY_CORE = ROOT / "Rockytkg/libfprint/libfprint"
DRIVER = ROOT / "libfprint-driver/goodix_fpimage_device.c"
PRODUCTION_TEST = ROOT / "libfprint-driver/tests/test_goodix_d278_secure_session.c"
FEDORA_ACTION_TEST = ROOT / "libfprint-driver/tests/test_goodix_fedora44_nbis_action.c"
KIT = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
README = ROOT / "operator_kit/d282-01-fprintd-target/README_IT.md"
BUILD = ROOT / "operator_kit/d282-01-fprintd-target/build-inner.sh"
PROBE_BUILD = ROOT / "operator_kit/d282-01-fprintd-target/build-staging-probe-inner.sh"
ATTEMPT_ENV = ROOT / "analysis/D282/D282_01_ATTEMPT_01_NORMALIZED.env"
ATTEMPT_REPORT = ROOT / "analysis/D282/D282_01_attempt_01_host_staging_failure.md"
OFFLINE_RESULT = ROOT / "analysis/D282/D282_01_OFFLINE_RESULT.env"
PROBE_AUDIT_RESULT = ROOT / "analysis/D282/D282_01_STAGING_PROBE_AUDIT.json"
ATTEMPT_02_ENV = ROOT / "analysis/D282/D282_01_ATTEMPT_02_NORMALIZED.env"
ATTEMPT_02_REPORT = ROOT / "analysis/D282/D282_01_attempt_02_post_live_analysis.md"
ATTEMPT_02_CAPTURE = (
    ROOT / "captures/D282_01/D28201_ATTEMPT_02_cc2452e5/sanitized")
ATTEMPT_03_ENV = ROOT / "analysis/D282/D282_01_ATTEMPT_03_NORMALIZED.env"
ATTEMPT_03_REPORT = ROOT / "analysis/D282/D282_01_attempt_03_post_live_analysis.md"
ATTEMPT_03_AUDITOR = ROOT / "analysis/D282/d282_01_attempt_03_evidence_audit.py"
ATTEMPT_03_CAPTURE = (
    ROOT / "captures/D282_01/D28201_ATTEMPT_03_42903b70/sanitized")
ATTEMPT_04_05_AUDITOR = (
    ROOT / "analysis/D282/d282_01_attempt_04_05_evidence_audit.py")

spec = importlib.util.spec_from_file_location(
    "d282_staging", ROOT / "analysis/D282/d282_01_staging_model.py")
staging = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(staging)


def function_slice(text: str, name: str, next_name: str) -> str:
    start = text.index(name)
    end = text.index(next_name, start + len(name))
    return text[start:end]


class D282OfflineContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fprintd = FPRINTD.read_text()
        cls.verify_utility = VERIFY_UTILITY.read_text()
        cls.core = (CORE / "fpi-image-device.c").read_text()
        cls.public_core = (CORE / "fp-image-device.c").read_text()
        cls.rocky_core = (ROCKY_CORE / "fpi-image-device.c").read_text()
        cls.rocky_core_header = (ROCKY_CORE / "fpi-image-device.h").read_text()
        cls.driver = DRIVER.read_text()
        cls.production_test = PRODUCTION_TEST.read_text()
        cls.fedora_action_test = FEDORA_ACTION_TEST.read_text()
        cls.kit = KIT.read_text()
        cls.readme = README.read_text()
        cls.build = BUILD.read_text()
        cls.probe_build = PROBE_BUILD.read_text()
        cls.attempt_env = ATTEMPT_ENV.read_text()
        cls.attempt_report = ATTEMPT_REPORT.read_text()
        cls.offline_result = OFFLINE_RESULT.read_text()
        cls.attempt_02_env = ATTEMPT_02_ENV.read_text()
        cls.attempt_02_report = ATTEMPT_02_REPORT.read_text()
        cls.attempt_03_env = ATTEMPT_03_ENV.read_text()
        cls.attempt_03_report = ATTEMPT_03_REPORT.read_text()

    def test_01_exact_fprintd_one_print_dispatches_verify(self):
        verify_start = function_slice(
            self.fprintd, "fprint_device_verify_start (", "verify_stop_wait_timeout (")
        one = verify_start.index("gallery->len == 1")
        select = verify_start.index("finger = fp_print_get_finger", one)
        identify = verify_start.index("finger == FP_FINGER_UNKNOWN", select)
        verify = verify_start.index("fp_device_verify (", identify)
        self.assertLess(one, select)
        self.assertLess(select, identify)
        self.assertLess(identify, verify)
        self.assertRegex(FPRINTD_SPEC.read_text(), r"(?m)^Version:\s*1\.94\.5$")

    def test_02_goodix_verify_is_single_acquisition(self):
        self.assertIn("action == FPI_DEVICE_ACTION_VERIFY", self.driver)
        self.assertIn("GOODIX_POST_TLS_CAPTURE_PROFILE_SINGLE_ACQUISITION",
                      self.driver)
        self.assertIn("D282/01: fprintd selects VERIFY", self.production_test)

    def test_03_sigfm_verify_same_template_match(self):
        self.assertIn("fpi_device_get_verify_data", self.core)
        self.assertIn("fpi_print_sigfm_match", self.core)
        self.assertIn("g_assert_true (fixture->verify_match)", self.production_test)

    def test_04_sigfm_verify_different_template_no_match(self):
        self.assertIn("g_assert_false (fixture->verify_match)", self.production_test)
        self.assertIn("verify_no_match_callback_count, ==, 1u", self.production_test)
        self.assertIn("fill_distinct_structured_sigfm_samples",
                      self.fedora_action_test)
        self.assertIn("SIGFM_DISTINCT_TEMPLATE_NO_MATCH=PASS_SYNTHETIC",
                      self.fedora_action_test)
        self.assertIn(
            "DIFFERENT_FINGER_NO_MATCH=PASS_LIVE_OPERATOR_ATTESTED_STIMULUS",
            self.readme)

    def test_05_identify_regression_remains(self):
        self.assertIn("FPI_DEVICE_ACTION_IDENTIFY", self.core)
        self.assertIn("fp_device_identify (", self.production_test)

    def test_06_enrollment_regression_remains(self):
        self.assertIn("FPI_DEVICE_ACTION_ENROLL", self.core)
        self.assertIn("GOODIX_SIGFM_ENROLL_MAX_STAGES", self.production_test)

    def test_07_retry_extraction_has_no_second_sensor_action(self):
        self.assertIn("goodix_test_sigfm_extract_set_failure (TRUE)",
                      self.production_test)
        self.assertIn("production_action_attempt_count, ==, 1u",
                      self.production_test)
        self.assertIn("production_rejected_action_count, ==, 0u",
                      self.production_test)
        self.assertIn("production_explicit_verify_reopen_count, ==, 1u",
                      self.production_test)

    def test_08_fprintd_retry_does_not_open_or_start_usb_itself(self):
        retry = function_slice(self.fprintd, "verify_cb (", "identify_cb (")
        self.assertIn("error->domain == FP_DEVICE_RETRY", retry)
        self.assertEqual(retry.count("fp_device_verify ("), 1)
        self.assertNotIn("fp_device_open", retry)
        self.assertNotIn("fp_device_close", retry)
        self.assertIn("SECOND_SENSOR_REACHING_ACTION_COUNT=0", self.readme)

    def test_09_malformed_fp3_fails_closed(self):
        self.assertIn("CORRUPT_FP3_REJECTED", self.kit)
        self.assertIn("fp_print_deserialize", self.build)

    def test_10_missing_fp3_fails_closed(self):
        self.assertIn("MISSING_FP3_REJECTED", self.kit)

    def test_11_wrong_user_and_finger_lookup_precedes_verify(self):
        verify_start = function_slice(
            self.fprintd, "fprint_device_verify_start (", "verify_stop_wait_timeout (")
        self.assertLess(verify_start.index("store.print_data_load"),
                        verify_start.index("fp_device_verify ("))
        self.assertLess(self.verify_utility.index("find_finger (dev, username)"),
                        self.verify_utility.index("match = do_verify (dev)"))
        self.assertIn("Finger '%s' not enrolled for user %s.",
                      self.verify_utility)
        self.assertIn("WRONG_USER_FINGER_REJECTED", self.kit)

    def test_12_close_open_restart_contract(self):
        self.assertIn("systemctl restart fprintd.service", self.kit)
        self.assertIn("DAEMON_RESTART_COUNT=1", self.kit)

    def test_13_verify_cancellation_is_wired(self):
        self.assertIn("action == FPI_DEVICE_ACTION_VERIFY", self.public_core)
        self.assertIn("D282/01 VERIFY cancellation", self.production_test)
        self.assertIn("g_cancellable_cancel (verify_cancellable)",
                      self.production_test)

    def test_14_daemon_restart_and_maps_verification(self):
        self.assertIn("/proc/$daemon_pid/maps", self.kit)
        self.assertIn("EXACT_LIBRARY_MAP_VERIFIED=true", self.kit)

    def test_15_cleanup_is_owned_and_bounded(self):
        self.assertIn(".goodix-d282-01-", self.kit)
        self.assertNotIn("rm -rf /var/lib/fprint", self.kit)
        self.assertIn("TEMPLATE_INCLUDED_IN_EXPORT=false", self.kit)
        self.assertIn("${result_prefix}_RESULT=FAIL_ROLLBACK", self.kit)
        self.assertIn("local exit_status=$?", self.kit)
        self.assertIn("live_run_return_code=$exit_status", self.kit)

    def test_16_staging_rollback(self):
        self._exercise_staging(None)

    def test_17_staging_rollback_after_each_intermediate_failure(self):
        for point in ("runtime", "dropin", "storage"):
            self._exercise_staging(point)

    def test_18_preexisting_storage_is_byte_preserved(self):
        self._exercise_staging(None, seed=True)
        self.assertIn('PREEXISTING_STORAGE_UNCHANGED=$storage_rollback',
                      self.kit)

    def test_19_no_hidden_retry_reopen_reset_or_clear_halt(self):
        for forbidden in ("g_usb_device_reset (", "g_usb_device_clear_halt ("):
            self.assertNotIn(forbidden, self.driver)
        self.assertIn("BIOMETRIC_ACTION_MAX=3", self.kit)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=10", self.kit)
        self.assertIn("RETRY_AUTHORIZED=false", self.kit)

    def test_20_no_persistent_family_outside_empty_allowlist(self):
        self.assertIn('KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=$persistent_count',
                      self.kit)
        self.assertIn("persistent=0", self.kit)
        self.assertIn("PAM_IN_SCOPE=false", self.kit)

    def test_21_all_pre_live_gates_precede_staging_without_credentials(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        refusal = function_slice(self.kit, "refuse ()", "is_sha ()")
        staging = live.index("live_staging_started=true")
        for anchor in (
                "refuse STAGING_COLLISION",
                "refuse FPRINTD_INITIAL_STATE_UNSAFE",
                "refuse SYSTEM_LIBFPRINT_MISSING",
                'validate_selinux_preconditions "$live_system_library" "$live_storage_root"',
                "refuse UNIT_SNAPSHOT_FAILED",
                "refuse STORAGE_INVENTORY_FAILED",
                "refuse TARGET_CARDINALITY_NOT_ONE"):
            self.assertLess(live.index(anchor), staging, anchor)
        self.assertLess(live.index("trap cleanup_live EXIT"), staging)
        self.assertLess(staging,
                        live.index('install -d -m 0700 "$live_runtime"'))
        after_staging = live[staging:]
        self.assertNotIn("command -v", after_staging)
        self.assertNotIn("$(getenforce)", after_staging)
        self.assertIn("validated_selinux_enforcement == Enforcing", after_staging)
        self.assertNotIn("validate_grant", live)
        self.assertNotIn("consume_validated_grant", live)
        for marker in ('AUTHORIZATION_CREDENTIAL_REQUIRED=false',
                       'REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted',
                       'LIVE_EXECUTION_PERFORMED=$live_execution_performed'):
            self.assertIn(marker, refusal)

    def test_22_staging_collision_precedes_staging(self):
        self._assert_preconsumption_refusal("STAGING_COLLISION")

    def test_23_unsafe_fprintd_state_precedes_staging(self):
        self._assert_preconsumption_refusal("FPRINTD_INITIAL_STATE_UNSAFE")

    def test_24_missing_system_libfprint_precedes_staging(self):
        self._assert_preconsumption_refusal("SYSTEM_LIBFPRINT_MISSING")

    def test_25_unit_snapshot_failure_precedes_staging(self):
        self._assert_preconsumption_refusal("UNIT_SNAPSHOT_FAILED")

    def test_26_storage_inventory_failure_precedes_staging(self):
        self._assert_preconsumption_refusal("STORAGE_INVENTORY_FAILED")

    def test_27_selinux_precondition_failure_precedes_staging(self):
        self._assert_preconsumption_refusal(
            "SELINUX_PRECONDITION_FAILED",
            source_anchor='validate_selinux_preconditions "$live_system_library" "$live_storage_root"')
        for refusal in ("SELINUX_STATE_UNREADABLE", "SELINUX_CHCON_MISSING",
                        "SELINUX_RESTORECON_MISSING", "SELINUX_REFERENCE_UNLABELED"):
            self.assertIn(refusal, self.kit)

    def test_28_invalid_grants_are_refused_before_consumption(self):
        validate = function_slice(self.kit, "validate_grant ()", "prepare_grant_claim ()")
        for reason in ("GRANT_FORMAT", "GRANT_BASELINE", "GRANT_OPERATION",
                       "GRANT_ID", "GRANT_USER", "GRANT_USER_UNKNOWN"):
            with self.subTest(reason=reason):
                self.assertIn(reason, validate)
                outcome = grant_ordering.simulate(
                    grant_ordering.GrantRegistry(), "grant-1",
                    invalid_grant_reason=reason)
                self._assert_unused(outcome)

    def test_29_atomic_one_shot_claim_blocks_reuse(self):
        consume = function_slice(
            self.kit, "consume_validated_grant ()", "validate_live_tooling ()")
        self.assertLess(consume.index('mkdir -m 0700 "$grant_claim"'),
                        consume.index("grant_consumed=true"))
        self.assertIn("refuse GRANT_ALREADY_CONSUMED", self.kit)
        registry = grant_ordering.GrantRegistry()
        first = grant_ordering.simulate(registry, "grant-1")
        second = grant_ordering.simulate(registry, "grant-1")
        self.assertTrue(first.grant_consumed)
        self.assertEqual(second.refusal, "GRANT_ALREADY_CONSUMED")
        self._assert_unused(second)
        self.assertEqual(registry.consumed_ids, {"grant-1"})

    def test_30_poststaging_failure_rolls_back_without_retry_and_flow_is_unchanged(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        staging = live.index("live_staging_started=true")
        self.assertLess(live.index("trap cleanup_live EXIT"), staging)
        self.assertLess(staging, live.index('install -d -m 0700 "$live_runtime"'))
        self.assertIn('echo AUTHORIZATION_CREDENTIAL_REQUIRED=false', cleanup)
        self.assertIn('echo AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false', cleanup)
        self.assertNotIn("consume_validated_grant", live)

        sequence = (
            "fprintd-enroll -f right-index-finger",
            "systemctl restart fprintd.service",
            'fprintd-verify "$user"',
            "PHASE_B=Verify dito diverso",
            'fprintd-delete "$user"',
        )
        positions = [live.index(item) for item in sequence]
        self.assertEqual(positions, sorted(positions))

    def test_31_missing_target_is_counted_before_consumption(self):
        self.assertEqual(self._count_synthetic_targets([]), 0)

    def test_32_multiple_targets_are_counted_before_consumption(self):
        self.assertEqual(self._count_synthetic_targets([
            ("1-1", "27c6", "5125"),
            ("2-1", "27c6", "5125"),
            ("3-1", "1234", "5678"),
        ]), 2)

    def test_33_exactly_one_target_passes_cardinality_count(self):
        self.assertEqual(self._count_synthetic_targets([
            ("1-1", "27c6", "5125"),
            ("2-1", "27c6", "0001"),
        ]), 1)

    def test_34_target_cardinality_gate_precedes_staging(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        count = live.index(
            "target_preconsumption_match_count=$(count_goodix_targets")
        gate = live.index("refuse TARGET_CARDINALITY_NOT_ONE", count)
        staging = live.index("live_staging_started=true")
        self.assertLess(count, gate)
        self.assertLess(gate, staging)
        self.assertIn(
            'TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count',
            function_slice(self.kit, "refuse ()", "is_sha ()"))
        self._assert_preconsumption_refusal("TARGET_CARDINALITY_NOT_ONE")

    def test_35_post_start_cardinality_check_remains_as_anti_toctou(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        start = live.index("systemctl start fprintd.service")
        post_count = live.index(
            "target_count=$(count_goodix_targets /sys/bus/usb/devices)", start)
        post_gate = live.index("refuse TARGET_CARDINALITY_NOT_ONE", post_count)
        self.assertLess(start, post_count)
        self.assertLess(post_count, post_gate)
        self.assertEqual(live.count("count_goodix_targets /sys/bus/usb/devices"), 2)

    def test_36_goodix_production_enrollment_processing_failure_is_terminal(self):
        usb_class = function_slice(
            self.driver, "goodix_usb_fpimage_device_class_init (",
            "goodix_usb_fpimage_device_init (")
        base_class = function_slice(
            self.driver, "goodix_fpimage_device_class_init (",
            "goodix_fpimage_device_init (")
        self.assertIn("enroll_processing_fail_closed", self.rocky_core_header)
        self.assertIn("img_class->enroll_processing_fail_closed = TRUE",
                      usb_class)
        self.assertNotIn("enroll_processing_fail_closed", base_class)
        self.assertIn("action == FPI_DEVICE_ACTION_ENROLL", self.rocky_core)
        self.assertIn("cls->enroll_processing_fail_closed", self.rocky_core)
        self.assertIn("FP_DEVICE_ERROR_DATA_INVALID", self.rocky_core)
        self.assertIn("cls->enroll_processing_fail_closed", self.core)
        self.assertIn("FP_DEVICE_ERROR_DATA_INVALID", self.core)
        self.assertIn("cls->enroll_processing_fail_closed", self.build)
        self.assertIn(
            "production-enrollment-intermediate-extraction-terminal",
            self.production_test)
        for marker in (
                "enroll_retry_callback_count, ==, 0u",
                "await_finger_on_count_at_failure",
                "goodix_fpi_usb_backend_is_drained",
                "audit.usb_real_submit_count, ==, 0u"):
            self.assertIn(marker, self.production_test)

    def test_37_launcher_rejects_enrollment_retry_markers(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        enroll = live.index("fprintd-enroll -f right-index-finger")
        marker = live.index("grep -c 'enroll-retry-'", enroll)
        refusal = live.index("refuse ENROLLMENT_RETRY_MARKER_OBSERVED", marker)
        restart = live.index("systemctl restart fprintd.service", refusal)
        self.assertLess(enroll, marker)
        self.assertLess(marker, refusal)
        self.assertLess(refusal, restart)
        for marker in (
                "ENROLLMENT_RETRY_CALLBACK_COUNT=$enroll_retry_count",
                "EXTRA_ENROLLMENT_CONTACT_REQUESTED=false",
                "EXTRA_ENROLLMENT_REARM_COUNT=0"):
            self.assertIn(marker, live)

    def test_38_exit_trap_survives_function_scope_in_real_bash_process(self):
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        run = function_slice(self.kit, "run_live ()", "operator_run ()")
        self.assertLess(self.kit.index("cleanup_live ()"),
                        self.kit.index("run_live ()"))
        self.assertNotIn("cleanup_live ()", run)
        for state_name in (
                "live_result", "live_private", "live_runtime", "live_owned",
                "live_storage_root", "live_dropin", "live_service_before",
                "live_staging_started", "live_service_touched",
                "live_cleanup_armed", "live_run_return_code"):
            self.assertIn(state_name, cleanup)

        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-exit-trap-test.", dir="/tmp") as td:
            root = Path(td)
            result = subprocess.run(
                [str(KIT), "--self-test-exit-trap", td],
                capture_output=True, text=True)
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 41, combined)
            self.assertIn("EXIT_TRAP_LOCAL_SCOPE_REGRESSION=PASS", combined)
            self.assertIn("UNBOUND_VARIABLE_DURING_CLEANUP=false", combined)
            self.assertNotIn("unbound variable", combined.lower())
            self.assertFalse((root / "runtime").exists())
            self.assertFalse(
                (root / "storage-root/.goodix-d282-01-test").exists())
            self.assertFalse(
                (root / "systemd/fprintd.service.d/90-goodix-d282-01.conf").exists())
            summary = (root / "result/summary.env").read_text()
            for marker in (
                    "D282_01_RESULT=FAIL_ACTION_OR_AUDIT",
                    "RUN_RETURN_CODE=41",
                    "ROLLBACK_COMPLETE=true",
                    "GRANT_CONSUMED=false",
                    "RETRY_AUTHORIZED=false"):
                self.assertIn(marker, summary)

    def test_39_direct_fprintd_dropin_is_production_shaped_and_parser_valid(self):
        helper = function_slice(
            self.kit, "write_systemd_dropin ()",
            "exit_trap_scope_regression ()")
        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-systemd-parser.", dir="/tmp") as td:
            dropin = Path(td) / "dropin.conf"
            shell = ("set -euo pipefail\n" + helper +
                     '\nwrite_systemd_dropin /run/goodix-d282-01/test '
                     '/var/lib/fprint/.goodix-d282-01-test "$1" live\n')
            generated = subprocess.run(
                ["bash", "-c", shell, "d282-dropin", str(dropin)],
                capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0,
                             generated.stdout + generated.stderr)
            text = dropin.read_text()
            self.assertIn("ExecStart=/usr/libexec/fprintd", text)
            self.assertNotIn("launch-fprintd", text)
            self.assertIn(
                'Environment="LD_LIBRARY_PATH=/run/goodix-d282-01/test"', text)
            self.assertIn(
                'Environment="FP_DRIVERS_ALLOWLIST=goodix_27c6_5125"', text)
            self.assertIn("StateDirectory=fprint/.goodix-d282-01-test", text)
            unit = Path(td) / "d282-parser-test.service"
            unit.write_text(
                "[Unit]\nDescription=D282 parser test\n"
                "[Service]\nType=simple\nExecStart=/usr/bin/false\n" + text)
            verified = subprocess.run(
                ["systemd-analyze", "verify", str(unit)],
                capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0,
                             verified.stdout + verified.stderr)

        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        self.assertIn(
            'grep -F "$live_runtime/libfprint-2.so.2.0.0" "/proc/$daemon_pid/maps"',
            live)
        self.assertIn(
            'readlink -f "/proc/$daemon_pid/exe") == /usr/libexec/fprintd', live)

    def test_40_attempt_01_is_normalized_without_biometric_claims(self):
        for marker in (
                "D282_01_LIVE_ATTEMPT_01=FAIL_HOST_STAGING",
                "D282_01_ATTEMPT_01_GRANT_CONSUMED=true",
                "D282_01_ATTEMPT_01_RETRY_AUTHORIZED=false",
                "D282_01_ATTEMPT_01_ENROLLMENT_STARTED=false",
                "D282_01_ATTEMPT_01_FINGER_CONTACT_COUNT=0",
                "D282_01_ATTEMPT_01_SENSOR_REACHING_ACTION_COUNT=0",
                "D282_01_ATTEMPT_01_ROOT_CAUSE_PRIMARY=SELINUX_WRAPPER_EXEC_DENIED",
                "D282_01_ATTEMPT_01_ROOT_CAUSE_SECONDARY=EXIT_TRAP_SCOPE_FAILURE",
                "D282_01_ATTEMPT_01_RAW_IMPORT=BLOCKED_ROOT_ONLY_NO_AUTHORIZATION"):
            self.assertIn(marker, self.attempt_env)
        self.assertIn("Nessuna proprietà biometrica", self.attempt_report)
        self.assertIn("USER_ATTESTED", self.attempt_report)

    def test_41_privileged_probe_closes_selinux_runtime_blocker(self):
        for marker in (
                "D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=VERIFIED_PRIVILEGED_HOST",
                "D282_01_SELINUX_WRAPPER_FAILURE=RESOLVED",
                "FPRINTD_SYSTEMD_STAGING_START=VERIFIED_PRIVILEGED_HOST",
                "SELINUX_EXEC_DENIAL=false",
                "D282_01_PRIVILEGED_STAGING_PROBE=ACCEPTED_CLOSED",
                "D282_01_BIOMETRIC_HUMAN_GATE_READINESS=NOT_REQUIRED_D282_CLOSED"):
            self.assertIn(marker, self.offline_result)
            self.assertIn(f"echo {marker}", self.kit)

    def test_42_privileged_probe_is_a_distinct_non_live_mode(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        self.assertIn("--run-authorized-staging-probe", self.kit)
        self.assertNotIn("run_live", probe)
        self.assertIn("staging_probe_execution_performed=true", probe)
        self.assertIn("live_execution_performed=false", probe)
        self.assertIn("real_usb_enumeration_attempted=false", probe)
        self.assertIn("real_sensor_accessed=false", probe)
        for marker in (
                "D282_01_PRIVILEGED_STAGING_PROBE=ACCEPTED_CLOSED",
                "D282_01_PRIVILEGED_STAGING_PROBE_EXECUTED=true",
                "D282_01_PRIVILEGED_STAGING_PROBE_WAS_AUTHORIZED=true",
                "D282_01_PRIVILEGED_STAGING_PROBE_CURRENTLY_AUTHORIZED=false",
                "D282_01_PRIVILEGED_STAGING_PROBE_GRANT_CONSUMED=true"):
            self.assertIn(marker, self.offline_result)

    def test_43_probe_candidate_is_virtual_only_and_usb_compiled_out(self):
        for marker in (
                "-Ddrivers=virtual_image",
                "-DD281_01_DISABLE_USB_CONTEXT",
                "fpi_device_virtual_image_get_type",
                "g_usb_context_(new|enumerate)",
                "D282_01_STAGING_PROBE_USB_CONTEXT_COMPILE_DISABLED=true",
                "D282_01_STAGING_PROBE_GOODIX_DRIVER_PRESENT=false"):
            self.assertIn(marker, self.probe_build)
        self.assertNotIn("-Ddrivers=goodix_27c6_5125", self.probe_build)

    def test_44_probe_reaudits_binary_safety_before_grant_consumption(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        audit = function_slice(
            self.kit, "audit_staging_probe_candidate ()", "abi_preflight ()")
        consume = probe.index('consume_validated_grant "$grant"')
        self.assertLess(probe.index(
            'audit_staging_probe_candidate "$candidate"'), consume)
        for marker in (
                "STAGING_PROBE_USB_NOT_DISABLED",
                "STAGING_PROBE_GOODIX_PRESENT",
                "STAGING_PROBE_USB_CONTEXT_SYMBOL_PRESENT",
                "STAGING_PROBE_GOODIX_TLS_SYMBOL_PRESENT",
                "STAGING_PROBE_GOODIX_DRIVER_PRESENT"):
            self.assertIn(marker, audit)

    def test_45_probe_grant_is_bound_to_the_exclusive_operation(self):
        exact = "D282_01_PRIVILEGED_SYSTEMD_SELINUX_STAGING_PROBE"
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        validate = function_slice(
            self.kit, "validate_grant ()", "prepare_grant_claim ()")
        self.assertIn(f"staging_probe_operation={exact}", self.kit)
        self.assertIn(
            'validate_grant "$grant" "$baseline" "$expected_id" \\\n    "$staging_probe_operation"', probe)
        self.assertNotIn("validate_grant", live)
        self.assertIn("AUTHORIZATION_CREDENTIAL_REQUIRED=false", live)
        self.assertIn('D282_01_OPERATION) == "$expected_operation"', validate)

    def test_46_probe_grant_claim_remains_atomic_and_one_shot(self):
        probe_id = "d28201-staging-probe-baseline"
        registry = grant_ordering.GrantRegistry()
        first = grant_ordering.simulate(registry, probe_id)
        second = grant_ordering.simulate(registry, probe_id)
        self.assertTrue(first.grant_consumed)
        self.assertEqual(second.refusal, "GRANT_ALREADY_CONSUMED")
        self.assertFalse(second.grant_consumed)
        consume = function_slice(
            self.kit, "consume_validated_grant ()", "validate_live_tooling ()")
        self.assertLess(consume.index('mkdir -m 0700 "$grant_claim"'),
                        consume.index("grant_consumed=true"))

    def test_47_probe_failures_before_consumption_leave_grant_unused(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        consume = probe.index('consume_validated_grant "$grant"')
        for anchor in (
                'audit_staging_probe_candidate "$candidate"',
                'validate_grant "$grant" "$baseline" "$expected_id"',
                "refuse STAGING_COLLISION",
                "refuse STAGING_PROBE_FPRINTD_INITIAL_STATE_UNSAFE",
                "refuse SYSTEM_LIBFPRINT_MISSING",
                "refuse STAGING_PROBE_SELINUX_NOT_ENFORCING",
                "refuse UNIT_SNAPSHOT_FAILED",
                "refuse STORAGE_INVENTORY_FAILED",
                'prepare_grant_claim "$expected_id"'):
            self.assertLess(probe.index(anchor), consume, anchor)
        outcome = grant_ordering.simulate(
            grant_ordering.GrantRegistry(), "probe",
            preconsumption_refusal="SELINUX_PRECONDITION_FAILED")
        self.assertFalse(outcome.grant_consumed)
        self.assertFalse(outcome.real_usb_enumeration_attempted)
        self.assertFalse(outcome.live_execution_performed)

    def test_48_probe_postconsume_failure_rolls_back_without_retry(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        consume = probe.index('consume_validated_grant "$grant"')
        self.assertLess(probe.index("trap cleanup_live EXIT"), consume)
        self.assertLess(consume, probe.index("live_staging_started=true"))
        self.assertIn('echo "RETRY_AUTHORIZED=false"', cleanup)
        outcome = grant_ordering.simulate(
            grant_ordering.GrantRegistry(), "probe",
            fail_immediately_after_consumption=True)
        self.assertTrue(outcome.grant_consumed)
        self.assertTrue(outcome.rollback_complete)
        self.assertFalse(outcome.retry_authorized)
        self.assertFalse(outcome.real_usb_enumeration_attempted)
        self.assertFalse(outcome.live_execution_performed)

    def test_49_probe_reuses_real_subprocess_verified_exit_trap(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        self.assertIn("trap cleanup_live EXIT", probe)
        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-exit-trap-test.", dir="/tmp") as td:
            result = subprocess.run(
                [str(KIT), "--self-test-exit-trap", td],
                capture_output=True, text=True)
            combined = result.stdout + result.stderr
            self.assertEqual(result.returncode, 41, combined)
            self.assertIn("EXIT_TRAP_LOCAL_SCOPE_REGRESSION=PASS", combined)
            self.assertIn("ROLLBACK_COMPLETE=true", combined)
            self.assertNotIn("unbound variable", combined.lower())

    def test_50_probe_dropin_is_direct_exec_and_systemd_parser_valid(self):
        helper = function_slice(
            self.kit, "write_systemd_dropin ()",
            "exit_trap_scope_regression ()")
        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-probe-systemd-parser.", dir="/tmp") as td:
            dropin = Path(td) / "dropin.conf"
            shell = ("set -euo pipefail\n" + helper +
                     '\nwrite_systemd_dropin /run/goodix-d282-01/probe '
                     '/var/lib/fprint/.goodix-d282-01-probe "$1" '
                     'staging-probe\n')
            generated = subprocess.run(
                ["bash", "-c", shell, "d282-probe-dropin", str(dropin)],
                capture_output=True, text=True)
            self.assertEqual(generated.returncode, 0,
                             generated.stdout + generated.stderr)
            text = dropin.read_text()
            for marker in (
                    "ExecStart=/usr/libexec/fprintd",
                    'Environment="FP_DRIVERS_ALLOWLIST=virtual_image"',
                    "UnsetEnvironment=FP_VIRTUAL_IMAGE",
                    "DeviceAllow=",
                    "DevicePolicy=closed",
                    "PrivateDevices=yes",
                    "ReadWritePaths="):
                self.assertIn(marker, text)
            self.assertNotIn(
                'Environment="FP_DRIVERS_ALLOWLIST=goodix_27c6_5125"', text)
            unit = Path(td) / "d282-probe-parser-test.service"
            unit.write_text(
                "[Unit]\nDescription=D282 probe parser test\n"
                "[Service]\nType=simple\nExecStart=/usr/bin/false\n" + text)
            verified = subprocess.run(
                ["systemd-analyze", "verify", str(unit)],
                capture_output=True, text=True)
            self.assertEqual(verified.returncode, 0,
                             verified.stdout + verified.stderr)
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        self.assertIn('LD_LIBRARY_PATH=$live_runtime', probe)
        self.assertIn("DAEMON_LIBRARY_MAP_NOT_EXACT", probe)
        self.assertIn("STAGING_PROBE_VIRTUAL_ENDPOINT_PRESENT", probe)

    def test_51_probe_storage_is_isolated_and_preserved_by_cleanup(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        self.assertIn(".goodix-d282-01-staging-probe-", probe)
        self.assertIn('d282_storage_inventory.py" "$live_storage_root"', probe)
        self.assertIn("STAGING_PROBE_STORAGE_NOT_EMPTY", probe)
        self.assertIn("DAEMON_STATE_DIRECTORY_DRIFT", probe)
        self.assertIn("EXACT_STATE_DIRECTORY_VERIFIED=true", probe)
        self.assertIn("storage.before.json", cleanup)
        self.assertIn("storage.after.json", cleanup)
        self.assertIn("PREEXISTING_STORAGE_UNCHANGED=$storage_rollback", cleanup)

    def test_52_probe_system_library_is_never_replaced_and_is_rehashed(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        self.assertIn('readlink -f /usr/lib64/libfprint-2.so.2', probe)
        self.assertIn("live_system_library_before", probe)
        self.assertIn("SYSTEM_LIBFPRINT_DRIFT", probe)
        self.assertNotIn("ldconfig", probe)
        self.assertNotIn("/usr/lib64/libfprint-2.so.2.0.0", probe)
        self.assertIn("SYSTEM_LIBFPRINT_UNCHANGED=$library_rollback", cleanup)

    def test_53_probe_has_no_biometric_pam_goodix_tls_or_psk_path(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        for forbidden in (
                "fprintd-enroll", "fprintd-verify", "fprintd-delete",
                "fprintd-list", "fp_device_identify",
                "goodix_27c6_5125", "get_tls_client_secret", "PSK",
                "pam_"):
            self.assertNotIn(forbidden, probe)
        for marker in (
                "BIOMETRIC_ACTION_COUNT=0",
                "FINGER_CONTACT_COUNT=0",
                "REAL_USB_ENUMERATION_ATTEMPTED=false",
                "REAL_SENSOR_ACCESSED=false",
                "LIVE_EXECUTION_PERFORMED=false",
                "PAM_IN_SCOPE=false"):
            self.assertIn(marker, probe)

    def test_54_probe_accepts_active_and_inactive_initial_service_state(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        accepted = (
            '[[ $live_service_before == active || '
            '$live_service_before == inactive ]]')
        self.assertIn(accepted, probe)
        self.assertNotIn("STAGING_PROBE_FPRINTD_MUST_BE_INACTIVE", probe)
        self.assertIn("STAGING_PROBE_FPRINTD_INITIAL_STATE_UNSAFE", probe)
        self.assertLess(probe.index("live_service_before=$(systemctl is-active"),
                        probe.index('consume_validated_grant "$grant"'))

    def test_55_active_probe_success_and_failure_restore_active(self):
        for action_outcome in ("success", "failure"):
            summary = self._exercise_real_cleanup("active", action_outcome)
            self.assertIn("SERVICE_INITIAL_STATE=active", summary)
            self.assertIn("SERVICE_FINAL_STATE=active", summary)
            self.assertIn("SERVICE_STATE_RESTORED=true", summary)
            self.assertIn("ROLLBACK_COMPLETE=true", summary)
            self.assertIn("RECOVERY_REQUIRED=false", summary)

    def test_56_inactive_probe_success_and_failure_restore_inactive(self):
        for action_outcome in ("success", "failure"):
            summary = self._exercise_real_cleanup("inactive", action_outcome)
            self.assertIn("SERVICE_INITIAL_STATE=inactive", summary)
            self.assertIn("SERVICE_FINAL_STATE=inactive", summary)
            self.assertIn("SERVICE_STATE_RESTORED=true", summary)
            self.assertIn("ROLLBACK_COMPLETE=true", summary)
            self.assertIn("RECOVERY_REQUIRED=false", summary)

    def test_57_probe_stops_active_service_only_after_consumption(self):
        probe = function_slice(
            self.kit, "run_authorized_staging_probe ()",
            "run_live ()")
        consume = probe.index('consume_validated_grant "$grant"')
        conditional_stop = probe.index(
            'if [[ $live_service_before == active ]]; then')
        self.assertLess(consume, conditional_stop)
        self.assertLess(conditional_stop,
                        probe.index("systemctl daemon-reload", conditional_stop))
        self.assertIn("systemctl stop fprintd.service", probe[conditional_stop:])
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        self.assertIn('service_final_state=$(systemctl is-active', cleanup)
        self.assertIn(
            '[[ $service_final_state == "$live_service_before" ]]', cleanup)
        self.assertIn('echo "RECOVERY_REQUIRED=$recovery_required"', cleanup)

    def test_58_service_restore_mismatch_fails_rollback(self):
        summary = self._exercise_real_cleanup("active", "restore-mismatch")
        self.assertIn("SERVICE_INITIAL_STATE=active", summary)
        self.assertIn("SERVICE_FINAL_STATE=inactive", summary)
        self.assertIn("SERVICE_STATE_RESTORED=false", summary)
        self.assertIn("ROLLBACK_COMPLETE=false", summary)
        self.assertIn("RECOVERY_REQUIRED=true", summary)
        self.assertIn("D282_01_RESULT=FAIL_ROLLBACK", summary)

    def test_59_authentic_staging_probe_evidence_is_hash_pinned(self):
        audit = probe_evidence.build_audit()
        self.assertEqual(audit["decision"], "ACCEPTED_CLOSED")
        self.assertEqual(
            audit["runtime"]["systemd_selinux_staging"],
            "VERIFIED_PRIVILEGED_HOST",
        )
        self.assertTrue(audit["rollback"]["complete"])
        self.assertFalse(audit["safety"]["real_usb_enumeration_attempted"])
        self.assertFalse(audit["safety"]["real_sensor_accessed"])
        self.assertEqual(audit["safety"]["biometric_action_count"], 0)
        self.assertFalse(
            audit["post_probe_inactive_dead"]["invalidates_recorded_rollback"]
        )
        committed = json.loads(PROBE_AUDIT_RESULT.read_text(encoding="utf-8"))
        self.assertEqual(committed["decision"], audit["decision"])
        self.assertEqual(
            committed["evidence"]["summary_sha256"],
            audit["evidence"]["sha256"],
        )
        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-probe-evidence.", dir="/tmp") as td:
            mutated = Path(td) / "summary.env"
            mutated.write_bytes(probe_evidence.EVIDENCE.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "evidence hash mismatch"):
                probe_evidence.build_audit(mutated)

    def _exercise_real_cleanup(self, initial_state, action_outcome):
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        with tempfile.TemporaryDirectory(
                prefix="goodix-d282-service-cleanup.", dir="/tmp") as td:
            shell = "set -u\n" + cleanup + r'''
systemctl () {
  local action=$1 state
  case $action in
    stop) printf 'inactive\n' >"$service_state_file" ;;
    start)
      if [[ $force_restore_mismatch != true ]]; then
        printf 'active\n' >"$service_state_file"
      fi
      ;;
    daemon-reload) return 0 ;;
    is-active)
      state=$(cat "$service_state_file")
      printf '%s\n' "$state"
      [[ $state == active ]]
      ;;
    *) return 1 ;;
  esac
}
work=$1
live_service_before=$2
action_outcome=$3
force_restore_mismatch=false
[[ $action_outcome != restore-mismatch ]] || force_restore_mismatch=true
service_state_file="$work/service.state"
printf '%s\n' "$live_service_before" >"$service_state_file"
live_result="$work/result"
live_private="$live_result/private"
live_runtime="$work/runtime"
live_storage_root="$work/storage"
live_owned="$live_storage_root/.goodix-d282-01-test"
live_dropin="$work/systemd/fprintd.service.d/90-goodix-d282-01.conf"
mkdir -p "$live_private" "$live_runtime" "$live_owned" "$(dirname "$live_dropin")"
printf '[Service]\n' >"$live_dropin"
printf 'D282_01_RESULT=PASS_STAGING_PROBE_PENDING_ROLLBACK\n' >"$live_result/summary.env"
live_cleanup_armed=true
live_cleanup_test_mode=true
live_service_touched=true
live_staging_started=true
live_storage_existed=true
live_before_inventory_ready=false
live_unit_before_ready=false
live_system_library_before_ready=false
live_run_return_code=0
grant_consumed=true
real_usb_enumeration_attempted=false
real_sensor_accessed=false
live_execution_performed=false
staging_probe_execution_performed=true
staging_probe_mode=true
if [[ $action_outcome == failure ]]; then
  false
  cleanup_live
else
  true
  cleanup_live
fi
cat "$live_result/summary.env"
'''
            result = subprocess.run(
                ["bash", "-c", shell, "d282-service-cleanup", td,
                 initial_state, action_outcome],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            return result.stdout

    def test_60_attempt_02_exact_fprintd_identify_then_enroll_root_cause(self):
        enroll_start = function_slice(
            self.fprintd, "fprint_device_enroll_start (", "fprint_device_enroll_stop (")
        identify_cb = function_slice(
            self.fprintd, "enroll_identify_cb (", "is_first_enrollment (")
        feature_gate = enroll_start.index("FP_DEVICE_FEATURE_IDENTIFY")
        identify = enroll_start.index("fp_device_identify (", feature_gate)
        direct = enroll_start.index("enroll_start (rdev);", identify)
        self.assertLess(feature_gate, identify)
        self.assertLess(identify, direct)
        stage = identify_cb.index('"enroll-stage-passed"')
        enroll = identify_cb.index("enroll_start (rdev);", stage)
        self.assertLess(stage, enroll)
        self.assertIn("production_action_consumed", self.driver)
        self.assertIn("already consumed; close/reopen required", self.driver)
        self.assertIn(
            "FPRINTD_DUPLICATE_IDENTIFY_THEN_ENROLL_COLLIDES_WITH_GOODIX_ONE_ACTION_PER_OPEN_EPOCH_FENCE",
            self.attempt_02_report)

    def test_61_d282_build_only_direct_enroll_profile_preserves_verify(self):
        usb_class = function_slice(
            self.driver, "goodix_usb_fpimage_device_class_init (",
            "goodix_usb_fpimage_device_init (")
        self.assertIn("#ifdef GOODIX_D282_DIRECT_ENROLL_PROFILE", usb_class)
        self.assertIn("~((guint) FP_DEVICE_FEATURE_IDENTIFY)", usb_class)
        self.assertNotIn("FP_DEVICE_FEATURE_VERIFY", usb_class.split(
            "#ifdef GOODIX_D282_DIRECT_ENROLL_PROFILE", 1)[1].split(
                "#endif", 1)[0])
        self.assertIn("-DGOODIX_D282_DIRECT_ENROLL_PROFILE", self.build)
        self.assertIn("D282_01_IDENTIFY_FEATURE_ADVERTISED=false", self.build)
        self.assertIn("D282_01_VERIFY_FEATURE_ADVERTISED=true", self.build)

    def test_62_enrollment_failure_evidence_is_captured_before_return(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        capture = live.index("capture_enroll_failure_evidence")
        failure_return = live.index("return 1", capture)
        restart = live.index("systemctl restart fprintd.service", failure_return)
        self.assertLess(capture, failure_return)
        self.assertLess(failure_return, restart)
        helper = function_slice(
            self.kit, "capture_enroll_failure_evidence ()", "run_live ()")
        for marker in (
                "FPRINTD_ENROLL_RETURN_CODE",
                "FPRINTD_ENROLL_STAGE_PASSED_COUNT",
                "FPRINTD_ENROLL_UNKNOWN_ERROR_COUNT",
                "GOODIX_D282_EPOCH_AUDIT_LINE_COUNT",
                "D282_01_FAILURE_EVIDENCE_CAPTURED_BEFORE_ROLLBACK"):
            self.assertIn(marker, helper)

        with tempfile.TemporaryDirectory() as td:
            shell = r'''set -eu
journalctl () {
  if [[ ${1:-} == -u ]]; then
    printf '%s\n' \
      'GOODIX_D282_EPOCH_AUDIT action=FPI_DEVICE_ACTION_IDENTIFY attempts=1 rejected=0' \
      'Device reported an error during enroll: already consumed'
  else
    printf '%s\n' \
      'avc: denied { read } comm="fprintd" scontext=system_u:system_r:fprintd_t:s0 name="nr_hugepages"' \
      'avc: denied { read } comm="unrelated" name="private"'
  fi
}
''' + helper + r'''
work=$1
live_private="$work/private"
live_result="$work/result"
mkdir -p "$live_private" "$live_result"
raw="$work/enroll.raw"
printf '%s\n' \
  'Enroll result: enroll-stage-passed' \
  'Enroll result: enroll-unknown-error' >"$raw"
capture_enroll_failure_evidence \
  "$raw" '2026-09-10 00:00:00' alice deadbeef runstamp 1
cat "$live_result/summary.env"
printf '%s\n' D282_TEST_OPERATOR_LOG
cat "$live_result/operator.log"
'''
            result = subprocess.run(
                ["bash", "-c", shell, "d282-failure-capture", td],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0,
                             result.stdout + result.stderr)
            self.assertIn("FPRINTD_ENROLL_RETURN_CODE=1", result.stdout)
            self.assertIn("FPRINTD_ENROLL_STAGE_PASSED_COUNT=1", result.stdout)
            self.assertIn("FPRINTD_ENROLL_UNKNOWN_ERROR_COUNT=1", result.stdout)
            self.assertIn("GOODIX_D282_EPOCH_AUDIT_LINE_COUNT=1", result.stdout)
            self.assertIn('comm="fprintd"', result.stdout)
            self.assertNotIn('comm="unrelated"', result.stdout)

    def test_63_attempt_02_sanitized_import_is_hash_pinned_and_bounded(self):
        expected = {
            "operator.log": "c6d680671af7bf6bb5b994980d5cd3f0131d7a3555caee4db301608e7ce4aa25",
            "summary.env": "e6b41990bbfe82e2bb8bae70cd504f37e76a4957e91a133cb6204c369e1cca4e",
        }
        import hashlib
        for name, digest in expected.items():
            self.assertEqual(
                hashlib.sha256((ATTEMPT_02_CAPTURE / name).read_bytes()).hexdigest(),
                digest)
        self.assertIn("D282_01_ATTEMPT_02_GRANT_CONSUMED=true",
                      self.attempt_02_env)
        self.assertIn("D282_01_ATTEMPT_02_RETRY_AUTHORIZED=false",
                      self.attempt_02_env)
        self.assertIn("D282_01_ATTEMPT_02_EXACT_EPOCH_AUDIT=UNOBSERVED_EXPORT_GAP",
                      self.attempt_02_env)

    def test_64_attempt_03_evidence_is_hash_pinned_and_classified(self):
        result = subprocess.run(
            [sys.executable, str(ATTEMPT_03_AUDITOR)],
            check=True, capture_output=True, text=True)
        audited = json.loads(result.stdout)
        self.assertEqual(audited["outcome"], "PASS_EVIDENCE_CLASSIFICATION")
        self.assertEqual(audited["phase_a_epoch_count"], 2)
        self.assertEqual(audited["total_real_submit_count"], 279)
        self.assertEqual(audited["verify_epoch"]["release_tail"], "0")
        self.assertEqual(audited["verify_epoch"]["single_terminal"], "0")
        self.assertFalse(audited["phase_b_started"])
        self.assertIn(
            "D282_01_ATTEMPT_03_EXACT_FAILED_ASSERT="
            "VERIFY_RELEASE_TAIL_1_SINGLE_TERMINAL_1_EXPECTED_ACTUAL_0_0",
            self.attempt_03_env)

    def test_65_verify_epoch_audit_accepts_coherent_close_only(self):
        helper = function_slice(
            self.kit, "verify_current_live_epoch_audit ()",
            "run_live ()")
        raw = (ATTEMPT_03_CAPTURE / "phase-a-audit.raw").read_text()
        with tempfile.TemporaryDirectory(prefix="goodix-d282-audit-") as td:
            audit = Path(td) / "audit.raw"
            audit.write_text(raw)
            accepted = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + helper +
                 '\nverify_current_live_epoch_audit "$1" 1',
                 "d282-audit", str(audit)], capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0,
                             accepted.stdout + accepted.stderr)
            audit.write_text(raw.replace(
                "release_tail=0 single_terminal=0",
                "release_tail=1 single_terminal=1"))
            completed_tail = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + helper +
                 '\nverify_current_live_epoch_audit "$1" 1',
                 "d282-audit", str(audit)], capture_output=True, text=True)
            self.assertEqual(completed_tail.returncode, 0,
                             completed_tail.stdout + completed_tail.stderr)
            audit.write_text(raw.replace(
                "release_tail=0 single_terminal=0",
                "release_tail=1 single_terminal=0"))
            rejected = subprocess.run(
                ["bash", "-c", "set -euo pipefail\n" + helper +
                 '\nverify_current_live_epoch_audit "$1" 1',
                 "d282-audit", str(audit)], capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)

    def test_66_current_operator_path_is_direct_and_bounded(self):
        operator = function_slice(self.kit, "operator_run ()", "export_results ()")
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        candidate = function_slice(
            self.kit, "prepare_candidate ()", "prepare_staging_probe_candidate ()")
        self.assertIn("--operator-run", self.kit)
        self.assertIn("Digitare ESEGUI", operator)
        self.assertIn("sudo", operator)
        self.assertIn("--run-live", operator)
        self.assertIn("--export-results", operator)
        self.assertNotIn("grant", operator.lower())
        self.assertNotIn("validate_grant", live)
        self.assertNotIn("consume_validated_grant", live)
        self.assertNotIn("EXPECTED_GRANT_ID", candidate)
        self.assertIn("BIOMETRIC_ACTION_MAX=3", live)
        self.assertIn("EXPECTED_PHYSICAL_CONTACT_COUNT_MAX=10", live)
        self.assertIn("AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false", live)
        self.assertNotIn("RETRY_AUTHORIZED=false", live)

    def test_67_attempt_04_05_are_hash_pinned_and_distinctly_classified(self):
        result = subprocess.run(
            [sys.executable, str(ATTEMPT_04_05_AUDITOR)],
            check=True, capture_output=True, text=True)
        audited = json.loads(result.stdout)
        self.assertEqual(audited["outcome"], "PASS_EVIDENCE_CLASSIFICATION")
        self.assertEqual(
            audited["runs"]["04"]["different_finger_claim"],
            "NOT_APPLICABLE")
        self.assertTrue(
            audited["runs"]["04"]
            ["same_finger_second_verify_false_non_match_observed"])
        self.assertEqual(
            audited["runs"]["05"]["different_finger_claim"],
            "PASS_OPERATOR_ATTESTED_STIMULUS")
        self.assertEqual(
            audited["runs"]["05"]["audit_actions"], [
                "FPI_DEVICE_ACTION_ENROLL", "FPI_DEVICE_ACTION_VERIFY",
                "FPI_DEVICE_ACTION_VERIFY", "FPI_DEVICE_ACTION_NONE"])

    def test_68_phase_b_poka_yoke_and_unique_current_summary_keys(self):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        prompt = live.index("INDICE SINISTRO")
        phase_b_action = live.index(
            'fprintd-verify "$user"', live.index('verify-different.raw'))
        self.assertLess(prompt, phase_b_action)
        self.assertIn("indicherà il template registrato", live)
        self.assertIn("PHASE_B_PHYSICAL_FINGER_NOT_CONFIRMED", live)
        summary = live[live.index(
            "echo D282_01_RESULT=PASS_LIVE_PENDING_INDEPENDENT_REVIEW"):]
        summary = summary[:summary.index('} >"$live_result/summary.env"')]
        self.assertNotIn("AUTHORIZATION_CREDENTIAL_REQUIRED", summary)
        self.assertNotIn("AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED", summary)
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        self.assertEqual(
            cleanup.count(
                "AUTOMATIC_OR_IMPLICIT_SENSOR_RETRY_ALLOWED=false"), 1)

    def _assert_preconsumption_refusal(self, reason, source_anchor=None):
        live = function_slice(self.kit, "run_live ()", "operator_run ()")
        anchor = source_anchor or f"refuse {reason}"
        self.assertLess(live.index(anchor),
                        live.index("live_staging_started=true"))

    def _assert_unused(self, outcome):
        self.assertFalse(outcome.grant_consumed)
        self.assertFalse(outcome.real_usb_enumeration_attempted)
        self.assertFalse(outcome.live_execution_performed)
        self.assertFalse(outcome.retry_authorized)

    def _count_synthetic_targets(self, entries):
        count_function = function_slice(
            self.kit, "count_goodix_targets ()", "validate_grant ()")
        with tempfile.TemporaryDirectory(prefix="goodix-d282-sysfs-") as td:
            root = Path(td)
            for name, vendor, product in entries:
                device = root / name
                device.mkdir()
                (device / "idVendor").write_text(vendor + "\n")
                (device / "idProduct").write_text(product + "\n")
            result = subprocess.run(
                ["bash", "-c",
                 "set -euo pipefail\n" + count_function +
                 '\ncount_goodix_targets "$1"',
                 "d282-cardinality-test", str(root)],
                check=True, capture_output=True, text=True)
            return int(result.stdout.strip())

    def _exercise_staging(self, fail_after, seed=False):
        with tempfile.TemporaryDirectory(prefix="goodix-d282-model-") as td:
            root = Path(td)
            runtime, units, storage_root = (
                root / "run", root / "units", root / "storage")
            for directory in (runtime, units, storage_root):
                directory.mkdir()
            if seed:
                staging.seed_preexisting(storage_root)
            before = staging.manifest(storage_root)
            try:
                staging.stage(runtime, units, storage_root, fail_after)
                if fail_after:
                    self.fail("failure injection did not fire")
            except RuntimeError:
                self.assertIsNotNone(fail_after)
            finally:
                staging.rollback(runtime, units, storage_root)
            staging.assert_preserved(before, storage_root)
            self.assertFalse((runtime / staging.OWNED_NAME).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
