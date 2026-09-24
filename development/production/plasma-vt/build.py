#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build only Fedora's daemon target, with extracted headers; never install/run it."""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REFERENCE = ROOT / 'reference/plasma-login-manager-fedora44-6.7.5'


def run(argv, **kw):
    subprocess.run([str(x) for x in argv], check=True, **kw)


def verify(manifest, directory):
    for line in manifest.read_text().splitlines():
        sha, name = line.split('  ', 1)
        if hashlib.sha256((directory/name).read_bytes()).hexdigest() != sha:
            raise RuntimeError('source_digest_drift: '+name)


def main():
    if os.geteuid() == 0 or len(sys.argv) != 2:
        raise RuntimeError('unprivileged_build_absolute_empty_output_required')
    out = Path(sys.argv[1])
    if not out.is_absolute() or out.is_symlink() or (out.exists() and any(out.iterdir())):
        raise RuntimeError('unsafe_output')
    out.mkdir(exist_ok=True)
    verify(REFERENCE/'SOURCE_SHA256SUMS', REFERENCE)
    verify(HERE/'source.sha256', ROOT)
    headers = ROOT/'GoodixArtifacts/plasma-header-rpms'
    verify(HERE/'headers.sha256', headers)
    src, gen, deps = out/'source', out/'generated', out/'deps'
    shutil.copytree(REFERENCE/'source', src)
    gen.mkdir(); deps.mkdir()
    for name in ('170.patch', '200.patch', 'plasmalogin-environment_file.patch', 'plasmalogin-rpmostree-tmpfiles-hack.patch'):
        with (REFERENCE/'fedora'/name).open('rb') as patch:
            run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=src, stdin=patch)
    with (HERE/'session-vt.patch').open('rb') as patch:
        run(['patch', '--batch', '--fuzz=0', '-p1'], cwd=src, stdin=patch)
    for name in ('SessionVt.h', 'SessionVt.cpp', 'vt-policy.h'):
        shutil.copyfile(HERE/name, src/'src/daemon'/name)
    for line in (HERE/'headers.sha256').read_text().splitlines():
        rpm = headers/line.split('  ', 1)[1]
        data = subprocess.check_output(['rpm2cpio', str(rpm)])
        run(['cpio', '-idm', '--quiet'], cwd=deps, input=data)
    qt = deps/'usr/lib64/qt6'
    values = {
        'CMAKE_INSTALL_FULL_LIBEXECDIR':'/usr/libexec', 'DATA_INSTALL_DIR':'/usr/share/plasmalogin',
        'CMAKE_INSTALL_FULL_SYSCONFDIR':'/etc', 'RUNTIME_DIR':'/run/plasmalogin',
        'STATE_DIR':'/var/lib/plasmalogin', 'SESSION_COMMAND':'/etc/X11/xinit/Xsession',
        'WAYLAND_SESSION_COMMAND':'/etc/plasmalogin/wayland-session',
        'CONFIG_FILE':'/etc/plasmalogin.conf', 'CONFIG_DIR':'/etc/plasmalogin.conf.d',
        'SYSTEM_CONFIG_DIR':'/usr/lib/plasmalogin/plasmalogin.conf.d',
        'LOG_FILE':'/var/log/plasmalogin.log', 'HALT_COMMAND':'', 'REBOOT_COMMAND':'',
    }
    constants = (src/'src/common/Constants.h.in').read_text()
    for key,value in values.items(): constants=constants.replace('@'+key+'@',value)
    if re.search(r'@\w+@', constants): raise RuntimeError('unexpanded_constant')
    (gen/'Constants.h').write_text(constants)
    (gen/'config.h').write_text('#pragma once\nstatic const int PLASMALOGIN_INITIAL_VT = 1;\n')
    run(['/usr/libexec/kf6/kconfig_compiler_kf6', src/'src/common/mainconfig.kcfg',
         src/'src/common/mainconfig.kcfgc', '-d', gen])
    dbus = qt/'bin/qdbusxml2cpp'
    for xml, name, klass in (
        ('org.freedesktop.DisplayManager','displaymanageradaptor','DisplayManager'),
        ('org.freedesktop.DisplayManager.Seat','seatadaptor','DisplayManagerSeat'),
        ('org.freedesktop.DisplayManager.Session','sessionadaptor','DisplayManagerSession')):
        run([dbus,'-a',gen/name,'-i','DisplayManager.h','-l','PLASMALOGIN::'+klass,
             src/'data/interfaces'/(xml+'.xml')])
    for name in ('Manager','Seat','Session'):
        run([dbus,'-p',gen/('Login1'+name),'-i','LogindDBusTypes.h',
             src/'data/interfaces'/('org.freedesktop.login1.'+name+'.xml')])
    include = [gen]+[src/'src'/x for x in ('common','auth','daemon')]
    include += [deps/'usr/include/qt6']+[deps/'usr/include/qt6'/('Qt'+x) for x in ('Core','DBus','Network','Qml','QmlIntegration','Gui')]
    include += [deps/'usr/include/KF6'/x for x in ('KConfig','KConfigCore','KConfigGui','KCoreAddons')]
    flags = ['-std=c++20','-O2','-DNDEBUG','-DQT_NO_DEBUG','-fPIC','-fstack-protector-strong','-D_FORTIFY_SOURCE=3',
             '-ffile-prefix-map='+str(out)+'=/goodix-plasma-build', '-Werror=return-type']
    flags += ['-I'+str(p) for p in include]
    sources = [src/'src/common'/(x+'.cpp') for x in ('SafeDataStream','Session','SocketWriter','VirtualTerminal','MainConfigLoader')]
    sources += [src/'src/auth'/(x+'.cpp') for x in ('Auth','AuthPrompt','AuthRequest')]
    sources += [src/'src/daemon'/(x+'.cpp') for x in ('DaemonApp','Display','DisplayManager','LogindDBusTypes','Greeter','Seat','SeatManager','SocketServer','SessionVt')]
    sources += sorted(gen.glob('*.cpp'))
    # Upstream source includes its moc output; generate those exact includes.
    for source in sources:
        for name in re.findall(r'#include "(moc_[^"]+\.cpp|[^"]+\.moc)"', source.read_text()):
            inp = source if name.endswith('.moc') else source.with_name(name[4:-4]+'.h')
            run([qt/'libexec/moc', *['-I'+str(p) for p in include], inp, '-o', gen/name])
    # Generated DBus/KConfig classes use separately compiled moc files.
    for header in sorted(gen.glob('*.h')):
        if 'Q_OBJECT' in header.read_text():
            moc = gen/('moc_'+header.stem+'.cpp')
            run([qt/'libexec/moc', *['-I'+str(p) for p in include], header, '-o', moc]); sources.append(moc)
    objects = [out/(str(i)+'.o') for i in range(len(sources))]
    # SDK supplies the compiler/C++ headers; native link uses Fedora's ABI.
    compile_script = out/'compile.sh'
    import shlex
    compile_script.write_text('set -eu\n'+''.join(shlex.join(['g++',*flags,'-c',str(s),'-o',str(o)])+'\n' for s,o in zip(sources,objects)))
    run(['flatpak','run','--user','--unshare=network','--filesystem='+str(out),
         '--command=sh','org.freedesktop.Sdk//25.08',compile_script])
    libs = ['/usr/lib64/libQt6'+x+'.so.6' for x in ('Core','DBus','Network','Qml','Gui')]
    libs += ['/usr/lib64/libKF6'+x+'.so.6' for x in ('ConfigCore','ConfigGui','CoreAddons')]
    libs += ['/usr/lib64/libstdc++.so.6','/usr/lib64/libsystemd.so.0']
    run(['gcc','-Wl,--no-undefined','-Wl,-z,relro,-z,now','-o',out/'plasmalogin',*objects,*libs])
    dynamic = subprocess.check_output(['readelf','-d',out/'plasmalogin'],text=True)
    if 'RPATH' in dynamic or 'RUNPATH' in dynamic: raise RuntimeError('unexpected_runtime_path')
    linked = subprocess.check_output(['ldd',out/'plasmalogin'],text=True)
    if 'not found' in linked: raise RuntimeError('missing_runtime_dependency')
    (out/'linked.txt').write_text(linked)
    print('PLASMA_VT_BUILD=PASS DAEMON_EXECUTED=false')


if __name__ == '__main__': main()
