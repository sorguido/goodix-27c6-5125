# SPDX-License-Identifier: GPL-2.0-or-later
"""Executable closure for the source-sealed D250 AF candidate."""

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
PATCHES = (
    Path("analysis/D245/D245_live_unseal.patch"),
    Path("analysis/D246/D246_d4_continuation.patch"),
    Path("analysis/D250/D250_af_continuation.patch"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sealed(root: Path) -> bool:
    backend = (root / SOURCE_FILES[0]).read_text(encoding="utf-8")
    entrypoint = (root / SOURCE_FILES[1]).read_text(encoding="utf-8")
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
            f"command failed ({result.returncode}): {' '.join(args)}\n"
            f"{result.stdout}\n{result.stderr}"
        )
    return result


def run() -> dict[str, object]:
    before = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    if not sealed(REPOSITORY):
        raise RuntimeError("repository live source is not sealed")

    with tempfile.TemporaryDirectory(prefix="d250-executable-closure-") as directory:
        work = Path(directory)
        for name in ("core", "src", "poc", "tests"):
            shutil.copytree(REPOSITORY / name, work / name)
        sealed_hashes = {str(path): digest(work / path) for path in SOURCE_FILES}
        (work / "analysis/D230/work/GoodixExport").mkdir(parents=True)
        shutil.copy2(
            REPOSITORY / "analysis/D230/work/GoodixExport/gfusb.dll",
            work / "analysis/D230/work/GoodixExport/gfusb.dll",
        )
        for step, names in {
            "D245": ("D245_live_unseal.patch",),
            "D246": ("D246_d4_continuation.patch",),
            "D250": ("D250_af_continuation.patch", "d250_runtime_matrix.py"),
        }.items():
            target = work / "analysis" / step
            target.mkdir(parents=True)
            for name in names:
                shutil.copy2(REPOSITORY / "analysis" / step / name, target / name)

        for patch in PATCHES:
            run_checked(["patch", "--batch", "--forward", "-p1", "-i", str(REPOSITORY / patch)], cwd=work)

        for path in (*SOURCE_FILES, Path("core/post_d4.py"), Path("analysis/D250/d250_runtime_matrix.py")):
            py_compile.compile(str(work / path), doraise=True)

        environment = dict(os.environ)
        environment.update(PYTHONPATH=str(work), PYTHONDONTWRITEBYTECODE="1")
        matrix_result = run_checked(
            [sys.executable, "analysis/D250/d250_runtime_matrix.py"],
            cwd=work,
            env=environment,
        )
        matrix = json.loads(matrix_result.stdout)
        if matrix.get("status") != "PASS":
            raise RuntimeError("D250 runtime matrix did not pass")

        for patch in reversed(PATCHES):
            run_checked(["patch", "--batch", "-R", "-p1", "-i", str(REPOSITORY / patch)], cwd=work)
        if sealed_hashes != {str(path): digest(work / path) for path in SOURCE_FILES}:
            raise RuntimeError("temporary patch round-trip did not restore sealed source")

    after = {str(path): digest(REPOSITORY / path) for path in SOURCE_FILES}
    if before != after or not sealed(REPOSITORY):
        raise RuntimeError("repository source seal changed during closure")

    return {
        "schema": "d250-executable-closure-v1",
        "status": "PASS",
        "matrix": matrix,
        "source_sealed_before": True,
        "source_sealed_after": True,
        "source_hashes_unchanged": True,
        "temporary_patch_round_trip": "PASS_BYTE_EXACT",
        "live_capability": "HARD_DISABLED_PENDING_SEPARATE_USER_AUTHORIZATION",
        "real_usb_open_count": 0,
        "real_tls_handshake_count": 0,
        "real_d4_send_count": 0,
        "real_af_attempt_count": 0,
        "real_af_send_count": 0,
        "retry_count": 0,
        "persistent_write_family_count": 0,
        "terminal_boundary": "STOP_AFTER_AF",
    }


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    if arguments != ["--offline-dry-run"]:
        print("D250_SEPARATE_USER_AUTHORIZATION_REQUIRED", file=sys.stderr)
        return 64
    print(json.dumps(run(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
