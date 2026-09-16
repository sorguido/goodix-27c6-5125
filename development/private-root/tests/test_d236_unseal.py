from __future__ import annotations

import contextlib
import io
import unittest
from unittest import mock

from src import goodix5125_d233_backend as d233
from src import goodix5125_d235_entrypoint as d235


class D236PostblockResealAndExitContractTests(unittest.TestCase):
    def test_source_is_resealed_after_preflight_block(self):
        with self.assertRaises(d233.D233LiveUnavailable):
            d233._d233_usb_source_seal()
        with self.assertRaises(d235.D235LiveUnavailable):
            d235._d235_source_seal()
        self.assertEqual(d235.D236_OPERATOR_RISK_ACCEPTANCE, "not_granted")
        self.assertEqual(d235.D235_LIVE_AUTHORIZATION, "no")
        self.assertEqual(d235.D235_RESULT_SCHEMA, "d235-production-entrypoint-result-v1")

    def test_exit_zero_depends_on_success_decision_even_with_one_usb_open(self):
        report = {
            "decision": "D236_LIVE_TLS_HANDSHAKE_SUCCESS",
            "usb_open_count": 1,
        }
        with mock.patch.object(d235, "d235_entrypoint", return_value=report):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(d235.main(()), 0)

    def test_every_blocker_or_abort_is_nonzero_even_with_zero_usb_open(self):
        for decision in (
            "D236_BLOCKED_BY_PREFLIGHT",
            "D236_ABORTED_E4_BINDING",
            "D236_ABORTED_USB_TRANSPORT",
            "D236_ABORTED_TLS",
            "D236_INTERNAL_SAFETY_VIOLATION",
        ):
            with self.subTest(decision=decision):
                report = {"decision": decision, "usb_open_count": 0}
                with mock.patch.object(d235, "d235_entrypoint", return_value=report):
                    with contextlib.redirect_stdout(io.StringIO()):
                        self.assertNotEqual(d235.main(()), 0)


if __name__ == "__main__":
    unittest.main()
