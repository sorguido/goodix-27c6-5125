# SPDX-License-Identifier: GPL-2.0-or-later
"""Exact RPM metadata for the two software PAM post-images; no host writes."""
import subprocess

QUERY = '[%{FILENAMES}\t%{FILESIZES}\t%{FILEMTIMES}\t%{FILEDIGESTS}\t%{FILEMODES:octal}\t%{FILEUSERNAME}\t%{FILEGROUPNAME}\t%{FILECAPS}\t%{FILEVERIFYFLAGS}\t%{FILEFLAGS}\n]'


def qualify(host, contract):
    for path, row in contract.items():
        if host.run('/usr/bin/rpm','-q','--whatprovides','--qf','%{NAME}',path) != row['package']:
            raise RuntimeError('pam_package_owner_drift')
        rows = [line.split('\t') for line in host.run('/usr/bin/rpm','-q','--qf',QUERY,row['package']).splitlines()]
        found = [r for r in rows if r[0] == path]
        if found != [row['rpm']]: raise RuntimeError('pam_package_metadata_drift')


def verify_host(host, contract):
    qualify(host, contract)
    # Match the real manager's path-scoped check, without ignoring execution errors.
    result = subprocess.run(['/usr/bin/rpm','-V','plasma-login-manager'],capture_output=True,
                            text=True,timeout=60,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    if result.returncode not in (0,1) or result.stderr:
        raise RuntimeError('package_verify_unavailable')
    lines = [line for line in result.stdout.splitlines() if line.split() and
             line.split()[-1] == '/usr/lib/pam.d/plasmalogin']
    if lines:
        print('PLASMALOGIN_RPM_VERIFY='+repr(lines),flush=True)
        raise RuntimeError('postimage_package_verification_failed')


def check_files(tx, state):
    for path, row in tx.plan['packages'].items():
        expected = row['rpm']
        data, label = tx.fs.read(path,0o644,65536)
        info = tx.fs.info(path)
        if (len(data) != int(expected[1]) or tx.hash(data) != expected[3] or
                info['mtime_ns'] != int(expected[2])*1000000000 or
                label != state['files'][path]['label']):
            raise RuntimeError('postimage_package_attributes_drift')


def mtime(contract, path):
    return int(contract[path]['rpm'][2])*1000000000
