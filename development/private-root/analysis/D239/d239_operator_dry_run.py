"""D239 production-shaped offline operator path stopped at the pre-USB fence.

This module never imports or instantiates ``LibusbSystemApi``.  It exercises the
reviewed D235 composition with synthetic protected inputs and an offline USB
seam whose ``init`` boundary raises before any libusb operation can occur.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence

from src.goodix5125_d232_offline import (
    DurableReportPublisher,
    SecretBuffer,
    TargetMaterial,
    _config90_finalizer,
)
from src.goodix5125_d233_backend import UsbIdentity
from src.goodix5125_d235_entrypoint import (
    ProductionRuntimePaths,
    ResolvedUsbTarget,
    run_injected_offline_entrypoint_review,
)


REPOSITORY = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = REPOSITORY / "analysis/D239/D239_operator_dry_run_report.json"
ARTIFACTS = (
    "src/goodix5125_d233_backend.py",
    "src/goodix5125_d235_entrypoint.py",
    "analysis/D236/d236_preflight.py",
    "analysis/D239/d239_operator_dry_run.py",
    "analysis/D239/D239_live_unseal.patch",
    "operator_kit/d239-live-pre-d1-tls-once.sh",
)


class PreUsbFenceReached(RuntimeError):
    """The synthetic operator path reached the exact libusb-init seam."""


class OfflineFenceUsbApi:
    """Offline-only USB seam that stops before a libusb init can happen."""

    offline_only = True

    def __init__(self) -> None:
        self.pre_usb_fence_count = 0
        self.libusb_init_count = 0
        self.usb_open_count = 0
        self.goodix_command_count = 0

    def init(self) -> object:
        self.pre_usb_fence_count += 1
        raise PreUsbFenceReached("OPERATOR_KIT_DRY_RUN_PRE_USB fence")

    def open_exact(self, _context: object, _vid: int, _pid: int) -> object:
        self.usb_open_count += 1
        raise AssertionError("dry-run crossed the pre-USB fence")

    def identity(self, _handle: object) -> UsbIdentity:
        raise AssertionError("dry-run crossed the pre-USB fence")

    def claim_interface(self, _handle: object, _interface: int) -> None:
        raise AssertionError("dry-run crossed the pre-USB fence")

    def bulk_out(
        self, _handle: object, _endpoint: int, _data: bytes, _timeout_ms: int
    ) -> int:
        self.goodix_command_count += 1
        raise AssertionError("dry-run crossed the pre-USB fence")

    def bulk_in(
        self, _handle: object, _endpoint: int, _maximum: int, _timeout_ms: int
    ) -> bytes:
        raise AssertionError("dry-run crossed the pre-USB fence")

    def release_interface(self, _handle: object, _interface: int) -> None:
        raise AssertionError("dry-run crossed the pre-USB fence")

    def close(self, _handle: object) -> None:
        raise AssertionError("dry-run crossed the pre-USB fence")

    def exit(self, _context: object) -> None:
        raise AssertionError("dry-run crossed the pre-USB fence")


class OfflineFacade:
    """In-memory preflight facade; no process, service, signal, or marker I/O."""

    offline_only = True

    def __init__(self) -> None:
        self.synthetic_marker_claim_count = 0
        self.fprintd_stop_count = 0
        self.signal_restore_count = 0

    def euid(self) -> int:
        return 0

    def sudo_uid(self) -> int:
        return 1000

    def process_count(self) -> int:
        return 1

    def thread_count(self) -> int:
        return 1

    def external_holders(self, _path: Path) -> tuple[int, ...]:
        return ()

    def fprintd_active(self) -> bool:
        return False

    def stop_fprintd(self) -> None:
        self.fprintd_stop_count += 1
        raise AssertionError("offline facade must not stop fprintd")

    def start_fprintd(self) -> None:
        raise AssertionError("offline facade must not start fprintd")

    def block_signals(self, _signals: object) -> str:
        return "synthetic-signal-mask"

    def restore_signals(self, _previous: object) -> None:
        self.signal_restore_count += 1

    def claim_single_use_marker(self, _path: Path) -> None:
        self.synthetic_marker_claim_count += 1

    def report_path_ready(self, _path: Path) -> bool:
        return True


class SyntheticInputs:
    """In-memory target material and PSK; never reads production stores."""

    offline_only = True

    def __init__(self) -> None:
        self.material_load_count = 0
        self.secret_load_count = 0
        self.real_secret_read_count = 0
        config = bytearray((17 * index + 3) & 0xFF for index in range(224))
        dac = []
        for register, value, offset in (
            (0x0220, b"\xd8\x0b", 117),
            (0x0236, b"\xbe\x00", 121),
            (0x0238, b"\xbd\x00", 125),
            (0x023A, b"\xbc\x00", 129),
        ):
            config[offset : offset + 4] = register.to_bytes(2, "little") + value
            dac.append((register, value, offset))
        config[-2:] = _config90_finalizer(bytes(config))
        self.material = TargetMaterial(
            e4_validator_sha256=hashlib.sha256(b"d239-e4-validator").hexdigest(),
            a2_response_sha256=hashlib.sha256(b"d239-a2").hexdigest(),
            chip82_response_sha256=hashlib.sha256(b"d239-chip82").hexdigest(),
            otp_a6_response_sha256=hashlib.sha256(b"d239-otp").hexdigest(),
            dac=tuple(dac),
            config90=bytes(config),
            config90_sha256=hashlib.sha256(config).hexdigest(),
        )
        self._secret = b"D239 synthetic operator secret!!"
        if len(self._secret) != 32:
            raise AssertionError("synthetic secret length drift")

    def load_material(self) -> TargetMaterial:
        self.material_load_count += 1
        if self.material_load_count != 1:
            raise AssertionError("material loaded more than once")
        return self.material

    def load_secret(self) -> SecretBuffer:
        self.secret_load_count += 1
        if self.secret_load_count != 1:
            raise AssertionError("secret loaded more than once")
        return SecretBuffer.synthetic(self._secret)

    @property
    def secret_bytes(self) -> bytes:
        return self._secret


class OfflineTlsFactory:
    def __init__(self, _secret: SecretBuffer):
        raise AssertionError("TLS construction is beyond the pre-USB fence")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_hashes() -> dict[str, str]:
    return {name: sha256(REPOSITORY / name) for name in ARTIFACTS}


def publish(path: Path, report: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(report, sort_keys=True, indent=2) + "\n").encode()
    fd, temporary_name = tempfile.mkstemp(prefix=".d239-dry-run-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, payload)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temporary, path)
    finally:
        if fd >= 0:
            os.close(fd)
        if temporary.exists():
            temporary.unlink()


def run(report_path: Path = DEFAULT_REPORT) -> dict[str, object]:
    production_paths = ProductionRuntimePaths.system_default()
    production_paths.validate()
    with tempfile.TemporaryDirectory(prefix="d239-pre-usb-") as directory:
        root = Path(directory).resolve()
        store = root / "store"
        reports = root / "reports"
        store.mkdir()
        reports.mkdir()
        paths = ProductionRuntimePaths(
            psk_store=store / "synthetic-transport-material.bin",
            target_material_manifest=store / "synthetic-material-manifest.json",
            config90_store=store / "synthetic-config90.bin",
            canonical_gfusb=production_paths.canonical_gfusb,
            report_directory=reports,
            checkpoint_report=reports / "offline-checkpoint.json",
            final_report=reports / "offline-final.json",
            single_use_marker=store / "offline-single-use.marker",
        )
        facade = OfflineFacade()
        inputs = SyntheticInputs()
        usb = OfflineFenceUsbApi()
        identity = UsbIdentity(0x27C6, 0x5125, 1, 4, (7,))
        target = ResolvedUsbTarget(identity, Path("/dev/bus/usb/001/004"))
        composed = run_injected_offline_entrypoint_review(
            offline_root=root,
            paths=paths,
            os_facade=facade,
            operator_uid=1000,
            target=target,
            inputs=inputs,
            usb_api=usb,
            tls_factory=OfflineTlsFactory,
            checkpoint_delegate=DurableReportPublisher(paths.checkpoint_report),
            final_delegate=DurableReportPublisher(paths.final_report),
        )
        serialized_reports = paths.checkpoint_report.read_bytes() + paths.final_report.read_bytes()
        secret_absent = inputs.secret_bytes not in serialized_reports
        offline_marker_exists = os.path.lexists(paths.single_use_marker)
        report = {
            "schema": "d239-operator-dry-run-pre-usb-v1",
            "gate": "OPERATOR_KIT_DRY_RUN_PRE_USB",
            "status": "PASS",
            "classification": "REAL_OFFLINE_OPERATOR_DRY_RUN",
            "repository": str(REPOSITORY),
            "cwd": str(Path.cwd().resolve()),
            "production_runtime_paths": {
                key: str(value) for key, value in production_paths.__dict__.items()
            },
            "artifact_sha256": artifact_hashes(),
            "modules_loaded": [
                "src.goodix5125_d232_offline",
                "src.goodix5125_d233_backend",
                "src.goodix5125_d235_entrypoint",
            ],
            "pre_usb_fence_count": usb.pre_usb_fence_count,
            "libusb_init_count": usb.libusb_init_count,
            "usb_open_count": usb.usb_open_count,
            "goodix_command_count": usb.goodix_command_count,
            "real_secret_read_count": inputs.real_secret_read_count,
            "synthetic_material_load_count": inputs.material_load_count,
            "synthetic_secret_load_count": inputs.secret_load_count,
            "synthetic_marker_claim_count": facade.synthetic_marker_claim_count,
            "offline_marker_created": offline_marker_exists,
            "live_marker_create_count": 0,
            "source_unseal_count": 0,
            "fprintd_stop_count": facade.fprintd_stop_count,
            "secret_present_in_report": not secret_absent,
            "composed_abort_class": composed.get("abort_class"),
            "composed_command_count": composed.get("command_count"),
            "composed_usb_open_count": composed.get("usb_open_count"),
            "live_usb_execution": "NOT_PERFORMED",
            "operator_path_stages": [
                "repository_and_artifact_gate",
                "real_python_import",
                "production_path_validation",
                "synthetic_preflight_prepare",
                "synthetic_protected_input_load",
                "canonical_pe_reference_gate",
                "production_backend_composition",
                "pre_usb_fence",
                "stop",
                "synthetic_restore_and_offline_report",
            ],
        }
        required = (
            usb.pre_usb_fence_count == 1
            and usb.libusb_init_count == 0
            and usb.usb_open_count == 0
            and usb.goodix_command_count == 0
            and inputs.real_secret_read_count == 0
            and inputs.material_load_count == 1
            and inputs.secret_load_count == 1
            and facade.fprintd_stop_count == 0
            and not offline_marker_exists
            and secret_absent
            and composed.get("command_count") == 0
            and composed.get("usb_open_count") == 0
        )
        if not required:
            report["status"] = "FAIL"
        publish(report_path, report)
        return report


def validate_report(path: Path) -> dict[str, object]:
    report = json.loads(path.read_text(encoding="utf-8"))
    expected_hashes = artifact_hashes()
    valid = (
        report.get("schema") == "d239-operator-dry-run-pre-usb-v1"
        and report.get("gate") == "OPERATOR_KIT_DRY_RUN_PRE_USB"
        and report.get("status") == "PASS"
        and report.get("classification") == "REAL_OFFLINE_OPERATOR_DRY_RUN"
        and report.get("live_usb_execution") == "NOT_PERFORMED"
        and report.get("pre_usb_fence_count") == 1
        and report.get("libusb_init_count") == 0
        and report.get("usb_open_count") == 0
        and report.get("goodix_command_count") == 0
        and report.get("real_secret_read_count") == 0
        and report.get("live_marker_create_count") == 0
        and report.get("source_unseal_count") == 0
        and report.get("secret_present_in_report") is False
        and report.get("artifact_sha256") == expected_hashes
    )
    if not valid:
        raise ValueError("D239 offline operator dry-run report missing, stale, or failed")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    arguments = tuple(sys.argv[1:] if argv is None else argv)
    try:
        if not arguments:
            report = run()
        elif len(arguments) == 2 and arguments[0] == "--report":
            report = run(Path(arguments[1]).resolve())
        elif len(arguments) == 2 and arguments[0] == "--verify-report":
            report = validate_report(Path(arguments[1]).resolve())
        else:
            print("d239_operator_dry_run: invalid arguments", file=sys.stderr)
            return 64
    except (OSError, ValueError, AssertionError) as exc:
        print(f"d239_operator_dry_run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
