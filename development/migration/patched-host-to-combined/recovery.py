#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Saved, removal-only recovery. Human root console: /run/gx."""
import fcntl
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

SHORT = '/run/gx'
BACKUP = '/var/lib/goodix-27c6-5125-migration'
SHORT_BYTES = (b'#!/usr/bin/bash\nexec /usr/bin/python3 -I -B '
               b'/var/lib/goodix-27c6-5125-migration/recovery.py\n')
PATHS = ('deployment/managed-install/root-transaction.sh',
         'production/polkit/deploy.py', 'production/sudo/rules.py')
DIRECTORIES = ('', '/deployment', '/deployment/managed-install', '/production',
               '/production/polkit', '/production/sudo')
ENV = {'PATH':'/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL':'C', 'PYTHONDONTWRITEBYTECODE':'1',
       'SUDO_USER':'guido', 'SUDO_UID':'1000', 'SUDO_GID':'1000'}


def sources(repo):
    data = {name:(Path(repo)/name).read_bytes() for name in PATHS}
    name=PATHS[0]
    old=b'repo=$(git -C "$here" rev-parse --show-toplevel)'
    if data[name].count(old) != 1: raise RuntimeError('manager_recovery_adapter_drift')
    # Uninstall does not consume repo. Remove ONLY the unused Git-root lookup,
    # and restrict dispatch to the original uninstall for the known installer.
    # All ownership, policy, PAM and template preservation checks stay intact.
    data[name]=data[name].replace(old,b'repo=')
    marker=b'set -euo pipefail\n'
    if data[name].count(marker) != 1: raise RuntimeError('manager_recovery_header_drift')
    data[name]=data[name].replace(marker,marker+b'[[ $# == 2 && $1 == --root-uninstall && $2 == guido ]] || exit 2\n')
    return data


def restore(tx, invoke):
    tx.state()  # Validate saved sources and backups before any host operation.
    if tx.fs.info('/var/lib/goodix-27c6-5125-managed/state') is not None:
        manager=str(tx.fs.root / (BACKUP+'/recovery/'+PATHS[0]).lstrip('/'))
        invoke(['/usr/bin/bash',manager,'--root-uninstall','guido'])
    # Refuses partial/foreign candidate residue. Never deletes it speculatively.
    return tx.rollback()


def main():
    if os.geteuid()!=0 or len(sys.argv)!=1:
        print('RECOVERY=STOP operator_root_required',file=sys.stderr); return 2
    here=Path(__file__).resolve().parent
    if here != Path(BACKUP):
        print('RECOVERY=STOP use_saved_command_/run/gx',file=sys.stderr); return 2
    spec=importlib.util.spec_from_file_location('migration',here/'migration.py')
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    fs=m.Files(); lock=os.open('/run',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        tx=m.Migration(fs,m.Host())
        def invoke(command): subprocess.run(command,check=True,env=ENV)
        print('RECOVERY='+restore(tx,invoke))
        return 0
    except (OSError,ValueError,RuntimeError,KeyError,subprocess.SubprocessError):
        print('RECOVERY=STOP preserve_console_and_backups_do_not_force',file=sys.stderr); return 1
    finally: os.close(lock); fs.close()

if __name__=='__main__': sys.exit(main())
