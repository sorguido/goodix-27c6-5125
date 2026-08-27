# SPDX-License-Identifier: GPL-2.0-or-later
import json, subprocess, unittest
from pathlib import Path
from unittest import mock
from core.persistent_runtime import TerminalBoundary
import tools.d275_live_second_b0_once as tool
import core.d268_first_image_operator as d268

REPO=Path(__file__).resolve().parents[1]
class D275LiveOneShotTests(unittest.TestCase):
 def test_fake_live_same_entrypoint_closes_second_b0(self):
  p=subprocess.run(["./operator_kit/d275-second-b0-once.sh","--fake-live","--terminal-boundary","STOP_AFTER_SECOND_IMAGE"],cwd=REPO,text=True,capture_output=True)
  self.assertEqual(p.returncode,0,p.stderr); d=json.loads(p.stdout); self.assertEqual(d["OUTCOME"],"PASS"); self.assertFalse(d["third_cycle_started"])
 def test_historical_default_is_not_silently_promoted(self):
  self.assertEqual(TerminalBoundary.STOP_AFTER_FIRST_IMAGE.value,"STOP_AFTER_FIRST_IMAGE")
  self.assertEqual(tool.main(["--fake-live"]),2)
 def test_gate_is_exact_and_precedes_usb(self):
  with mock.patch.dict("os.environ",{tool.BASELINE_ENV:"a"*40}), mock.patch.object(tool,"verify_d268_authoritative_baseline") as verify:
   self.assertEqual(tool.live_once("vague"),1); verify.assert_not_called()
 def test_d268_runner_default_remains_first_image(self):
  self.assertNotIn("terminal_mode", d268.run_d268_first_image_candidate.__kwdefaults__ or {})
  self.assertIn("TerminalBoundary.STOP_AFTER_FIRST_IMAGE", (REPO/"core/d268_first_image_operator.py").read_text())
 def test_allowlist_has_no_persistent_families(self):
  source=(REPO/"core/persistent_runtime.py").read_text()
  self.assertIn("control not in {0x34, 0x20, 0x50, 0x32, 0x22}",source)
  for forbidden in ("0xA2, 0x70","flash","enrollment_commit","factory_reset"):
   self.assertNotIn(forbidden,source[source.index("class _ProductionMultiFrameChannel"):source.index("class PersistentRuntimeCoordinator")])
 def test_failure_matrix_is_owned_by_production_suite(self):
  # D275/01 exercises ACK07, stale/cross-cycle generation and event ordering;
  # D272/D273 cover wrong echo, NAV, B0 state, retry/reopen/third-cycle guards.
  self.assertEqual(tool.BOUNDARY,TerminalBoundary.STOP_AFTER_SECOND_IMAGE)
if __name__=="__main__": unittest.main()
