#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

from analysis.D282 import d282_01_grant_ordering_model as grant_ordering


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
ATTEMPT_ENV = ROOT / "analysis/D282/D282_01_ATTEMPT_01_NORMALIZED.env"
ATTEMPT_REPORT = ROOT / "analysis/D282/D282_01_attempt_01_host_staging_failure.md"
OFFLINE_RESULT = ROOT / "analysis/D282/D282_01_OFFLINE_RESULT.env"

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
        cls.attempt_env = ATTEMPT_ENV.read_text()
        cls.attempt_report = ATTEMPT_REPORT.read_text()
        cls.offline_result = OFFLINE_RESULT.read_text()

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
        self.assertIn("DIFFERENT_FINGER_NO_MATCH=UNPROVEN_LIVE", self.readme)

    def test_05_identify_regression_remains(self):
        self.assertIn("FPI_DEVICE_ACTION_IDENTIFY", self.core)
        self.assertIn("fp_device_identify (", self.production_test)

    def test_06_enrollment_regression_remains(self):
        self.assertIn("FPI_DEVICE_ACTION_ENROLL", self.core)
        self.assertIn("GOODIX_SIGFM_ENROLL_MAX_STAGES", self.production_test)

    def test_07_retry_extraction_has_no_second_sensor_action(self):
        self.assertIn("goodix_test_sigfm_extract_set_failure (TRUE)",
                      self.production_test)
        self.assertIn("production_action_attempt_count, ==, 2u",
                      self.production_test)
        self.assertIn("production_rejected_action_count, ==, 1u",
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
        self.assertIn("D282_01_RESULT=FAIL_ROLLBACK", self.kit)
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
        self.assertIn("AUTHORIZED_BIOMETRIC_ACTION_MAX=3", self.kit)
        self.assertIn("RETRY_AUTHORIZED=false", self.kit)

    def test_20_no_persistent_family_outside_empty_allowlist(self):
        self.assertIn('KNOWN_PERSISTENT_FAMILY_ALLOWLIST_COUNT=$persistent_count',
                      self.kit)
        self.assertIn("persistent=0", self.kit)
        self.assertIn("PAM_IN_SCOPE=false", self.kit)

    def test_21_all_pre_live_gates_precede_atomic_consumption(self):
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        refusal = function_slice(self.kit, "refuse ()", "is_sha ()")
        consume = live.index('consume_validated_grant "$grant"')
        for anchor in (
                "refuse STAGING_COLLISION",
                "refuse FPRINTD_INITIAL_STATE_UNSAFE",
                "refuse SYSTEM_LIBFPRINT_MISSING",
                'validate_selinux_preconditions "$live_system_library" "$live_storage_root"',
                "refuse UNIT_SNAPSHOT_FAILED",
                "refuse STORAGE_INVENTORY_FAILED",
                'prepare_grant_claim "$expected_id"'):
            self.assertLess(live.index(anchor), consume, anchor)
        self.assertLess(live.index("trap cleanup_live EXIT"), consume)
        self.assertLess(consume, live.index("live_staging_started=true"))
        self.assertLess(live.index("live_staging_started=true"),
                        live.index('install -d -m 0700 "$live_runtime"'))
        after_consume = live[consume:]
        self.assertNotIn("command -v", after_consume)
        self.assertNotIn("$(getenforce)", after_consume)
        self.assertIn("validated_selinux_enforcement == Enforcing", after_consume)
        self.assertEqual(live.count('consume_validated_grant "$grant"'), 1)
        for marker in ('GRANT_CONSUMED=$grant_consumed',
                       'REAL_USB_ENUMERATION_ATTEMPTED=$real_usb_enumeration_attempted',
                       'LIVE_EXECUTION_PERFORMED=$live_execution_performed'):
            self.assertIn(marker, refusal)

    def test_22_staging_collision_does_not_consume_grant(self):
        self._assert_preconsumption_refusal("STAGING_COLLISION")

    def test_23_unsafe_fprintd_state_does_not_consume_grant(self):
        self._assert_preconsumption_refusal("FPRINTD_INITIAL_STATE_UNSAFE")

    def test_24_missing_system_libfprint_does_not_consume_grant(self):
        self._assert_preconsumption_refusal("SYSTEM_LIBFPRINT_MISSING")

    def test_25_unit_snapshot_failure_does_not_consume_grant(self):
        self._assert_preconsumption_refusal("UNIT_SNAPSHOT_FAILED")

    def test_26_storage_inventory_failure_does_not_consume_grant(self):
        self._assert_preconsumption_refusal("STORAGE_INVENTORY_FAILED")

    def test_27_selinux_precondition_failure_does_not_consume_grant(self):
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

    def test_30_postconsume_failure_rolls_back_without_retry_and_flow_is_unchanged(self):
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        cleanup = function_slice(self.kit, "cleanup_live ()", "verify_baseline ()")
        consume = live.index('consume_validated_grant "$grant"')
        self.assertLess(live.index("trap cleanup_live EXIT"), consume)
        self.assertLess(consume, live.index('install -d -m 0700 "$live_runtime"'))
        self.assertIn('echo "GRANT_CONSUMED=$grant_consumed"', cleanup)
        self.assertIn('echo "RETRY_AUTHORIZED=false"', cleanup)
        outcome = grant_ordering.simulate(
            grant_ordering.GrantRegistry(), "grant-1",
            fail_immediately_after_consumption=True)
        self.assertTrue(outcome.grant_consumed)
        self.assertFalse(outcome.retry_authorized)
        self.assertTrue(outcome.rollback_complete)
        self.assertFalse(outcome.real_usb_enumeration_attempted)
        self.assertFalse(outcome.live_execution_performed)

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

    def test_34_target_cardinality_gate_precedes_atomic_claim(self):
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        count = live.index(
            "target_preconsumption_match_count=$(count_goodix_targets")
        gate = live.index("refuse TARGET_CARDINALITY_NOT_ONE", count)
        prepare = live.index('prepare_grant_claim "$expected_id"')
        consume = live.index('consume_validated_grant "$grant"')
        self.assertLess(count, gate)
        self.assertLess(gate, prepare)
        self.assertLess(prepare, consume)
        self.assertIn(
            'TARGET_PRECONSUMPTION_MATCH_COUNT=$target_preconsumption_match_count',
            function_slice(self.kit, "refuse ()", "is_sha ()"))
        self._assert_preconsumption_refusal("TARGET_CARDINALITY_NOT_ONE")

    def test_35_post_start_cardinality_check_remains_as_anti_toctou(self):
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        consume = live.index('consume_validated_grant "$grant"')
        start = live.index("systemctl start fprintd.service", consume)
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
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
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
        run = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        self.assertLess(self.kit.index("cleanup_live ()"),
                        self.kit.index("run_authorized_live ()"))
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
                     '/var/lib/fprint/.goodix-d282-01-test "$1"\n')
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

        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
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

    def test_41_selinux_runtime_start_remains_an_explicit_blocker(self):
        for marker in (
                "D282_01_SYSTEMD_SELINUX_STAGING_CORRECTIVE=IMPLEMENTED_PENDING_PRIVILEGED_HOST_TEST",
                "FPRINTD_SYSTEMD_STAGING_START=NOT_RUN_REQUIRES_SEPARATE_PRIVILEGED_AUTHORIZATION",
                "SELINUX_EXEC_DENIAL=NOT_PROVEN_CORRECTED",
                "D282_01_HUMAN_GATE_READINESS=NOT_READY"):
            self.assertIn(marker, self.offline_result)

    def _assert_preconsumption_refusal(self, reason, source_anchor=None):
        live = function_slice(self.kit, "run_authorized_live ()", "export_results ()")
        anchor = source_anchor or f"refuse {reason}"
        self.assertLess(live.index(anchor),
                        live.index('consume_validated_grant "$grant"'))
        outcome = grant_ordering.simulate(
            grant_ordering.GrantRegistry(), "grant-1",
            preconsumption_refusal=reason)
        self._assert_unused(outcome)

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
