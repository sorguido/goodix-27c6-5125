"""Offline-only D246 live-enablement safety extension.

This file applies the already-reviewed D245 and D246 patches only inside a
temporary tree. No system USB implementation or protected input is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
SOURCE_FILES = (
    Path("src/goodix5125_d233_backend.py"),
    Path("src/goodix5125_d235_entrypoint.py"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_patched_runtime_tests() -> dict[str, object]:
    from analysis.D246.d246_runtime_matrix import (
        D4_ACK,
        assert_cleanup,
        d4_out_count,
        normal_frames,
        run_case,
    )
    from src.goodix5125_d232_offline import AbortClass, ReplayAbort
    from src.goodix5125_d233_backend import D4_CANONICAL_REQUEST, UsbFailure, UsbIdentity
    from src.goodix5125_d235_entrypoint import ProductionReportPolicy, map_production_report
    from tests.test_d233_backend import FakeUsbApi

    alternate_identity = UsbIdentity(0x27C6, 0x5125, 1, 5, (2, 4))

    class DisconnectAfterD4Api(FakeUsbApi):
        def bulk_in(self, handle, endpoint, maximum, timeout_ms):
            if self.outgoing and self.outgoing[-1][:10] == D4_CANONICAL_REQUEST:
                self.calls.append(("in_disconnect", endpoint, timeout_ms))
                raise UsbFailure("D246 injected device disappearance after D4")
            return super().bulk_in(handle, endpoint, maximum, timeout_ms)

    class ReenumerateAfterD4AckApi(FakeUsbApi):
        def identity(self, handle):
            if (
                self.outgoing
                and self.outgoing[-1][:10] == D4_CANONICAL_REQUEST
                and not self.incoming
            ):
                self.calls.append("identity_changed")
                return alternate_identity
            return super().identity(handle)

    class AmbiguousD4CompletionApi(FakeUsbApi):
        def bulk_out(self, handle, endpoint, data, timeout_ms):
            if bytes(data)[:10] == D4_CANONICAL_REQUEST:
                self.calls.append(("out_ambiguous", endpoint, timeout_ms))
                self.outgoing.append(bytes(data))
                return len(data) - 1
            return super().bulk_out(handle, endpoint, data, timeout_ms)

    disconnect_api = DisconnectAfterD4Api(normal_frames())
    disconnected = run_case([], api=disconnect_api)
    disconnected_report = disconnected["report"]
    require(disconnected_report["result"] == "abort", "disconnect must abort")
    require(disconnected_report["d4_attempt_count"] == 1, "disconnect D4 attempt")
    require(disconnected_report["d4_send_count"] == 1, "disconnect D4 count")
    require(
        disconnected_report["d4_failure_class"] == "usb_or_frame_error",
        "disconnect failure class",
    )
    require(d4_out_count(disconnected) == 1, "disconnect retried D4")
    require(disconnect_api.calls.count(("open", 0x27C6, 0x5125)) == 1, "disconnect reopened")
    require(disconnect_api.calls.count(("claim", 0)) == 1, "disconnect reclaimed")
    assert_cleanup(disconnected)

    reenumerated = run_case(
        [], api=ReenumerateAfterD4AckApi([*normal_frames(), D4_ACK])
    )
    reenumerated_report = reenumerated["report"]
    require(reenumerated_report["result"] == "abort", "re-enumeration must abort")
    require(reenumerated_report["d4_attempt_count"] == 1, "re-enumeration D4 attempt")
    require(reenumerated_report["d4_send_count"] == 1, "re-enumeration D4 count")
    require(reenumerated_report["d4_completed"] is False, "re-enumeration completed D4")
    require(
        reenumerated_report["d4_failure_class"] == "usb_or_frame_error",
        "re-enumeration failure class",
    )
    require(d4_out_count(reenumerated) == 1, "re-enumeration retried D4")
    assert_cleanup(reenumerated)

    happy = run_case([*normal_frames(), D4_ACK])
    backend = happy["backend"]
    outgoing_before = tuple(happy["api"].outgoing)
    try:
        backend._exchange_d4_after_tls()
    except ReplayAbort as exc:
        require(exc.abort_class == AbortClass.EXTRA_OR_REORDERED, "second D4 class")
    else:
        raise AssertionError("second D4 unexpectedly reachable")
    require(tuple(happy["api"].outgoing) == outgoing_before, "second D4 emitted OUT")
    require(backend.d4_attempt_count == 1, "happy re-entry changed attempt latch")
    assert_cleanup(happy)

    ambiguous = run_case([], api=AmbiguousD4CompletionApi(normal_frames()))
    ambiguous_report = ambiguous["report"]
    ambiguous_backend = ambiguous["backend"]
    require(ambiguous_report["result"] == "abort", "ambiguous completion must abort")
    require(ambiguous_report["d4_attempt_count"] == 1, "attempt latch not set pre-submit")
    require(ambiguous_report["d4_send_count"] == 0, "ambiguous submit marked confirmed")
    require(
        ambiguous_report["d4_failure_class"] == "ambiguous_usb_completion",
        "ambiguous completion class",
    )
    ambiguous_mapped = map_production_report(
        ambiguous_report,
        ProductionReportPolicy("offline_dry_run", "not_applicable", "no"),
    )
    require(ambiguous_mapped["retry_count"] == 0, "ambiguous completion retried")
    require(d4_out_count(ambiguous) == 1, "ambiguous D4 physical attempt count")
    ambiguous_outgoing = tuple(ambiguous["api"].outgoing)
    try:
        ambiguous_backend._exchange_d4_after_tls()
    except ReplayAbort as exc:
        require(exc.abort_class == AbortClass.EXTRA_OR_REORDERED, "ambiguous re-entry class")
    else:
        raise AssertionError("ambiguous D4 re-entry unexpectedly reachable")
    require(
        tuple(ambiguous["api"].outgoing) == ambiguous_outgoing,
        "ambiguous re-entry emitted a second transport write",
    )
    require(ambiguous_backend.d4_attempt_count == 1, "ambiguous re-entry changed latch")
    require(ambiguous_backend.d4_failure_class == "ambiguous_usb_completion", "failure class lost")
    assert_cleanup(ambiguous)

    return {
        "schema": "d246-live-enablement-offline-v1",
        "status": "PASS",
        "unexpected_disconnect": "TERMINAL_NO_RETRY_NO_REOPEN",
        "unexpected_reenumeration": "TERMINAL_NO_RETRY_NO_RECLAIM",
        "second_d4": "UNREACHABLE",
        "ambiguous_completion_reentry": "PASS_ATTEMPT_LATCHED_SECOND_WRITE_ZERO",
        "automatic_reset_recovery": "FORBIDDEN_NOT_INVOKED",
        "real_usb_open_count": 0,
        "real_tls_handshake_count": 0,
        "real_d4_send_count": 0,
        "persistent_write_family_count": 0,
    }


def run_parent() -> dict[str, object]:
    from analysis.D246.d246_live_critical import offline_stale_detection_test
    from analysis.D246.d246_preflight import offline_sandbox_preflight
    from analysis.D246.d246_preflight_observability import render

    before = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    with tempfile.TemporaryDirectory(prefix="d246-preflight-fixture-") as preflight_root:
        preflight = offline_sandbox_preflight(Path(preflight_root))
    require(preflight["status"] == "PASS", "D246 preflight namespace fixtures failed")
    require(preflight["d245_marker_touched"] is False, "historical D245 marker changed")
    require(
        "/analysis/D246/D246_preflight_report.json"
        in preflight["durable_preflight_report"],
        "D246 durable preflight report namespace",
    )
    failure_render = render(
        {
            "failure_class": "d246_single_use_marker_consumed",
            "failures": ["d246_single_use_marker_consumed"],
            "marker_namespace_status": preflight["consumed_d246_marker_case"],
        }
    )
    require("D246_PHASE=PREFLIGHT" in failure_render, "D246 renderer phase")
    require("D245_PHASE=" not in failure_render, "D245 renderer namespace leaked")
    stale_detection = offline_stale_detection_test()
    with tempfile.TemporaryDirectory(prefix="d246-live-enablement-") as directory:
        work = Path(directory)
        for name in ("src", "poc", "tests"):
            shutil.copytree(REPOSITORY / name, work / name)
        (work / "analysis/D230/work/GoodixExport").mkdir(parents=True)
        shutil.copy2(
            REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll",
            work / "analysis/D230/work/GoodixExport/gfusb.dll",
        )
        (work / "analysis/D246").mkdir(parents=True)
        for name in ("d246_runtime_matrix.py", "d246_live_enablement_offline.py"):
            shutil.copy2(REPOSITORY / "analysis/D246" / name, work / "analysis/D246" / name)
        for patch in (
            REPOSITORY / "analysis/D245/D245_live_unseal.patch",
            REPOSITORY / "analysis/D246/D246_d4_continuation.patch",
        ):
            subprocess.run(
                ["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
                cwd=work,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        environment = dict(os.environ)
        environment.update(PYTHONPATH=str(work), PYTHONDONTWRITEBYTECODE="1")
        result = subprocess.run(
            [sys.executable, "analysis/D246/d246_live_enablement_offline.py", "--patched-runtime"],
            cwd=work,
            env=environment,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode:
            raise RuntimeError(
                f"patched runtime failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
            )
        report = json.loads(result.stdout)
    after = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    require(before == after, "canonical source changed during offline tests")
    require(report.get("status") == "PASS", "patched runtime tests failed")
    report["preflight_namespace"] = preflight
    report["preflight_failure_renderer_namespace"] = "PASS_D246_ONLY"
    report["live_critical_stale_detection"] = stale_detection
    return report


def main() -> int:
    if sys.argv[1:] == ["--patched-runtime"]:
        report = run_patched_runtime_tests()
    elif not sys.argv[1:]:
        report = run_parent()
    else:
        print("d246_live_enablement_offline: unexpected arguments", file=sys.stderr)
        return 64
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
