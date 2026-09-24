# -*- coding: utf-8 -*-

'''fprintd mock template

This creates the expected methods and properties of the
net.reactivated.Fprint.Manager object (/net/reactivated/Fprint/Manager)
but no devices.
'''

# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU Lesser General Public License as published by the Free
# Software Foundation; either version 3 of the License, or (at your option) any
# later version.  See http://www.gnu.org/copyleft/lgpl.html for the full text
# of the license.

__author__ = 'Bastien Nocera'
__email__ = 'hadess@hadess.net'
__copyright__ = '(c) 2020 Red Hat Inc.'
__license__ = 'LGPL 3+'

import sys
from gi.repository import GLib
import dbus
import asyncio

from dbusmock import MOCK_IFACE, mockobject

BUS_NAME = 'net.reactivated.Fprint'
MAIN_OBJ = '/net/reactivated/Fprint/Manager'
SYSTEM_BUS = True
IS_OBJECT_MANAGER = False

MAIN_IFACE = 'net.reactivated.Fprint.Manager'
MANAGER_MOCK_IFACE = 'net.reactivated.Fprint.Manager.Mock'

DEVICE_IFACE = 'net.reactivated.Fprint.Device'
DEVICE_MOCK_IFACE = 'net.reactivated.Fprint.Device.Mock'

VALID_FINGER_NAMES = [
    'left-thumb',
    'left-index-finger',
    'left-middle-finger',
    'left-ring-finger',
    'left-little-finger',
    'right-thumb',
    'right-index-finger',
    'right-middle-finger',
    'right-ring-finger',
    'right-little-finger'
]

VALID_VERIFY_STATUS = [
    'verify-no-match',
    'verify-match',
    'verify-retry-scan',
    'verify-too-fast',
    'verify-swipe-too-short',
    'verify-finger-not-centered',
    'verify-remove-and-retry',
    'verify-disconnected',
    'verify-unknown-error'
]

VALID_ENROLL_STATUS = [
    'enroll-completed',
    'enroll-failed',
    'enroll-stage-passed',
    'enroll-retry-scan',
    'enroll-too-fast',
    'enroll-swipe-too-short',
    'enroll-finger-not-centered',
    'enroll-remove-and-retry',
    'enroll-data-full',
    'enroll-disconnected',
    'enroll-unknown-error'
]

def load(mock, parameters):
    fprintd = mockobject.objects[MAIN_OBJ]
    mock.last_device_id = 0
    fprintd.fingers = {}
    mock.loop = asyncio.new_event_loop()

@dbus.service.method(MAIN_IFACE,
                     in_signature='', out_signature='ao')
def GetDevices(self):
    return [(k) for k in mockobject.objects.keys() if "/Device/" in k]

@dbus.service.method(MAIN_IFACE,
                     in_signature='', out_signature='o')
def GetDefaultDevice(self):
    devices = self.GetDevices()
    if len(devices) < 1:
        raise dbus.exceptions.DBusException(
            'No devices available',
            name='net.reactivated.Fprint.Error.NoSuchDevice')
    return devices[0]

@dbus.service.method(MANAGER_MOCK_IFACE,
                     in_signature='sisb', out_signature='s')
def AddDevice(self, device_name, num_enroll_stages, scan_type,
    has_identification=False):
    '''Convenience method to add a fingerprint reader device

    You have to specify a device name, the number of enrollment
    stages it would use (> 0) and the scan type, as a string
    (either 'press' or 'swipe')
    '''

    if scan_type not in ['swipe', 'press']:
        raise dbus.exceptions.DBusException(
            'Invalid scan_type \'%s\'.' % scan_type,
            name='org.freedesktop.DBus.Error.InvalidArgs')

    if num_enroll_stages <= 0:
        raise dbus.exceptions.DBusException(
            'Invalid num_enroll_stages \'%s\'.' % num_enroll_stages,
            name='org.freedesktop.DBus.Error.InvalidArgs')

    self.last_device_id += 1
    path = '/net/reactivated/Fprint/Device/%d' % self.last_device_id
    device_properties = {
        'name': dbus.String(device_name, variant_level=1),
        'num-enroll-stages': dbus.Int32(num_enroll_stages, variant_level=1),
        'scan-type': scan_type
    }

    self.AddObject(path,
                   DEVICE_IFACE,
                   # Properties
                   device_properties,
                   [])

    device = mockobject.objects[path]
    device.fingers = {}
    device.has_identification = has_identification
    device.claimed_user = None
    device.action = None
    device.selected_finger = None
    device.verify_script = []

    return path

@dbus.service.method(MANAGER_MOCK_IFACE,
                     in_signature='o')
def RemoveDevice(self, path):
    # This isn't compatible with hotplugging devices, which fprintd doesn't
    # support yet, but it's meant to remove devices added to the mock for
    # testing purposes.
    if not path:
        raise dbus.exceptions.DBusException(
            'Invalid empty path.',
            name='org.freedesktop.DBus.Error.InvalidArgs')

    self.RemoveObject(path)

@dbus.service.method(DEVICE_IFACE,
                     in_signature='s', out_signature='as')
def ListEnrolledFingers(device, user):
    if user in device.fingers:
        return device.fingers[user]
    raise dbus.exceptions.DBusException(
        'No enrolled prints in device %s for user %s' % (device.path, user),
        name='net.reactivated.Fprint.Error.NoEnrolledPrints')

@dbus.service.method(DEVICE_IFACE,
                     in_signature='s', out_signature='')
def DeleteEnrolledFingers(device, user):
    device.fingers[user] = []

@dbus.service.method(DEVICE_IFACE,
                     in_signature='', out_signature='')
def DeleteEnrolledFingers2(device):
    if not device.claimed_user:
        raise dbus.exceptions.DBusException(
            'Device was not claimed before use',
            name='net.reactivated.Fprint.Error.ClaimDevice')
    if not device.fingers[device.claimed_user]:
        raise dbus.exceptions.DBusException(
            'No enrolled prints in device {} for user {}'.format(device.path,
                device.claimed_user),
            name='net.reactivated.Fprint.Error.NoEnrolledPrints')
    device.fingers[device.claimed_user] = []

@dbus.service.method(DEVICE_IFACE,
                     in_signature='s', out_signature='')
def Claim(device, user):
    if device.claimed_user:
        raise dbus.exceptions.DBusException(
            'Device already in use by %s' % device.claimed_user,
            name='net.reactivated.Fprint.Error.AlreadyInUse')

    device.claimed_user = user

@dbus.service.method(DEVICE_IFACE,
                     in_signature='', out_signature='')
def Release(device):
    if not device.claimed_user:
        raise dbus.exceptions.DBusException(
            'Device was not claimed before use',
            name='net.reactivated.Fprint.Error.ClaimDevice')
    device.claimed_user = None
    device.action = None
    device.selected_finger = None

def can_verify_finger(device, finger_name):
    # We should already have checked that there are enrolled fingers
    if finger_name == 'any':
        return True
    if finger_name in device.fingers[device.claimed_user]:
        return True
    return False

def glib_sleep(timeout):
    waiting = True

    def done_waiting():
        nonlocal waiting
        waiting = False

    GLib.timeout_add(timeout, done_waiting)
    while (waiting):
        GLib.main_context_default().iteration(True)

def device_run_script(device, result, done):
    if result == 'MOCK: quit':
        sys.exit(0)

    # Emit signal
    device.EmitSignal(DEVICE_IFACE, 'VerifyStatus', 'sb', [
                        result,
                        done
                      ])

@dbus.service.method(DEVICE_IFACE,
                     in_signature='s', out_signature='')
def VerifyStart(device, finger_name):
    if not device.claimed_user:
        raise dbus.exceptions.DBusException(
            'Device was not claimed before use',
            name='net.reactivated.Fprint.Error.ClaimDevice')
    if device.claimed_user not in device.fingers:
        raise dbus.exceptions.DBusException(
            'No enrolled prints for user \'%s\'' % device.claimed_user,
            name='net.reactivated.Fprint.Error.NoEnrolledPrints')
    if not finger_name:
        raise dbus.exceptions.DBusException(
            'Invalid empty finger_name.',
            name='org.freedesktop.DBus.Error.InvalidArgs')
    if not can_verify_finger(device, finger_name):
        raise dbus.exceptions.DBusException(
            'Finger \'%s\' not enrolled.' % finger_name,
            name='org.freedesktop.DBus.Error.Internal')
    if device.action:
        raise dbus.exceptions.DBusException(
            'Action \'%s\' already in progress' % device.action,
            name='net.reactivated.Fprint.Error.AlreadyInUse')
    device.action = 'verify'

    if finger_name == 'any' and not device.has_identification:
        finger_name = device.fingers[device.claimed_user][0]
    device.selected_finger = finger_name
    # Needs to happen after method return
    GLib.idle_add(device.EmitSignal,
                  DEVICE_IFACE, 'VerifyFingerSelected', 's', [
                    device.selected_finger
                  ])

    error = None
    base_delay = 0
    while device.verify_script is not None and len(device.verify_script) > 0:
        result, done, timeout = device.verify_script.pop(0)

        # We stop when "timeout >= 0 and done"
        if result == 'MOCK: no-prints':
            # Special case to change return value of DBus call, ignores timeout
            error = dbus.exceptions.DBusException(
                'No enrolled prints for user \'%s\'' % device.claimed_user,
                name='net.reactivated.Fprint.Error.NoEnrolledPrints')

        elif timeout < 0:
            # Negative timeouts mean emitting before the DBus call returns
            device_run_script(device, result, done)
            glib_sleep(-timeout)

        else:
            # Positive or zero means emitting afterwards the given timeout
            base_delay += timeout
            GLib.timeout_add(base_delay,
                             device_run_script,
                             device,
                             result,
                             done)

            # Stop processing commands when the done flag is set
            if done:
                break

    if error:
        raise error

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='sb', out_signature='')
def EmitVerifyStatus(device, result, done):
    if (not device.action) or (device.action != 'verify'):
        raise dbus.exceptions.DBusException(
            'Cannot send verify statuses when not verifying',
            name='org.freedesktop.DBus.Error.InvalidArgs')
    if result not in VALID_VERIFY_STATUS:
        raise dbus.exceptions.DBusException(
            'Unknown verify status \'%s\'' % result,
            name='org.freedesktop.DBus.Error.InvalidArgs')
    device.EmitSignal(DEVICE_IFACE, 'VerifyStatus', 'sb', [
                          result,
                          done
                      ])

@dbus.service.method(DEVICE_IFACE,
                     in_signature='', out_signature='')
def VerifyStop(device):
    if device.action != 'verify':
        raise dbus.exceptions.DBusException(
            'No verification to stop',
            name='net.reactivated.Fprint.Error.NoActionInProgress')
    device.action = None
    device.selected_finger = None

@dbus.service.method(DEVICE_IFACE,
                     in_signature='s', out_signature='')
def EnrollStart(device, finger_name):
    if finger_name not in VALID_FINGER_NAMES:
        raise dbus.exceptions.DBusException(
            'Invalid finger name \'%s\'' % finger_name,
            name='net.reactivated.Fprint.Error.InvalidFingername')
    if not device.claimed_user:
        raise dbus.exceptions.DBusException(
            'Device was not claimed before use',
            name='net.reactivated.Fprint.Error.ClaimDevice')
    if device.action:
        raise dbus.exceptions.DBusException(
            'Action \'%s\' already in progress' % device.action,
            name='net.reactivated.Fprint.Error.AlreadyInUse')
    device.action = 'enroll'

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='sb', out_signature='')
def EmitEnrollStatus(device, result, done):
    if (not device.action) or (device.action != 'enroll'):
        raise dbus.exceptions.DBusException(
            'Cannot send enroll statuses when not enrolling',
            name='org.freedesktop.DBus.Error.InvalidArgs')
    if result not in VALID_ENROLL_STATUS:
        raise dbus.exceptions.DBusException(
            'Unknown enroll status \'%s\'' % result,
            name='org.freedesktop.DBus.Error.InvalidArgs')
    device.EmitSignal(DEVICE_IFACE, 'EnrollStatus', 'sb', [
                          result,
                          done
                      ])
    # FIXME save enrolled finger?

@dbus.service.method(DEVICE_IFACE,
                     in_signature='', out_signature='')
def EnrollStop(device):
    if device.action != 'enroll':
        raise dbus.exceptions.DBusException(
            'No enrollment to stop',
            name='net.reactivated.Fprint.Error.NoActionInProgress')
    device.action = None

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='sas', out_signature='')
def SetEnrolledFingers(device, user, fingers):
    '''Convenience method to set the list of enrolled fingers.

    The device_path is the return value from AddDevice(), and the
    array of fingers must only contain valid finger names.

    Returns nothing.
    '''

    for k in fingers:
        if k not in VALID_FINGER_NAMES:
            raise dbus.exceptions.DBusException(
                'Invalid finger name \'%s\'' % k,
                name='org.freedesktop.DBus.Error.InvalidArgs')

    device.fingers[user] = fingers

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='', out_signature='s')
def GetSelectedFinger(device):
    '''Convenience method to get the finger under verification

    Returns the finger name that the user has selected for verifying
    '''
    if not device.selected_finger:
        raise dbus.exceptions.DBusException(
            'Device is not verifying',
            name='net.reactivated.Fprint.Error.NoActionInProgress')

    return device.selected_finger

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='', out_signature='b')
def HasIdentification(device):
    '''Convenience method to get if a device supports identification

    Returns whether identification is supported.
    '''

    return device.has_identification

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='a(sbi)', out_signature='')
def SetVerifyScript(device, script):
    '''Convenience method to set the verification script.

    After VerifyStart is called, signal results will be sent in order after
    a certain timeout declared in seconds. The array contains each
    'result' followed by the 'done' argument for VerifyStatus, and the
    amount of time to wait before each signal is sent.

    Returns nothing.
    '''

    device.verify_script = script

@dbus.service.method(DEVICE_MOCK_IFACE,
                     in_signature='s', out_signature='')
def SetClaimed(device, user):
    if user == '':
        device.claimed_user = None
    else:
        device.claimed_user = user
