#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Kit Operatore D268 first-image one-shot; dry-run privo di side effect."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.d268_first_image_operator import (  # noqa: E402
    D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS,
    D268_REPORT_PATH,
    D268_SINGLE_USE_MARKER_PATH,
    D268ProductionDependencies,
    issue_d268_intent_for_operator,
    run_d268_first_image_candidate,
    verify_d268_authoritative_baseline,
)
from core.live_capability import D268_LIVE_AUTHORIZATION_FLAG  # noqa: E402
from core.persistent_runtime import FIRST_IMAGE_IRQ2_TIMEOUT_MS  # noqa: E402


DRY_FLAG = "--dry-run"
LIVE_FLAG = D268_LIVE_AUTHORIZATION_FLAG
APPROVED_BASELINE_ENV = "D268_APPROVED_LIVE_BASELINE_SHA"
CANONICAL_LIVE_COMMAND_TEMPLATE = (
    "sudo env D268_APPROVED_LIVE_BASELINE_SHA=<SHA_COMPLETO_APPROVATO> "
    "./operator_kit/d268-first-image-once.sh " + LIVE_FLAG
)
MANIFEST = REPO / "analysis/D268/D268_01_live_critical_manifest.json"


@dataclass
class PhaseTracker:
    secret_materialization_count: int = 0
    marker_claim_count: int = 0
    live_io_capability_issue_count: int = 0
    coordinator_construct_count: int = 0
    operator_prompt_count: int = 0
    coordinator: Any = None


class PromptingEventSource:
    """Mostra una sola richiesta subito prima dell'attesa IRQ2 reale."""

    def __init__(self, delegate: Any, tracker: PhaseTracker) -> None:
        self.delegate = delegate
        self.tracker = tracker

    def wait_event(self, timeout_ms: int) -> bytes:
        if (
            timeout_ms == FIRST_IMAGE_IRQ2_TIMEOUT_MS
            and self.tracker.operator_prompt_count == 0
        ):
            print("Tieni il dito lontano dal sensore finché non compare la richiesta.")
            print(
                "Quando richiesto, appoggia UN SOLO dito UNA SOLA volta e "
                "tienilo fermo fino alla conclusione."
            )
            print("Se l'esecuzione fallisce o va in timeout, NON riprovare.")
            print("D268_AZIONE_OPERATORE = APPOGGIA_UN_DITO_ORA")
            self.tracker.operator_prompt_count += 1
        return self.delegate.wait_event(timeout_ms)


def instrument_dependencies(dependencies: Any, tracker: PhaseTracker) -> Any:
    """Conta le fasi host completate senza sostituire il lavoro produttivo."""

    def after(name: str, counter: str) -> None:
        original = getattr(dependencies, name)

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            value = original(*args, **kwargs)
            setattr(tracker, counter, getattr(tracker, counter) + 1)
            return value

        setattr(dependencies, name, wrapped)

    after("materialize_secret_once", "secret_materialization_count")
    after("claim_marker_once", "marker_claim_count")
    after("observe_live_io_issue", "live_io_capability_issue_count")
    original_construct = dependencies.construct_coordinator

    def construct(*args: Any, **kwargs: Any) -> Any:
        coordinator = original_construct(*args, **kwargs)
        tracker.coordinator = coordinator
        tracker.coordinator_construct_count += 1
        coordinator.event_source = PromptingEventSource(
            coordinator.event_source, tracker
        )
        return coordinator

    dependencies.construct_coordinator = construct
    return dependencies


def _zero_side_effects() -> dict[str, int]:
    return {
        "REAL_USB_ACCESS_COUNT": 0,
        "REAL_SECRET_READ_COUNT": 0,
        "REAL_DEVICE_COMMAND_COUNT": 0,
        "MARKER_MUTATION_COUNT": 0,
        "FPRINTD_MUTATION_COUNT": 0,
        "PERSISTENT_DEVICE_WRITE_COUNT": 0,
        "LIVE_TLS_HANDSHAKE_COUNT": 0,
    }


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dry_run() -> dict[str, Any]:
    """Legge soltanto metadata repository, manifest e sintassi shell."""
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    try:
        document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        rows = document["live_critical_files"]
        paths = tuple(row["path"] for row in rows)
        if document.get("schema") != "D268_01_LIVE_CRITICAL_MANIFEST_V1":
            failures.append("schema_manifest_non_valido")
        if document.get("authority") != "D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS":
            failures.append("authority_manifest_non_valida")
        if document.get("baseline_approved") is not False:
            failures.append("baseline_non_deve_essere_auto_approvata")
        if document.get("live_authorized") is not False:
            failures.append("live_non_deve_essere_autorizzato")
        if document.get("ready_for_live") is not False:
            failures.append("percorso_non_deve_essere_ready_live")
        if paths != D268_FIRST_IMAGE_LIVE_CRITICAL_PATHS:
            failures.append("path_set_live_critical_non_esatto")
        for row in rows:
            path = REPO / row["path"]
            if not path.is_file() or _sha256_file(path) != row["sha256"]:
                failures.append(f"identita_byte_non_valida:{row['path']}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failures.append(f"manifest_non_leggibile:{type(exc).__name__}")
    launcher = REPO / "operator_kit/d268-first-image-once.sh"
    syntax = subprocess.run(
        ("bash", "-n", str(launcher)), check=False
    ).returncode == 0
    if not syntax:
        failures.append("sintassi_launcher_non_valida")
    passed = not failures
    return {
        "schema": "D268_OPERATOR_DRY_RUN_V1",
        "OUTCOME": "PASS_KIT_OPERATORE_OFFLINE" if passed else "BLOCCATO_IN_SICUREZZA",
        "D268_OPERATOR_DRY_RUN": "PASS" if passed else "FAIL_CLOSED",
        "MESSAGGIO_OPERATORE": (
            "Verifica offline completata: nessun accesso al sensore."
            if passed
            else "Verifica offline fallita; non eseguire il percorso live."
        ),
        "execution_mode": "OFFLINE_ONLY",
        "cwd_independent": True,
        "approved_baseline_environment": APPROVED_BASELINE_ENV,
        "approved_baseline_value_consumed": False,
        "canonical_live_command_template": CANONICAL_LIVE_COMMAND_TEMPLATE,
        "full_40_lowercase_sha_required": True,
        "live_critical_file_count": len(rows),
        "live_critical_path_authority_exact": (
            "path_set_live_critical_non_esatto" not in failures
        ),
        "launcher_syntax": "PASS" if syntax else "FAIL",
        "marker_path_metadata_model": str(D268_SINGLE_USE_MARKER_PATH),
        "report_path_metadata_model": str(D268_REPORT_PATH),
        "protected_content_reads": 0,
        "service_mutations": 0,
        "live_capability_reachable": False,
        "failures": failures,
        "READY_FOR_LIVE": False,
        "LIVE_AUTHORIZED": False,
        "BASELINE_APPROVED": False,
        **_zero_side_effects(),
    }


def _unknown_or(audit: dict[str, Any], key: str) -> Any:
    return audit[key] if key in audit else "NON_RAGGIUNTO"


def _decode_fields(
    audit: dict[str, Any], report: dict[str, Any]
) -> dict[str, Any]:
    diagnostic = audit.get("first_image_decode_diagnostic")
    if not isinstance(diagnostic, dict):
        diagnostic = {}
    if audit.get("first_image_received"):
        status = "SUCCESSFUL_RASTER_DECODE"
    elif diagnostic.get("exception_class"):
        status = "DECODE_FAILED"
    else:
        status = "NOT_REACHED"
    return {
        "FIRST_IMAGE_DECODE_STATUS": status,
        "FIRST_IMAGE_DECODE_STAGE": diagnostic.get("decode_stage", "NOT_REACHED"),
        "FIRST_IMAGE_DECODE_EXCEPTION": diagnostic.get(
            "exception_class", "NONE" if status.startswith("SUCCESSFUL") else "NOT_REACHED"
        ),
        "FIRST_IMAGE_PAYLOAD_TRAILER_CLASS": diagnostic.get(
            "payload_trailer_class", "NOT_REACHED"
        ),
        "FIRST_IMAGE_PAYLOAD_CHECKSUM_POLICY": diagnostic.get(
            "payload_checksum_policy", "NOT_REACHED"
        ),
        "FIRST_IMAGE_PAYLOAD_CHECKSUM_MATCH": diagnostic.get(
            "payload_checksum_match", "NOT_REACHED"
        ),
        "FIRST_IMAGE_RECORD_CRC_MATCH": diagnostic.get(
            "image_record_crc_match", "NOT_REACHED"
        ),
        "FIRST_IMAGE_RASTER_SHAPE": report.get(
            "first_image_raster_shape",
            diagnostic.get("raster_shape_if_success", "NOT_REACHED"),
        ),
    }


def _summary(
    sha: str,
    report: dict[str, Any],
    tracker: PhaseTracker | None = None,
) -> dict[str, Any]:
    tracker = tracker or PhaseTracker()
    coordinator = tracker.coordinator
    audit = coordinator.audit() if coordinator is not None else report.get("runtime_audit", {})
    transport = getattr(coordinator, "transport", None)
    backend = getattr(transport, "backend", None)
    sessions = audit.get(
        "usb_transport_session_count",
        "NON_RAGGIUNTO" if coordinator is None else "SCONOSCIUTO",
    )
    trace = audit.get("exact_fdt_command_trace", [])
    final_arm = trace.count("0x32") if isinstance(trace, list) else "SCONOSCIUTO"
    forbidden = (
        sum(value in {"0x34", "0x20", "0xa2", "0x70"} for value in trace[8:])
        if isinstance(trace, list)
        else "SCONOSCIUTO"
    )
    recovery = (
        audit.get("a2_special_recovery_count", 0)
        + audit.get("0x70_special_recovery_count", 0)
        if "a2_special_recovery_count" in audit
        and "0x70_special_recovery_count" in audit
        else "SCONOSCIUTO"
    )
    reopen = max(0, sessions - 1) if isinstance(sessions, int) else "SCONOSCIUTO"
    result = report.get("result", "FAIL_CLOSED")
    passed = result == "PASS_STOP_AFTER_FIRST_IMAGE"
    failure = report.get("failure_class", "NESSUNO" if passed else "SCONOSCIUTO")
    return {
        "OUTCOME": "PASS_D268_FIRST_IMAGE_LIVE" if passed else result,
        "MESSAGGIO_OPERATORE": (
            "Prima immagine decodificata; esecuzione conclusa e cleanup completato."
            if passed
            else f"Esecuzione arrestata in sicurezza. Causa sanitizzata: {failure}"
        ),
        "APPROVED_BASELINE_SHA": sha,
        "LIVE_ATTEMPT_INVOCATION_COUNT": 1,
        "D268_MARKER_CLAIMED": tracker.marker_claim_count == 1,
        "USB_OPEN_COUNT": getattr(
            backend, "open_count", "NON_RAGGIUNTO" if coordinator is None else "SCONOSCIUTO"
        ),
        "TRANSPORT_SESSION_COUNT": sessions,
        "TLS_OBJECT_COUNT": _unknown_or(audit, "tls_server_session_object_count"),
        "TLS_HANDSHAKE_COUNT": _unknown_or(audit, "tls_server_handshake_count"),
        "SECRET_MATERIALIZATION_COUNT": tracker.secret_materialization_count,
        "FINAL_FDT_ARM_COUNT": final_arm,
        "IRQ2_FINGER_DOWN_COUNT": _unknown_or(
            audit, "first_image_irq2_observed_count"
        ),
        "COMMAND_22_ATTEMPT_COUNT": _unknown_or(audit, "image_command_attempt_count"),
        "COMMAND_22_ACK_VALIDATION_COUNT": _unknown_or(
            audit, "first_image_ack_validation_count"
        ),
        "FIRST_B0_COUNT": _unknown_or(audit, "first_image_b0_count"),
        **_decode_fields(audit, report),
        "RETRY_COUNT": _unknown_or(audit, "retry_count"),
        "RECOVERY_COUNT": recovery,
        "REOPEN_COUNT": reopen,
        "PERSISTENT_DEVICE_WRITE_COUNT": _unknown_or(
            audit, "persistent_device_write_count"
        ),
        "FORBIDDEN_POST_IMAGE_COMMAND_COUNT": forbidden,
        "TERMINAL_BOUNDARY": "STOP_AFTER_FIRST_IMAGE",
        "LIVE_RESULT": result,
        "FAILURE_CLASS": failure,
        "HOST_CLEANUP_STATUS": (
            "COMPLETATO"
            if audit.get("transport_cleanup_count", 0) == 1
            and not audit.get("cleanup_failures")
            else "INCOMPLETO_O_NON_RAGGIUNTO"
        ),
        "FPRINTD_RESTORE_STATUS": "VEDI_REPORT_OPERATORE",
        "SECRET_ZEROIZED": _unknown_or(audit, "secret_boundary_zeroized"),
    }


def live_once() -> int:
    sha = os.environ.get(APPROVED_BASELINE_ENV, "")
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        print(
            json.dumps(
                {
                    "OUTCOME": "BLOCCATO_BASELINE_SHA_COMPLETO_RICHIESTO",
                    "MESSAGGIO_OPERATORE": (
                        "Live non autorizzato: manca il commit SHA completo approvato."
                    ),
                    **_zero_side_effects(),
                },
                sort_keys=True,
            )
        )
        return 1
    try:
        verify_d268_authoritative_baseline(REPO, sha)
    except (RuntimeError, OSError, ValueError, KeyError) as exc:
        print(
            json.dumps(
                {
                    "OUTCOME": "BLOCCATO_BASELINE_NON_VALIDA",
                    "MESSAGGIO_OPERATORE": f"Live non avviato: {exc}",
                    **_zero_side_effects(),
                },
                sort_keys=True,
            )
        )
        return 1
    intent = issue_d268_intent_for_operator(LIVE_FLAG)
    tracker = PhaseTracker()
    dependencies = instrument_dependencies(
        D268ProductionDependencies.build(REPO, intent), tracker
    )
    print("Il tentativo D268 sta per iniziare.")
    print("La password, se richiesta, è gestita direttamente da sudo.")
    try:
        report = run_d268_first_image_candidate(
            intent,
            dependencies,
            repo=REPO,
            approved_baseline_sha=sha,
            ts16=int(time.time()) & 0xFFFF,
        )
    finally:
        print("D268_FINESTRA_AZIONE_OPERATORE = CHIUSA")
    summary = _summary(sha, report, tracker)
    print(json.dumps(summary, sort_keys=True))
    for key, value in summary.items():
        print(f"{key} = {value}")
    return 0 if summary["LIVE_RESULT"] == "PASS_STOP_AFTER_FIRST_IMAGE" else 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args == [DRY_FLAG]:
        report = dry_run()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["D268_OPERATOR_DRY_RUN"] == "PASS" else 1
    if args == [LIVE_FLAG]:
        return live_once()
    print(
        "D268 BLOCCATO: modalità esatta richiesta; nessun accesso al sensore eseguito.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
