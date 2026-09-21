#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Unprivileged kernel TIOCSCTTY check on newly allocated PTYs, never real VTs."""
import errno
import fcntl
import os
import termios

assert os.geteuid() != 0
master, slave = os.openpty()
ready_r, ready_w = os.pipe()
hold_r, hold_w = os.pipe()
owner = os.fork()
if owner == 0:
    os.close(ready_r); os.close(hold_w)
    os.setsid()
    fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    os.write(ready_w, b'1')
    os.read(hold_r, 1)
    os._exit(0)
os.close(ready_w); os.close(hold_r)
try:
    assert os.read(ready_r, 1) == b'1'
    contender = os.fork()
    if contender == 0:
        os.setsid()
        try:
            fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
            os._exit(1)
        except OSError as error:
            if error.errno != errno.EPERM: os._exit(2)
        fresh_master, fresh_slave = os.openpty()
        fcntl.ioctl(fresh_slave, termios.TIOCSCTTY, 0)
        os._exit(0)
    _, status = os.waitpid(contender, 0)
    assert os.waitstatus_to_exitcode(status) == 0, status
finally:
    os.write(hold_w, b'1'); os.waitpid(owner, 0)
    for fd in (master, slave, ready_r, hold_w): os.close(fd)
print('KERNEL_PTY_TIOCSCTTY=PASS occupied_EPERM_free_SUCCESS argument_zero_no_steal')
print('REAL_VT_OPENQRY_HANDOFF=NOT_TESTED_REAL_TARGET_LIVE_PENDING')
