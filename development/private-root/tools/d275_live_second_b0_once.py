#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""D275/02 bounded second-B0 operator entrypoint; fake-live is hardware inert."""
from __future__ import annotations
import argparse, json, os, re, sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))
from core.live_capability import D275_LIVE_AUTHORIZATION_FLAG
from core.persistent_runtime import TerminalBoundary
from core.d275_second_b0_operator import (
    D275_LIVE_CRITICAL_PATHS, build_dependencies, issue_intent, run_candidate,
    verify_d275_authoritative_baseline,
    D275OperatorPromptState,
    D275OperatorPromptingEventSource,
    print_d275_preparation,
    print_d275_success,
)

BOUNDARY = TerminalBoundary.STOP_AFTER_SECOND_IMAGE
FAKE_FLAG = "--fake-live"
BASELINE_ENV = "D275_APPROVED_LIVE_BASELINE_SHA"
GATE = "27c6:5125_ONE_SHOT_STOP_AFTER_SECOND_IMAGE_NO_RETRY_FACTORY_PRESERVING_NO_ENROLLMENT_NO_THIRD_CYCLE"

def fake_live() -> dict[str, object]:
    from tools.d264_first_image_offline import rehearse
    state = D275OperatorPromptState()
    print_d275_preparation(simulation=True)
    report = rehearse(
        BOUNDARY,
        event_source_wrapper=lambda es: D275OperatorPromptingEventSource(
            es, state=state, simulation=True
        ),
    )
    audit = report["runtime_audit"]
    trace = report["command_trace"]
    passed = (
        report["second_image_received"] is True and trace[-6:] == ["0x22","0x34","0x20","0x50","0x32","0x22"]
        and audit["usb_transport_session_count"] == 1
        and audit["tls_server_session_object_count"] == 1
        and audit["tls_server_handshake_count"] == 1
        and audit["secret_boundary_handoff_count"] == 1
        and audit["retry_count"] == 0 and audit["transport_cleanup_count"] == 1
        and audit["persistent_device_write_count"] == 0
    )
    if passed:
        print_d275_success(simulation=True)
    else:
        state.show_failure(simulation=True)
    return {
        "schema":"D275_02_FAKE_LIVE_V1", "OUTCOME":"PASS" if passed else "FAIL_CLOSED",
        "execution_mode":"FAKE_TRANSPORT_SAME_PRODUCTION_COORDINATOR",
        "terminal_boundary":BOUNDARY.value, "command_trace":trace,
        "ownership": {k:audit[k] for k in ("usb_transport_session_count","tls_server_session_object_count","tls_server_handshake_count","secret_boundary_handoff_count","retry_count","transport_cleanup_count","persistent_device_write_count")},
        "third_cycle_started":False, "biometric_payload_serialized":False,
        "REAL_USB_ACCESS":False,"REAL_SENSOR_COMMAND_COUNT":0,"NEW_LIVE_EVIDENCE":False,"LIVE_AUTHORIZED":False,
    }

def live_once(gate: str) -> int:
    sha=os.environ.get(BASELINE_ENV,"")
    if gate != GATE or not re.fullmatch(r"[0-9a-f]{40}",sha):
        print(json.dumps({"OUTCOME":"PRECHECK_FAILURE","REAL_USB_ACCESS":False,"REAL_SENSOR_COMMAND_COUNT":0}))
        return 1
    try: verify_d275_authoritative_baseline(REPO,sha,D275_LIVE_CRITICAL_PATHS)
    except Exception as exc:
        print(json.dumps({"OUTCOME":"PRECHECK_FAILURE","failure_class":f"{type(exc).__name__}:{exc}","REAL_USB_ACCESS":False,"REAL_SENSOR_COMMAND_COUNT":0}))
        return 1
    intent=issue_intent(D275_LIVE_AUTHORIZATION_FLAG)
    print_d275_preparation(simulation=False)
    prompt_state = D275OperatorPromptState()
    report=run_candidate(intent,build_dependencies(REPO,intent,prompt_state),repo=REPO,sha=sha,ts16=int(time.time())&0xffff)
    if report.get("result") == "PASS_STOP_AFTER_SECOND_IMAGE":
        print_d275_success(simulation=False)
    else:
        prompt_state.show_failure(simulation=False)
    print(json.dumps(report,sort_keys=True))
    return 0 if report["result"]=="PASS_STOP_AFTER_SECOND_IMAGE" else 1

def main(argv=None)->int:
    p=argparse.ArgumentParser()
    p.add_argument("--terminal-boundary",choices=[x.value for x in TerminalBoundary],default=TerminalBoundary.STOP_AFTER_FIRST_IMAGE.value)
    p.add_argument(FAKE_FLAG,action="store_true")
    p.add_argument(D275_LIVE_AUTHORIZATION_FLAG,action="store_true",dest="live")
    p.add_argument("--operator-gate",default="")
    a=p.parse_args(argv)
    if a.terminal_boundary != BOUNDARY.value:
        print(json.dumps({"OUTCOME":"PRECHECK_FAILURE","reason":"explicit_second_image_boundary_required","REAL_USB_ACCESS":False,"REAL_SENSOR_COMMAND_COUNT":0})); return 2
    if a.fake_live and not a.live:
        result=fake_live(); print(json.dumps(result,indent=2,sort_keys=True)); return 0 if result["OUTCOME"]=="PASS" else 1
    if a.live and not a.fake_live: return live_once(a.operator_gate)
    print(json.dumps({"OUTCOME":"PRECHECK_FAILURE","reason":"exactly_one_mode_required","REAL_USB_ACCESS":False,"REAL_SENSOR_COMMAND_COUNT":0})); return 2
if __name__=="__main__": raise SystemExit(main())
