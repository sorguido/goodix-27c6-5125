#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Kit operatore D265 one-shot; il dry-run non raggiunge capacità live."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.resolve(), *start.resolve().parents):
        if (candidate / ".git").exists() and (candidate / "AGENTS.md").is_file():
            return candidate
    raise RuntimeError("root del repository non trovata")


REPO = find_repo_root(Path(__file__))
if str(REPO) not in sys.path: sys.path.insert(0, str(REPO))

from core.future_first_image_operator import (  # noqa: E402
    D265_FUTURE_REPORT_PATH, D265_FUTURE_SINGLE_USE_MARKER_PATH,
    FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS, FutureProductionDependencies,
    issue_future_intent_for_injected_rehearsal, run_future_first_image_candidate,
    sha256_file,
)
from core.live_capability import D265_FUTURE_LIVE_AUTHORIZATION_FLAG as INTERNAL_INTENT_FLAG  # noqa: E402
from core.persistent_runtime import FIRST_IMAGE_IRQ2_TIMEOUT_MS  # noqa: E402

DRY_FLAG = "--dry-run"
LIVE_FLAG = "--i-authorize-one-d265-first-image-live-attempt"
APPROVED_BASELINE_ENV = "D265_APPROVED_LIVE_BASELINE_SHA"
CANONICAL_LIVE_COMMAND_TEMPLATE = (
    "sudo env D265_APPROVED_LIVE_BASELINE_SHA=<FULL_APPROVED_SHA> "
    "./operator_kit/d265-first-image-once.sh " + LIVE_FLAG
)
D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS = (
    "operator_kit/d265-first-image-once.sh", "tools/d265_live_first_image_once.py",
    *FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
)
MANIFEST = REPO / "analysis/D265/D265_01_live_critical_manifest.json"


@dataclass
class PhaseTracker:
    secret_materialization_count: int = 0
    marker_claim_count: int = 0
    live_io_capability_issue_count: int = 0
    coordinator_construct_count: int = 0
    operator_prompt_count: int = 0
    coordinator: Any = None


class PromptingEventSource:
    """Decorate only the real 15 s first-image IRQ2 wait."""
    def __init__(self, delegate: Any, tracker: PhaseTracker) -> None:
        self.delegate, self.tracker = delegate, tracker

    def wait_event(self, timeout_ms: int) -> bytes:
        if timeout_ms == FIRST_IMAGE_IRQ2_TIMEOUT_MS and self.tracker.operator_prompt_count == 0:
            print("Tieni il dito lontano dal sensore finché non compare la richiesta.")
            print("Quando richiesto, appoggia UN SOLO dito UNA SOLA volta e tienilo fermo fino alla conclusione.")
            print("Se questa esecuzione fallisce o va in timeout, NON riprovare.")
            print("D265_OPERATOR_ACTION = APPOGGIA_UN_DITO_ORA")
            self.tracker.operator_prompt_count += 1
        return self.delegate.wait_event(timeout_ms)


def instrument_dependencies(dependencies: Any, tracker: PhaseTracker) -> Any:
    """Decorate successful phase transitions without replacing production work."""
    def after(name: str, counter: str):
        original = getattr(dependencies, name)
        def wrapped(*args: Any, **kwargs: Any):
            value = original(*args, **kwargs)
            setattr(tracker, counter, getattr(tracker, counter) + 1)
            return value
        setattr(dependencies, name, wrapped)
    after("materialize_secret_once", "secret_materialization_count")
    after("claim_marker_once", "marker_claim_count")
    after("observe_live_io_issue", "live_io_capability_issue_count")
    original_construct = dependencies.construct_coordinator
    def construct(*args: Any, **kwargs: Any):
        coordinator = original_construct(*args, **kwargs)
        tracker.coordinator = coordinator
        tracker.coordinator_construct_count += 1
        coordinator.event_source = PromptingEventSource(coordinator.event_source, tracker)
        return coordinator
    dependencies.construct_coordinator = construct
    return dependencies


def _zero_side_effects() -> dict[str, int]:
    return {"REAL_USB_OPEN_COUNT": 0, "REAL_SECRET_READ_COUNT": 0,
            "REAL_SENSOR_COMMAND_COUNT": 0, "REAL_SINGLE_USE_MARKER_CREATE_COUNT": 0,
            "FPRINTD_MUTATION_COUNT": 0, "LIVE_TLS_HANDSHAKE_COUNT": 0}


def dry_run() -> dict[str, Any]:
    failures: list[str] = []
    try:
        doc = json.loads(MANIFEST.read_text(encoding="utf-8")); rows = doc["future_live_critical_files"]
        paths = tuple(row["path"] for row in rows)
        if doc.get("schema") != "D265_01_LIVE_CRITICAL_MANIFEST_V1": failures.append("schema")
        if doc.get("baseline_approved") is not False: failures.append("baseline_model")
        if paths != D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS: failures.append("path_authority")
        for row in rows:
            path = REPO / row["path"]
            if not path.is_file() or sha256_file(path) != row["sha256"]: failures.append(f"byte_identity:{row['path']}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append(f"manifest:{type(exc).__name__}"); rows = []
    syntax = subprocess.run(("bash", "-n", str(REPO / "operator_kit/d265-first-image-once.sh")), check=False).returncode == 0
    if not syntax: failures.append("launcher_syntax")
    return {"schema":"D265_01_OPERATOR_DRY_RUN_V2","OUTCOME":"PASS_OFFLINE_OPERATOR_KIT" if not failures else "FAIL_CLOSED",
            "execution_mode":"OFFLINE_ONLY","cwd_independent":True,"approved_baseline_environment":APPROVED_BASELINE_ENV,
            "canonical_live_command_template":CANONICAL_LIVE_COMMAND_TEMPLATE,"sudo_password_handling":"DELEGATED_TO_SUDO_INTERACTIVE",
            "approved_baseline_value_consumed":False,"full_40_lowercase_sha_required":True,
            "future_live_critical_file_count":len(rows),"future_live_critical_path_authority_exact":not any("authority" in x for x in failures),
            "launcher_syntax":"PASS" if syntax else "FAIL","marker_path_metadata_model":str(D265_FUTURE_SINGLE_USE_MARKER_PATH),
            "report_path_metadata_model":str(D265_FUTURE_REPORT_PATH),"protected_content_reads":0,"service_mutations":0,
            "live_capability_reachable":False,"failures":failures,"READY_FOR_LIVE":False,"LIVE_AUTHORIZED":False,
            "BASELINE_APPROVED":False,**_zero_side_effects()}


def _unknown_or(audit: dict[str, Any], key: str) -> Any: return audit[key] if key in audit else "UNKNOWN"


def _summary(sha: str, report: dict[str, Any], tracker: PhaseTracker | None = None) -> dict[str, Any]:
    tracker = tracker or PhaseTracker(); coordinator = tracker.coordinator
    audit = coordinator.audit() if coordinator is not None else report.get("runtime_audit", {})
    transport = getattr(coordinator, "transport", None); backend = getattr(transport, "backend", None)
    sessions = audit.get("usb_transport_session_count", "NOT_REACHED" if coordinator is None else "UNKNOWN")
    trace = audit.get("exact_fdt_command_trace", [])
    final_arm = trace.count("0x32") if isinstance(trace, list) else "UNKNOWN"
    forbidden = sum(x in {"0x34","0x20","0xa2","0x70"} for x in trace[8:]) if isinstance(trace, list) else "UNKNOWN"
    recovery = (audit.get("a2_special_recovery_count", 0) + audit.get("0x70_special_recovery_count", 0)
                if "a2_special_recovery_count" in audit and "0x70_special_recovery_count" in audit else "UNKNOWN")
    reopen = max(0, sessions - 1) if isinstance(sessions, int) else "UNKNOWN"
    result = report.get("result", "FAIL_CLOSED"); passed = result == "PASS_STOP_AFTER_FIRST_IMAGE"
    return {"OUTCOME":"PASS_D265_FIRST_IMAGE_LIVE" if passed else result,"APPROVED_BASELINE_SHA":sha,
            "LIVE_ATTEMPT_INVOCATION_COUNT":1,"D265_MARKER_CLAIMED":tracker.marker_claim_count == 1,
            "USB_OPEN_COUNT":getattr(backend,"open_count","NOT_REACHED" if coordinator is None else "UNKNOWN"),
            "TRANSPORT_SESSION_COUNT":sessions,"TLS_OBJECT_COUNT":_unknown_or(audit,"tls_server_session_object_count"),
            "TLS_HANDSHAKE_COUNT":_unknown_or(audit,"tls_server_handshake_count"),
            "SECRET_MATERIALIZATION_COUNT":tracker.secret_materialization_count,"FINAL_FDT_ARM_COUNT":final_arm,
            "IRQ2_FINGER_DOWN_COUNT":_unknown_or(audit,"first_image_irq2_observed_count"),
            "COMMAND_22_ATTEMPT_COUNT":_unknown_or(audit,"image_command_attempt_count"),
            "COMMAND_22_ACK_VALIDATION_COUNT":_unknown_or(audit,"first_image_ack_validation_count"),
            "FIRST_B0_COUNT":_unknown_or(audit,"first_image_b0_count"),
            "FIRST_IMAGE_DECODE_STATUS":"PASS" if audit.get("first_image_received") else ("NOT_REACHED" if coordinator is None else "FAIL_OR_NOT_REACHED"),
            "FIRST_IMAGE_RASTER_SHAPE":report.get("first_image_raster_shape","NOT_REACHED"),
            "RETRY_COUNT":_unknown_or(audit,"retry_count"),"RECOVERY_COUNT":recovery,"REOPEN_COUNT":reopen,
            "PERSISTENT_DEVICE_WRITE_COUNT":_unknown_or(audit,"persistent_device_write_count"),
            "FORBIDDEN_POST_IMAGE_COMMAND_COUNT":forbidden,"TERMINAL_BOUNDARY":"STOP_AFTER_FIRST_IMAGE",
            "LIVE_RESULT":result,"FAILURE_CLASS":report.get("failure_class","NONE" if passed else "UNKNOWN"),
            "HOST_CLEANUP_STATUS":("COMPLETED" if audit.get("transport_cleanup_count",0) == 1 and not audit.get("cleanup_failures") else "INCOMPLETE_OR_NOT_REACHED"),
            "FPRINTD_RESTORE_STATUS":"SEE_OPERATOR_REPORT","SECRET_ZEROIZED":_unknown_or(audit,"secret_boundary_zeroized")}


def verify_d265_approved_baseline(repo: Path, sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", sha): raise RuntimeError("baseline_full_sha_required")
    def git(*args: str, text: bool=True): return subprocess.run(("git",*args),cwd=repo,check=False,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=text)
    resolved=git("rev-parse",f"{sha}^{{commit}}")
    if resolved.returncode or resolved.stdout.strip()!=sha: raise RuntimeError("baseline_resolution_mismatch")
    head=git("rev-parse","HEAD")
    if head.returncode or head.stdout.strip()!=sha: raise RuntimeError("baseline_head_mismatch")
    dirty=git("status","--porcelain","--untracked-files=all")
    if dirty.returncode or dirty.stdout: raise RuntimeError("baseline_worktree_dirty")
    paths=tuple(row["path"] for row in json.loads(MANIFEST.read_text())["future_live_critical_files"])
    if paths!=D265_FIRST_IMAGE_LIVE_CRITICAL_PATHS: raise RuntimeError("live_critical_path_set_mismatch")
    for relative in paths:
        blob=git("show",f"{sha}:{relative}",text=False)
        if blob.returncode or blob.stdout!=(repo/relative).read_bytes(): raise RuntimeError(f"live_critical_byte_mismatch:{relative}")


def live_once() -> int:
    sha=os.environ.get(APPROVED_BASELINE_ENV,"")
    if not re.fullmatch(r"[0-9a-f]{40}",sha):
        print(json.dumps({"OUTCOME":"FAIL_BASELINE_FULL_SHA_REQUIRED",**_zero_side_effects()},sort_keys=True)); return 1
    try: verify_d265_approved_baseline(REPO,sha)
    except (RuntimeError,OSError,ValueError,KeyError) as exc:
        print(json.dumps({"OUTCOME":f"FAIL_{exc}",**_zero_side_effects()},sort_keys=True)); return 1
    intent=issue_future_intent_for_injected_rehearsal(INTERNAL_INTENT_FLAG); tracker=PhaseTracker()
    dependencies=instrument_dependencies(FutureProductionDependencies.build(REPO,intent),tracker)
    print("D265 sta per iniziare."); print("La password, se richiesta, è gestita direttamente da sudo.")
    try:
        report=run_future_first_image_candidate(intent,dependencies,repo=REPO,approved_baseline_sha=sha,
                authoritative_paths=FUTURE_FIRST_IMAGE_LIVE_CRITICAL_PATHS,ts16=int(time.time())&0xffff)
    finally: print("D265_OPERATOR_ACTION_WINDOW = CHIUSA")
    summary=_summary(sha,report,tracker); print(json.dumps(summary,sort_keys=True))
    for key,value in summary.items(): print(f"{key} = {value}")
    return 0 if summary["LIVE_RESULT"]=="PASS_STOP_AFTER_FIRST_IMAGE" else 1


def main(argv: list[str]|None=None) -> int:
    args=sys.argv[1:] if argv is None else argv
    if args==[DRY_FLAG]:
        report=dry_run(); print(json.dumps(report,indent=2,sort_keys=True)); return 0 if report["OUTCOME"]=="PASS_OFFLINE_OPERATOR_KIT" else 1
    if args==[LIVE_FLAG]: return live_once()
    print("HARD_DISABLED_DEFAULT: modalità D265 esatta richiesta"); return 2


if __name__=="__main__": raise SystemExit(main())
