"""D246 executable closure: offline patch application and synthetic tests only."""

from __future__ import annotations

import hashlib
import json
import os
import py_compile
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


def sealed() -> bool:
    backend = (REPOSITORY / SOURCE_FILES[0]).read_text(encoding="utf-8")
    entrypoint = (REPOSITORY / SOURCE_FILES[1]).read_text(encoding="utf-8")
    return (
        'raise D233LiveUnavailable("D233 USB source is hard-disabled")' in backend
        and 'raise D235LiveUnavailable("D235 production live entrypoint is source-sealed")'
        in entrypoint
    )


def run_checked(args: list[str], *, cwd: Path, env=None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}\n{result.stderr}"
        )
    return result


def main() -> int:
    before = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    if not sealed():
        raise RuntimeError("repository live source is not sealed")

    with tempfile.TemporaryDirectory(prefix="d246-executable-closure-") as directory:
        work = Path(directory)
        for name in ("src", "poc", "tests"):
            shutil.copytree(REPOSITORY / name, work / name)
        temporary_sealed_hashes = {
            str(path): digest(work / path) for path in SOURCE_FILES
        }
        (work / "analysis/D230/work/GoodixExport").mkdir(parents=True)
        shutil.copy2(
            REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll",
            work / "analysis/D230/work/GoodixExport/gfusb.dll",
        )
        (work / "analysis/D246").mkdir(parents=True)
        shutil.copy2(
            REPOSITORY / "analysis/D246/d246_runtime_matrix.py",
            work / "analysis/D246/d246_runtime_matrix.py",
        )

        run_checked(
            ["patch", "-p1", "-i", str(REPOSITORY / "analysis/D245/D245_live_unseal.patch")],
            cwd=work,
        )
        run_checked(
            ["patch", "-p1", "-i", str(REPOSITORY / "analysis/D246/D246_d4_continuation.patch")],
            cwd=work,
        )
        for path in SOURCE_FILES:
            py_compile.compile(str(work / path), doraise=True)

        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(work)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        matrix_result = run_checked(
            [sys.executable, "analysis/D246/d246_runtime_matrix.py"],
            cwd=work,
            env=environment,
        )
        matrix = json.loads(matrix_result.stdout)
        if matrix.get("status") != "PASS":
            raise RuntimeError("D246 runtime matrix did not pass")

        run_checked(
            [
                "patch",
                "-R",
                "-p1",
                "-i",
                str(REPOSITORY / "analysis/D246/D246_d4_continuation.patch"),
            ],
            cwd=work,
        )
        run_checked(
            [
                "patch",
                "-R",
                "-p1",
                "-i",
                str(REPOSITORY / "analysis/D245/D245_live_unseal.patch"),
            ],
            cwd=work,
        )
        if temporary_sealed_hashes != {
            str(path): digest(work / path) for path in SOURCE_FILES
        }:
            raise RuntimeError("temporary patch round-trip did not restore sealed source")

    after = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    if before != after or not sealed():
        raise RuntimeError("repository source seal changed during closure")

    print(
        json.dumps(
            {
                "schema": "d246-executable-closure-v1",
                "status": "PASS",
                "matrix": matrix,
                "source_sealed_before": True,
                "source_sealed_after": True,
                "source_hashes_unchanged": True,
                "temporary_patch_round_trip": "PASS_BYTE_EXACT",
                "live_baseline_approval": "PENDING_USER_REVIEW",
                "real_usb_open_count": 0,
                "real_tls_handshake_count": 0,
                "real_d4_send_count": 0,
                "persistent_write_family_count": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
