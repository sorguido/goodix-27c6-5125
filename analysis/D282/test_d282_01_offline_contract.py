#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

from analysis.D282 import d282_01_grant_ordering_model as grant_ordering


ROOT = Path(__file__).resolve().parents[2]
FPRINTD = ROOT / "reference/fprintd-fedora44-1.94.5/source/src/device.c"
VERIFY_UTILITY = ROOT / "reference/fprintd-fedora44-1.94.5/source/utils/verify.c"
FPRINTD_SPEC = ROOT / "reference/fprintd-fedora44-1.94.5/fprintd.spec"
CORE = ROOT / "reference/libfprint-fedora44-1.94.100/source/libfprint"
DRIVER = ROOT / "libfprint-driver/goodix_fpimage_device.c"
PRODUCTION_TEST = ROOT / "libfprint-driver/tests/test_goodix_d278_secure_session.c"
FEDORA_ACTION_TEST = ROOT / "libfprint-driver/tests/test_goodix_fedora44_nbis_action.c"
KIT = ROOT / "operator_kit/d282-01-fprintd-target/run-d282-01.sh"
README = ROOT / "operator_kit/d282-01-fprintd-target/README_IT.md"
BUILD = ROOT / "operator_kit/d282-01-fprintd-target/build-inner.sh"

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
        cls.driver = DRIVER.read_text()
        cls.production_test = PRODUCTION_TEST.read_text()
        cls.fedora_action_test = FEDORA_ACTION_TEST.read_text()
        cls.kit = KIT.read_text()
        cls.readme = README.read_text()
        cls.build = BUILD.read_text()

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
        self.assertIn("rc=$exit_status", self.kit)

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
                'validate_selinux_preconditions "$system_library" "$storage_root"',
                "refuse UNIT_SNAPSHOT_FAILED",
                "refuse STORAGE_INVENTORY_FAILED",
                'prepare_grant_claim "$expected_id"'):
            self.assertLess(live.index(anchor), consume, anchor)
        self.assertLess(live.index("trap cleanup_live EXIT"), consume)
        self.assertLess(consume, live.index("staging_started=true"))
        self.assertLess(live.index("staging_started=true"),
                        live.index('install -d -m 0700 "$runtime"'))
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
            source_anchor='validate_selinux_preconditions "$system_library" "$storage_root"')
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
        consume = live.index('consume_validated_grant "$grant"')
        self.assertLess(live.index("trap cleanup_live EXIT"), consume)
        self.assertLess(consume, live.index('install -d -m 0700 "$runtime"'))
        self.assertIn('echo "GRANT_CONSUMED=$grant_consumed"', live)
        self.assertIn('echo "RETRY_AUTHORIZED=false"', live)
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
