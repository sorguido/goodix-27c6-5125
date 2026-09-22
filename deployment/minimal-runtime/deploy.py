#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""R3-A: own only the private library directory and one environment drop-in."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import stat
import subprocess
import sys
import tempfile

BUILD_COMMIT = "c5df71772b3ade7cf3d1ea2d418a65e0ab75b1f6"
RUNTIME = Path("/usr/local/lib64/goodix-27c6-5125")
DROPIN = Path("/etc/systemd/system/fprintd.service.d/90-goodix-5125-runtime.conf")
UNIT = "fprintd.service"
LIBRARIES = ("libfprint-2.so.2.0.0",) + tuple(
    f"libopencv_{part}.so.413" for part in ("core", "features2d", "flann", "imgproc"))
LINKS = {"libfprint-2.so.2": "libfprint-2.so.2.0.0", "libfprint-2.so": "libfprint-2.so.2"}
CONFIG = f"[Service]\nEnvironment=LD_LIBRARY_PATH={RUNTIME}\n".encode()
STATE = "installation.json"
REPO = Path(__file__).resolve().parents[2]
ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LC_ALL": "C"}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def run(*args):
    result = subprocess.run(args, env=ENV, text=True, capture_output=True)
    require(result.returncode == 0,
            f"{' '.join(args)}: {result.stderr.strip() or result.stdout.strip() or result.returncode}")
    return result.stdout.strip()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=64 * 1024 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, "rb") as stream:
        st = os.fstat(stream.fileno())
        require(stat.S_ISREG(st.st_mode) and st.st_size <= limit, f"invalid regular file: {path}")
        data = stream.read(limit + 1)
    require(len(data) <= limit, f"file too large: {path}")
    return data


def safe_directory(path):
    require(path.is_absolute(), f"non-absolute directory: {path}")
    for item in (path, *path.parents):
        st = item.lstat()
        require(stat.S_ISDIR(st.st_mode) and st.st_uid == os.geteuid()
                and not st.st_mode & 0o022, f"unsafe directory: {item}")


def no_sensor():
    # Read sysfs identity only; no USB handle or sensor command is opened.
    for device in Path("/sys/bus/usb/devices").iterdir():
        if (device / "idVendor").exists():
            vendor = (device / "idVendor").read_text().strip().lower()
            product = (device / "idProduct").read_text().strip().lower()
            require((vendor, product) != ("27c6", "5125"), "disconnect the Goodix reader from the VM")


def machine_gate():
    run("systemd-detect-virt", "--vm", "--quiet")
    require(os.geteuid() == 0, "run manually with sudo inside the VM")
    no_sensor()


def property_value(name):
    return run("systemctl", "show", UNIT, "--property=" + name, "--value")


def install_preflight():
    os_info = Path("/etc/os-release").read_text()
    require(re.search(r'^ID="?fedora"?$', os_info, re.M) and
            re.search(r'^VERSION_ID="?44"?$', os_info, re.M), "Fedora 44 required for this candidate")
    require(os.uname().machine == "x86_64", "x86_64 required")
    run("rpm", "-V", "fprintd")
    require(property_value("FragmentPath") == "/usr/lib/systemd/system/fprintd.service",
            "vendor fprintd unit required")
    commands = re.findall(r"path=([^ ;]+)", property_value("ExecStart"))
    require(commands == ["/usr/libexec/fprintd"], "stock fprintd ExecStart required")
    for name in property_value("DropInPaths").split():
        if name == str(DROPIN):
            continue
        require(name.startswith("/usr/lib/systemd/system/"), f"foreign service override: {name}")
        run("rpm", "-qf", name)
    environment = shlex.split(property_value("Environment"))
    for variable in environment:
        require(not variable.startswith("LD_PRELOAD="), "foreign preload environment")
        if variable.startswith("LD_LIBRARY_PATH="):
            require(variable == f"LD_LIBRARY_PATH={RUNTIME}" and DROPIN.exists()
                    and CONFIG == read_regular(DROPIN), "foreign library environment")
    require("LD_LIBRARY_PATH" not in property_value("UnsetEnvironment"), "library environment is unset by another override")
    active = property_value("ActiveState")
    require(active in ("active", "inactive"), f"service state requires review: {active}")
    require(run("getenforce") == "Enforcing", "SELinux Enforcing required; do not change enforcement for this test")
    return active


def git(*args):
    return run("git", "-c", f"safe.directory={REPO}", "-C", str(REPO), *args)


def load_payload(build):
    require(build.is_absolute() and build.resolve() == build, "use a real absolute build directory")
    for directory in (build / "runtime", build / "runtime/licenses"):
        require(directory.is_dir() and directory.resolve() == directory, f"unexpected directory link: {directory}")
    require(git("branch", "--show-current") == "development", "development required")
    require(not git("status", "--porcelain"), "clean committed checkout required")
    install_commit = git("rev-parse", "HEAD")
    provenance = read_regular(build / "build-provenance.txt", 65536)
    require(provenance.startswith(f"SOURCE_COMMIT={BUILD_COMMIT}\nBUILD_MODE=normal\n".encode()),
            "expected the retained normal R2 build, not a rebuild or sanitizer output")
    critical = ["libfprint-driver", "reference/libfprint-fedora44-1.94.100",
                "Rockytkg/libfprint/libfprint/sigfm", "production/build-inner.sh",
                "production/build-support", "production/minimal-runtime/build.sh",
                "production/check-source.sh", "production/source-files.tsv",
                "production/source-files.sha256", "production/host-test-only-symbols.txt"]
    git("diff", "--exit-code", BUILD_COMMIT, "HEAD", "--", *critical)
    checksum_text = read_regular(build / "runtime/SHA256SUMS", 4096).decode()
    checksums = {}
    for line in checksum_text.splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  ([a-zA-Z0-9_.-]+)", line)
        require(match is not None and match[2] not in checksums, "invalid runtime checksum manifest")
        checksums[match[2]] = match[1]
    require(set(checksums) == set(LIBRARIES), "unexpected runtime library set")
    payload = {name: read_regular(build / "runtime" / name) for name in LIBRARIES}
    require(all(digest(payload[name]) == checksums[name] for name in LIBRARIES), "runtime digest mismatch")
    for name, target in LINKS.items():
        require((build / "runtime" / name).is_symlink() and
                os.readlink(build / "runtime" / name) == target, f"unexpected link: {name}")
    for name in ("OpenCV-LICENSES.txt", "source-files.tsv", "source-files.sha256"):
        payload[name] = read_regular(build / "runtime" / name)
    for name in ("GPL-2.0-or-later", "LGPL-2.1-or-later", "GPL-3.0-or-later", "Apache-2.0"):
        payload[f"licenses/{name}.txt"] = read_regular(build / "runtime/licenses" / f"{name}.txt")
    payload["LICENSING_AND_PROVENANCE.md"] = read_regular(REPO / "docs/LICENSING_AND_PROVENANCE.md")
    payload["build-provenance.txt"] = provenance
    payload["SHA256SUMS"] = checksum_text.encode()
    # Keep the exact inverse with the installed runtime, independent of later Git changes.
    payload["deploy.py"] = read_regular(Path(__file__).resolve())
    payload["uninstall.sh"] = read_regular(Path(__file__).with_name("uninstall.sh"))
    return payload, install_commit


def inspect_owned():
    safe_directory(RUNTIME)
    state = json.loads(read_regular(RUNTIME / STATE, 65536))
    require(state.get("schema") == 1 and state.get("build_commit") == BUILD_COMMIT,
            "unknown installation metadata; retain files for review")
    require(state.get("previous_service") in ("active", "inactive") and
            type(state.get("created_dropin_directory")) is bool, "invalid previous state")
    expected = set(state["files"]) | set(LINKS) | {STATE, "licenses"}
    actual = {str(p.relative_to(RUNTIME)) for p in RUNTIME.rglob("*")}
    require(actual == expected, "runtime contains missing or unowned files; retain for review")
    for name, checksum in state["files"].items():
        require(not Path(name).is_absolute() and ".." not in Path(name).parts, "invalid owned path")
        st = (RUNTIME / name).lstat()
        require(st.st_uid == os.geteuid() and not st.st_mode & 0o022, f"installed metadata drift: {name}")
        require(digest(read_regular(RUNTIME / name)) == checksum, f"installed file drift: {name}")
    for name, target in LINKS.items():
        require(os.readlink(RUNTIME / name) == target, f"installed link drift: {name}")
    if DROPIN.exists() or DROPIN.is_symlink():
        require(read_regular(DROPIN) == CONFIG, "project drop-in has drifted; retain for review")
    return state


def remove_owned_files(state, own_dropin=True):
    require(own_dropin or not (DROPIN.exists() or DROPIN.is_symlink()),
            "concurrent foreign drop-in: service left stopped; retained runtime for review")
    # Missing drop-in is allowed for recovery after an interrupted removal.
    if own_dropin and (DROPIN.exists() or DROPIN.is_symlink()):
        require(read_regular(DROPIN) == CONFIG, "drop-in collision during recovery; retained runtime")
        DROPIN.unlink()
    run("systemctl", "daemon-reload")
    restore_service(state)
    # Retain the inverse and previous state until the vendor service is restored.
    shutil.rmtree(RUNTIME)
    if state["created_dropin_directory"]:
        try:
            DROPIN.parent.rmdir()
        except OSError:
            # A new foreign file must be preserved, never recursively removed.
            if not DROPIN.parent.is_dir() or not any(DROPIN.parent.iterdir()):
                raise


def restore_service(state):
    if state["previous_service"] == "active":
        no_sensor()
        run("systemctl", "start", UNIT)


def install(payload, install_commit, previous_service):
    safe_directory(RUNTIME.parent)
    safe_directory(DROPIN.parent if DROPIN.parent.exists() else DROPIN.parent.parent)
    if RUNTIME.exists() or RUNTIME.is_symlink():
        state = inspect_owned()
        require(DROPIN.exists(), "incomplete install: use saved uninstall before reinstalling")
        require(all(state["files"].get(name) == digest(data) for name, data in payload.items()),
                "different payload: use saved uninstall first")
        print("R3_INSTALL=ALREADY_INSTALLED")
        return
    require(not DROPIN.exists() and not DROPIN.is_symlink(), "project drop-in path already occupied")
    state = {"schema": 1, "build_commit": BUILD_COMMIT, "install_commit": install_commit,
             "previous_service": previous_service, "created_dropin_directory": not DROPIN.parent.exists(),
             "files": {name: digest(data) for name, data in payload.items()}}
    stage = Path(tempfile.mkdtemp(prefix=".goodix-5125-stage-", dir=RUNTIME.parent))
    published = False
    stopped = False
    own_dropin = False
    try:
        for name, data in payload.items():
            destination = stage / name
            destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            destination.write_bytes(data)
            destination.chmod(0o755 if name == "uninstall.sh" else 0o644)
        for name, target in LINKS.items():
            (stage / name).symlink_to(target)
        (stage / STATE).write_text(json.dumps(state, indent=2) + "\n")
        (stage / STATE).chmod(0o600)
        stage.chmod(0o755)
        no_sensor()
        stopped = True
        run("systemctl", "stop", UNIT)
        stage.rename(RUNTIME)
        published = True
        DROPIN.parent.mkdir(mode=0o755, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".goodix-5125-dropin-", dir=DROPIN.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(CONFIG)
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            os.link(temporary, DROPIN)  # Atomic publication; never overwrite a collision.
            own_dropin = True
        finally:
            Path(temporary).unlink()
        run("restorecon", "-RF", str(RUNTIME), str(DROPIN))
        run("systemctl", "daemon-reload")
        # Leave stopped: the user explicitly starts stock fprintd in the R3 load check.
        print(f"R3_INSTALL=PASS BUILD_SOURCE_COMMIT={BUILD_COMMIT} INSTALL_COMMIT={install_commit}")
        print("FPRINTD=STOPPED_READY_FOR_MANUAL_LOAD_CHECK FEDORA_COMPONENTS_REPLACED=NONE")
    except BaseException:
        if published:
            # Only this transaction's files exist here; restore before propagating failure.
            remove_owned_files(state, own_dropin=own_dropin)
        elif stopped:
            restore_service(state)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def uninstall():
    safe_directory(RUNTIME.parent)
    safe_directory(DROPIN.parent if DROPIN.parent.exists() else DROPIN.parent.parent)
    if not RUNTIME.exists() and not RUNTIME.is_symlink():
        require(not DROPIN.exists() and not DROPIN.is_symlink(), "orphan drop-in: retain for review")
        print("R3_UNINSTALL=ALREADY_ABSENT")
        return
    state = inspect_owned()
    run("systemctl", "stop", UNIT)
    remove_owned_files(state)
    print("R3_UNINSTALL=PASS FEDORA_VENDOR_FILES_UNCHANGED=true MATERIALS_TEMPLATES_PRESERVED=true")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("build_output", nargs="?", type=Path)
    args = parser.parse_args()
    require((args.action == "install") == (args.build_output is not None), "install needs a build directory; uninstall takes none")
    machine_gate()
    def interrupted(_signum, _frame):
        raise KeyboardInterrupt("deployment interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    safe_directory(RUNTIME.parent)
    # Advisory lock on the existing directory: serialize our transactions without a new host file.
    fd = os.open(RUNTIME.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if args.action == "install":
            active = install_preflight()
            payload, commit = load_payload(args.build_output)
            install(payload, commit, active)
        else:
            uninstall()  # No Fedora version/RPM/build-source check: inverse works after an update.
    finally:
        os.close(fd)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("R3_DEPLOY=INTERRUPTED inspect the reported recovery result before continuing", file=sys.stderr)
        sys.exit(130)
    except (RuntimeError, OSError, ValueError, KeyError) as error:
        print(f"R3_DEPLOY=FAIL {error}", file=sys.stderr)
        sys.exit(1)
