"""D235 production live-entrypoint composition, offline and source-sealed.

This module adds no protocol implementation.  It resolves production paths,
selects one exact USB target, constructs the D232/D233 components, maps their
terminal result, and owns the shipped entrypoint.  The shipped entrypoint hits
an unconditional source seal before sysfs, protected inputs, services, libusb,
or reports are touched.  A future D236 requires an explicit source patch.
"""

from __future__ import annotations

import json
import os
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Protocol, Sequence

from .goodix5125_d232_offline import (
    AbortClass,
    ContractError,
    DurableReportPublisher,
    SecretBuffer,
    TargetMaterial,
    TARGET_PID,
    TARGET_VID,
    load_root_psk,
    load_root_target_material,
)
from .goodix5125_d233_backend import (
    LibusbSystemApi,
    ProductionOsPreflight,
    ProductionReplayBackend,
    ProductionUsbTransport,
    SystemOsFacade,
    Tls12PskServer,
    UsbApi,
    UsbIdentity,
    run_production_candidate_offline,
)


D235_LIVE_CAPABILITY = 0
D235_LIVE_AUTHORIZATION = "no"
D236_OPERATOR_RISK_ACCEPTANCE = "not_granted"
D235_RESULT_SCHEMA = "d235-production-entrypoint-result-v1"
D235_OFFLINE_MODE = "injected_offline_entrypoint_review"
CANONICAL_GFUSB_SHA256 = (
    "904eab1d9dbfab2609da361aa6ddba549a9d503f85b4e439b0294908f4cbc7e2"
)


class D235LiveUnavailable(RuntimeError):
    """The D235 shipped entrypoint stopped at its source seal."""


def _d235_source_seal() -> None:
    """Unconditional barrier; D236 must modify source, never runtime state."""
    raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")


@dataclass(frozen=True)
class ProductionRuntimePaths:
    psk_store: Path
    target_material_manifest: Path
    config90_store: Path
    canonical_gfusb: Path
    report_directory: Path
    checkpoint_report: Path
    final_report: Path
    single_use_marker: Path

    @classmethod
    def system_default(cls) -> "ProductionRuntimePaths":
        repository = Path(__file__).resolve().parents[1]
        store = Path("/var/lib/goodix-5125-poc")
        reports = store / "d243-results"
        return cls(
            psk_store=store / "transport-material.bin",
            target_material_manifest=store / "target-material-manifest.json",
            config90_store=store / "target-config-90.bin",
            canonical_gfusb=repository / "analysis/D230/work/GoodixExport/gfusb.dll",
            report_directory=reports,
            checkpoint_report=reports / "d243-live-pre-restore.json",
            final_report=reports / "d243-live-result.json",
            single_use_marker=store / "d243-operator-invocation.marker",
        )

    def validate(self) -> None:
        values = tuple(Path(value) for value in self.__dict__.values())
        if any(not value.is_absolute() for value in values):
            raise ContractError("production runtime path is not absolute")
        if len(set(values)) != len(values):
            raise ContractError("production runtime paths overlap")
        if self.checkpoint_report.parent != self.report_directory:
            raise ContractError("checkpoint outside report directory")
        if self.final_report.parent != self.report_directory:
            raise ContractError("final report outside report directory")
        if self.psk_store.parent != self.config90_store.parent:
            raise ContractError("protected stores have inconsistent roots")
        if self.target_material_manifest.parent != self.psk_store.parent:
            raise ContractError("protected manifest has inconsistent root")


@dataclass(frozen=True)
class ResolvedUsbTarget:
    identity: UsbIdentity
    device_path: Path

    def validate(self) -> None:
        if (self.identity.vid, self.identity.pid) != (TARGET_VID, TARGET_PID):
            raise ContractError("resolved USB target has wrong VID/PID")
        expected = Path(f"/dev/bus/usb/{self.identity.bus:03d}/{self.identity.address:03d}")
        if self.device_path != expected or not self.device_path.is_absolute():
            raise ContractError("resolved USB device path is inconsistent")
        if not self.identity.port_path:
            raise ContractError("resolved USB target lacks a stable port path")


class UsbTargetSelector(Protocol):
    def resolve_exact(self, vid: int, pid: int) -> ResolvedUsbTarget: ...


class SystemUsbTargetSelector:
    """Resolve one exact sysfs target without opening a USB device."""

    SYSFS_USB = Path("/sys/bus/usb/devices")

    @staticmethod
    def _read(path: Path) -> str:
        return path.read_text(encoding="ascii").strip()

    @staticmethod
    def _port_path(entry_name: str) -> tuple[int, ...]:
        if "-" not in entry_name:
            return ()
        suffix = entry_name.split("-", 1)[1].split(":", 1)[0]
        try:
            return tuple(int(part, 10) for part in suffix.split("."))
        except ValueError:
            return ()

    def resolve_exact(self, vid: int, pid: int) -> ResolvedUsbTarget:
        if (vid, pid) != (TARGET_VID, TARGET_PID):
            raise ContractError("non-target selector request")
        candidates: list[ResolvedUsbTarget] = []
        for entry in sorted(self.SYSFS_USB.iterdir(), key=lambda item: item.name):
            try:
                if int(self._read(entry / "idVendor"), 16) != vid:
                    continue
                if int(self._read(entry / "idProduct"), 16) != pid:
                    continue
                bus = int(self._read(entry / "busnum"), 10)
                address = int(self._read(entry / "devnum"), 10)
            except (FileNotFoundError, PermissionError, UnicodeError, ValueError):
                continue
            identity = UsbIdentity(vid, pid, bus, address, self._port_path(entry.name))
            target = ResolvedUsbTarget(
                identity, Path(f"/dev/bus/usb/{bus:03d}/{address:03d}")
            )
            try:
                status = os.lstat(target.device_path)
            except OSError as exc:
                raise ContractError("resolved USB device node unavailable") from exc
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISCHR(status.st_mode):
                raise ContractError("resolved USB path is not a character device")
            target.validate()
            candidates.append(target)
        if len(candidates) != 1:
            raise ContractError("exactly one target USB device is required")
        return candidates[0]


class ProtectedInputProvider(Protocol):
    offline_only: bool

    def load_material(self) -> TargetMaterial: ...
    def load_secret(self) -> SecretBuffer: ...


class RootProtectedInputProvider:
    """Single-load root provider; validation remains owned by D232 loaders."""

    offline_only = False

    def __init__(self, paths: ProductionRuntimePaths):
        self.paths = paths
        self.material_load_count = 0
        self.secret_load_count = 0

    def load_material(self) -> TargetMaterial:
        if self.material_load_count:
            raise ContractError("target material loaded more than once")
        self.material_load_count = 1
        return load_root_target_material(
            self.paths.target_material_manifest, self.paths.config90_store
        )

    def load_secret(self) -> SecretBuffer:
        if self.secret_load_count:
            raise ContractError("PSK loaded more than once")
        self.secret_load_count = 1
        return load_root_psk(self.paths.psk_store)


@dataclass(frozen=True)
class ProductionReportPolicy:
    execution_mode: str
    operator_risk_acceptance: str
    live_authorization: str


_ATTEMPT_DECISIONS = {
    "E4": "D236_ABORTED_E4_BINDING",
    "A2_1": "D236_ABORTED_A2",
    "CHIP_82": "D236_ABORTED_CHIPID",
    "OTP_A6": "D236_ABORTED_OTP",
    "A2_2": "D236_ABORTED_A2",
    "MODE_70": "D236_ABORTED_MODE70",
    "DAC_220": "D236_ABORTED_DAC",
    "DAC_236": "D236_ABORTED_DAC",
    "DAC_238": "D236_ABORTED_DAC",
    "DAC_23A": "D236_ABORTED_DAC",
    "CONFIG_90": "D236_ABORTED_CONFIG90",
    "D1": "D236_ABORTED_D1",
    "TLS": "D236_ABORTED_TLS",
}


def map_future_live_decision(report: Mapping[str, object]) -> str:
    """Map every D233 terminal to one future D236 decision."""
    if report.get("result") == "pass":
        return "D236_LIVE_TLS_HANDSHAKE_SUCCESS"
    abort = str(report.get("abort_class", AbortClass.INTERNAL.value))
    reached = str(report.get("reached_phase", "not_reached"))
    attempted = str(report.get("attempted_phase", "not_reached"))
    failure_domain = str(report.get("backend_failure_domain", "none"))
    if reached == "PREFLIGHT":
        return (
            "D236_BLOCKED_BY_PREFLIGHT"
            if abort == AbortClass.PREFLIGHT.value
            else "D236_INTERNAL_SAFETY_VIOLATION"
        )
    if reached in {"PROTECTED_INPUT_GATE", "PE_REFERENCE_GATE", "SECRET_LOAD_GATE"}:
        return "D236_BLOCKED_BY_PROTECTED_INPUT"
    if abort == AbortClass.INTERNAL.value:
        return "D236_INTERNAL_SAFETY_VIOLATION"
    if failure_domain == "usb_transport":
        return "D236_ABORTED_USB_TRANSPORT"
    if abort == AbortClass.SECRET_BOUNDARY.value:
        return "D236_ABORTED_E4_BINDING"
    if abort == AbortClass.WRONG_CHIPID.value:
        return "D236_ABORTED_CHIPID"
    if abort == AbortClass.OTP_MALFORMED.value:
        return "D236_ABORTED_OTP"
    if abort in {
        AbortClass.BAD_RECORD_MAC.value,
        AbortClass.TLS_ALERT.value,
        AbortClass.TLS_TIMEOUT.value,
    }:
        return "D236_ABORTED_TLS"
    if attempted in _ATTEMPT_DECISIONS:
        return _ATTEMPT_DECISIONS[attempted]
    return "D236_INTERNAL_SAFETY_VIOLATION"


def map_production_report(
    report: Mapping[str, object], policy: ProductionReportPolicy
) -> dict[str, object]:
    mapped = dict(report)
    mapped.update(
        schema=D235_RESULT_SCHEMA,
        execution_mode=policy.execution_mode,
        operator_risk_acceptance=policy.operator_risk_acceptance,
        live_authorization=policy.live_authorization,
        decision=map_future_live_decision(report),
        d4_count=0,
        application_data_count=0,
        persistent_write_family_count=0,
        retry_count=0,
        automatic_invasive_recovery="forbidden",
        contains_secret=False,
        contains_raw_config90=False,
        contains_biometric_data=False,
        d241_result=(
            "TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED_D4_NOT_EXECUTED"
            if report.get("result") == "pass"
            else "D241_ABORTED_FAIL_CLOSED"
        ),
        d241_failure_class=(
            report.get("tls_failure_class")
            if report.get("tls_failure_class") not in (None, "none")
            else report.get("abort_class", AbortClass.INTERNAL.value)
            if report.get("result") != "pass"
            else "none"
        ),
        d241_d1_direct_b0_handoff=(
            "exactly_once"
            if report.get("first_tls_record_handoff_count") == 1
            else "not_completed"
        ),
        d241_psk_binding=(
            "same_e4_validated_secret_object_used_by_tls"
            if report.get("same_validated_psk_used_by_tls") is True
            else "not_proven"
        ),
        d241_tls_handshake_timeout_policy="bounded_3000ms_no_retry",
        d241_tls_trace_redacted=True,
        d242_result=(
            "TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED_D4_NOT_EXECUTED"
            if report.get("result") == "pass"
            else "D242_ABORTED_FAIL_CLOSED"
        ),
        d242_failure_class=(
            report.get("tls_failure_class")
            if report.get("tls_failure_class") not in (None, "none")
            else report.get("abort_class", AbortClass.INTERNAL.value)
            if report.get("result") != "pass"
            else "none"
        ),
        d242_transport_fix="OEM_64_BYTE_OUT_AND_10MS_TLS_RECORD_PACING",
        d243_result=(
            "TLS_CRYPTOGRAPHIC_HANDSHAKE_COMPLETED_D4_NOT_EXECUTED"
            if report.get("result") == "pass"
            else "D243_ABORTED_FAIL_CLOSED"
        ),
        d243_failure_class=(
            report.get("tls_failure_class")
            if report.get("tls_failure_class") not in (None, "none")
            else report.get("abort_class", AbortClass.INTERNAL.value)
            if report.get("result") != "pass"
            else "none"
        ),
        d243_transport_split="A0_D241_SHORT_OUT_B0_D242_FIXED64_TLS_PACING_10MS",
    )
    return mapped


class MappedDurablePublisher:
    """Map immediately before delegating to the existing atomic publisher."""

    def __init__(self, delegate: DurableReportPublisher, policy: ProductionReportPolicy):
        self.delegate = delegate
        self.policy = policy
        self.publish_count = 0
        self.last_report: dict[str, object] | None = None

    def publish(self, report: Mapping[str, object]) -> None:
        if self.publish_count:
            raise ContractError("mapped report published more than once")
        mapped = map_production_report(report, self.policy)
        self.delegate.publish(mapped)
        self.last_report = mapped
        self.publish_count = 1


def _execute_composed_candidate(
    *,
    paths: ProductionRuntimePaths,
    os_facade: object,
    operator_uid: int,
    target: ResolvedUsbTarget,
    inputs: ProtectedInputProvider,
    usb_api: UsbApi,
    tls_factory: Callable[[SecretBuffer], Tls12PskServer],
    checkpoint_delegate: DurableReportPublisher,
    final_delegate: DurableReportPublisher,
    report_policy: ProductionReportPolicy,
) -> dict[str, object]:
    paths.validate()
    target.validate()
    preflight = ProductionOsPreflight(
        os_facade,
        operator_uid=operator_uid,
        device_path=target.device_path,
        marker=paths.single_use_marker,
        report=paths.final_report,
    )

    def backend_factory(secret: SecretBuffer, binder: object) -> ProductionReplayBackend:
        transport = ProductionUsbTransport(usb_api, expected_identity=target.identity)
        return ProductionReplayBackend(
            transport, secret, binder, tls_factory=tls_factory
        )

    checkpoint = MappedDurablePublisher(checkpoint_delegate, report_policy)
    final = MappedDurablePublisher(final_delegate, report_policy)
    run_production_candidate_offline(
        preflight_tx=preflight,
        material_loader=inputs.load_material,
        secret_loader=inputs.load_secret,
        canonical_pe_path=paths.canonical_gfusb,
        backend_factory=backend_factory,
        checkpoint_publisher=checkpoint,
        final_publisher=final,
    )
    if final.last_report is None:
        raise ContractError("final mapped report missing")
    return final.last_report


def run_injected_offline_entrypoint_review(
    *,
    offline_root: Path,
    paths: ProductionRuntimePaths,
    os_facade: object,
    operator_uid: int,
    target: ResolvedUsbTarget,
    inputs: ProtectedInputProvider,
    usb_api: UsbApi,
    tls_factory: Callable[[SecretBuffer], Tls12PskServer],
    checkpoint_delegate: DurableReportPublisher,
    final_delegate: DurableReportPublisher,
) -> dict[str, object]:
    """Exercise composition with synthetic dependencies; cannot use system ones."""
    root = Path(offline_root).resolve()
    confined = (
        paths.psk_store,
        paths.target_material_manifest,
        paths.config90_store,
        paths.report_directory,
        paths.checkpoint_report,
        paths.final_report,
        paths.single_use_marker,
    )
    if any(not Path(value).resolve().is_relative_to(root) for value in confined):
        raise ContractError("offline review path escaped its temporary root")
    if isinstance(os_facade, SystemOsFacade) or not getattr(os_facade, "offline_only", False):
        raise ContractError("system OS facade forbidden in offline review")
    if isinstance(usb_api, LibusbSystemApi) or not getattr(usb_api, "offline_only", False):
        raise ContractError("system USB API forbidden in offline review")
    if not getattr(inputs, "offline_only", False):
        raise ContractError("root protected inputs forbidden in offline review")
    return _execute_composed_candidate(
        paths=paths,
        os_facade=os_facade,
        operator_uid=operator_uid,
        target=target,
        inputs=inputs,
        usb_api=usb_api,
        tls_factory=tls_factory,
        checkpoint_delegate=checkpoint_delegate,
        final_delegate=final_delegate,
        report_policy=ProductionReportPolicy(
            D235_OFFLINE_MODE, "not_applicable_offline", "no"
        ),
    )


def _blocked(reason: str) -> dict[str, object]:
    return {
        "d235_live_capability": D235_LIVE_CAPABILITY,
        "d235_live_hard_disabled": True,
        "live_authorization": D235_LIVE_AUTHORIZATION,
        "runtime_live_enablement_exists": False,
        "usb_init_count": 0,
        "usb_open_count": 0,
        "reason": reason,
    }


def _early_terminal_report(
    *,
    reached_phase: str,
    abort_class: AbortClass,
    reason: str,
    policy: ProductionReportPolicy,
) -> dict[str, object]:
    raw: dict[str, object] = {
        "result": "abort",
        "terminal_state": "STOP",
        "reached_phase": reached_phase,
        "abort_class": abort_class.value,
        "attempted_phase": "not_reached",
        "backend_failure_domain": "none",
        "command_count": 0,
        "usb_open_count": 0,
        "tls_handshake_count": 0,
        "cleanup_count": 0,
        "report_publish_count": 0,
        "fprintd_initial_state": "not_acquired",
        "fprintd_restore_status": "not_needed",
        "signal_restore_status": "not_needed",
        "secret_zeroized": "not_loaded",
        "same_validated_psk_used_by_tls": False,
        "reason": reason,
    }
    return map_production_report(raw, policy)


def _publish_early_if_ready(
    report: dict[str, object],
    *,
    facade: SystemOsFacade,
    path: Path,
) -> dict[str, object]:
    if not facade.report_path_ready(path):
        return report
    durable = dict(report)
    durable["report_publish_count"] = 1
    DurableReportPublisher(path).publish(durable)
    return durable


def d235_entrypoint(
    argv: Sequence[str] = (),
    environ: Mapping[str, str] | None = None,
    config: Mapping[str, object] | None = None,
    backend_name: str | None = None,
) -> dict[str, object]:
    """Only shipped entrypoint; all D235 invocations stop at source."""
    del environ  # Environment is intentionally not an enablement surface.
    if argv or config is not None or backend_name is not None:
        return _blocked("operator arguments/config/backend cannot enable D235")
    try:
        _d235_source_seal()
    except D235LiveUnavailable as exc:
        return _blocked(str(exc))

    # Unreachable in shipped D235. D236 must source-patch the seal and its
    # compile-time authorization declarations, then review this exact wiring.
    paths = ProductionRuntimePaths.system_default()
    os_facade = SystemOsFacade()
    policy = ProductionReportPolicy(
            "future_live_single_shot",
        D236_OPERATOR_RISK_ACCEPTANCE,
        D235_LIVE_AUTHORIZATION,
    )
    try:
        paths.validate()
    except ContractError as exc:
        return _publish_early_if_ready(
            _early_terminal_report(
                reached_phase="PREFLIGHT",
                abort_class=AbortClass.INTERNAL,
                reason=str(exc),
                policy=policy,
            ),
            facade=os_facade,
            path=paths.final_report,
        )
    operator_uid = os_facade.sudo_uid()
    if os_facade.euid() != 0 or operator_uid is None:
        return _publish_early_if_ready(
            _early_terminal_report(
                reached_phase="PREFLIGHT",
                abort_class=AbortClass.PREFLIGHT,
                reason="root/SUDO_UID gate failed",
                policy=policy,
            ),
            facade=os_facade,
            path=paths.final_report,
        )
    try:
        target = SystemUsbTargetSelector().resolve_exact(TARGET_VID, TARGET_PID)
    except (ContractError, OSError, ValueError) as exc:
        return _publish_early_if_ready(
            _early_terminal_report(
                reached_phase="PREFLIGHT",
                abort_class=AbortClass.PREFLIGHT,
                reason=str(exc),
                policy=policy,
            ),
            facade=os_facade,
            path=paths.final_report,
        )
    inputs = RootProtectedInputProvider(paths)
    return _execute_composed_candidate(
        paths=paths,
        os_facade=os_facade,
        operator_uid=operator_uid,
        target=target,
        inputs=inputs,
        usb_api=LibusbSystemApi(),
        tls_factory=Tls12PskServer,
        checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
        final_delegate=DurableReportPublisher(paths.final_report),
        report_policy=policy,
    )


def main(argv: Sequence[str] | None = None) -> int:
    result = d235_entrypoint(tuple(sys.argv[1:] if argv is None else argv), os.environ)
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("decision") == "D236_LIVE_TLS_HANDSHAKE_SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
