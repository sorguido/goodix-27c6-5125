# SPDX-License-Identifier: GPL-2.0-or-later
"""Safe structured diagnostics shared by the GUI, CLI and tests.

Never interpolate exception text, paths, payloads or device-specific digests.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Diagnostic:
    code: str
    observed: str
    possible_cause: str
    action: str

    def text(self):
        return (f'{self.code}\nObserved: {self.observed}\n'
                f'Possible cause: {self.possible_cause}\nAction: {self.action}')


RETRY = ('Detach Goodix through the hypervisor UI. Start a new capture first, '
         'then attach it once. DO NOT TOUCH THE SENSOR. Keep the previous capture.')
CATALOG = {}


def _add(code, observed, cause, action):
    CATALOG[code] = Diagnostic(code, observed, cause, action)


for kind, filename in [('GOODIX_CACHE', 'Goodix_Cache.bin'), ('FDT', 'goodix.dat'),
                       ('DLL', 'gfusb.dll')]:
    _add(f'SOURCE_{kind}_MISSING', f'{filename} is missing.',
         'The selected folder may be incomplete.',
         'Select a private folder containing all three original OEM files.')
for code, observed, cause, action in [
    ('SOURCE_UNSAFE', 'An input is not a stable regular file in a real local directory.',
     'A link, reparse point, shared path or concurrent change may be involved.',
     'Copy ordinary files into a private local folder and select it again.'),
    ('SOURCE_CACHE_INVALID', 'Goodix_Cache.bin has an invalid size or entropy trailer.',
     'The file may be incomplete or from an incompatible OEM context.',
     'Re-copy Goodix_Cache.bin from the original qualified Windows context.'),
    ('DLL_NOT_QUALIFIED', 'gfusb.dll does not satisfy the qualified producer identity/layout.',
     'A different OEM package may have supplied this DLL.',
     'Use the unchanged gfusb.dll from the qualified 1.1.125.14 OEM package.'),
    ('FDT_INVALID_SIZE', 'goodix.dat is not exactly 13,520 bytes.',
     'The selected file may be incomplete or incompatible.', 'Re-copy goodix.dat from the qualified OEM context.'),
    ('FDT_CRC_INVALID', 'goodix.dat fails CRC-32/MPEG-2 validation.',
     'The bytes may have changed or may use an unsupported layout.', 'Re-copy goodix.dat without editing it.'),
    ('FDT_SEED_MISSING', 'The qualified FDT seed region is all zero.',
     'The cache may not contain initialized material.', 'Use the existing qualified OEM environment and re-copy goodix.dat.'),
    ('DPAPI_RECOVERY_FAILED', 'DPAPI did not return a valid existing 32-byte PSK.',
     'The user or Windows context may differ from the original OEM context.',
     'Run the app normally as the original Windows user. Do not run as SYSTEM or another administrator.'),
    ('PLATFORM_UNSUPPORTED', 'This workflow requires a normal, unelevated Windows user session.',
     'The app may be running on another platform or under an elevated account.',
     'Launch the GUI normally inside the original qualified Windows VM.'),
    ('USBPCAP_NOT_INSTALLED', 'USBPcap driver or USBPcapCMD was not found.',
     'USBPcap may not be installed completely.', 'Press Install USBPcap, complete the official installer and reboot the VM.'),
    ('USBPCAP_VERSION_UNSUPPORTED', 'The installed USBPcap components do not match the pinned release.',
     'Another USBPcap release may be installed.', 'Use the official pinned 1.5.4.0 release; do not substitute an arbitrary executable.'),
    ('USBPCAP_HASH_OR_PROVENANCE_FAILURE', 'The official installer could not be downloaded and verified.',
     'Network access, provenance or file integrity may be unavailable.',
     'Check connectivity to the official release source and retry Install USBPcap. Do not execute an unverified file.'),
    ('USBPCAP_INSTALL_FAILED', 'The interactive installer did not complete successfully.',
     'UAC may have been cancelled or installation may have failed.',
     'Review the official installer result, then recheck prerequisites.'),
    ('USBPCAP_REBOOT_REQUIRED', 'A verified post-install reboot has not been observed.',
     'USBPcap filters may not yet be active.', 'Reboot the Windows VM, relaunch this app and recheck prerequisites.'),
    ('USBPCAP_INTERFACE_NONE', 'No USBPcap capture interface is available.',
     'The filter driver may need a reboot or repair.', 'Reboot the VM and recheck. If still absent, repair the official installation.'),
    ('USBPCAP_INTERFACE_AMBIGUOUS', 'A unique mapped capture controller has not been established.',
     'Several root hubs may be available.',
     'Map the exact reader in Device Manager and the USBPcap device tree as described in the guide. Select that observed controller, or stop.'),
    ('TARGET_PRESENT_BEFORE_CAPTURE', 'Goodix is already present in the guest before capture readiness.',
     'Automatic passthrough may have attached it early.',
     'Detach Goodix through the hypervisor UI, prevent automatic attachment, then press Recheck.'),
    ('TARGET_QUERY_FAILED', 'The present-device query did not complete reliably.',
     'Windows device enumeration may be unavailable.', 'Resolve the Windows device-query error before starting another capture.'),
    ('CAPTURE_PROCESS_FAILED', 'The capture process did not start, remain ready, or stop cleanly.',
     'UAC, capture permissions, storage or USBPcap may have failed.',
     'Stop and retain the raw capture. Report the safe lifecycle.txt status fields from the run diagnostics folder; '
     'do not infer clean shutdown from a readable capture or start an automatic retry.'),
    ('CAPTURE_CANCELLED', 'Capture was cancelled; the raw recording was retained.',
     'The acquisition may be incomplete.', RETRY),
    ('CAPTURE_EMPTY', 'The capture contains no packets.',
     'The target may not have attached to the selected controller.', RETRY),
    ('CAPTURE_TRUNCATED_OR_INVALID', 'The capture has unsupported, truncated or inconsistent records.',
     'Capture may have stopped abruptly or exceeded supported bounds.', RETRY),
    ('TARGET_NOT_OBSERVED', 'No qualified target USB descriptor was observed.',
     'The selected controller or attachment timing may be wrong.', RETRY),
    ('TARGET_WRONG_IDENTITY', 'The observed reader identities or attachment epochs are not a single 27c6:5125 stream.',
     'Another device or a repeated attachment may be included.', RETRY),
    ('APP_ID_MISSING_OR_WRONG', 'The capture does not contain a unique exact APP12509 response.',
     'Initialization may be incomplete or firmware may be incompatible.', RETRY),
    ('A6_FDT_MISMATCH', 'The captured A6 response does not match the selected goodix.dat.',
     'The files and capture may describe different reader states or devices.',
     'Re-copy goodix.dat from the same qualified Windows environment and make a fresh single-attach capture.'),
    ('TRANSPORT_BUILD_FAILED', 'The qualified transport derivation did not complete.',
     'Crypto dependencies or recovered inputs may be invalid.',
     'Verify the cryptography dependency and original OEM source files; never substitute a PSK.'),
    ('MANIFEST_BUILD_FAILED', 'The canonical ten-field manifest could not be constructed.',
     'Required validated evidence may be incomplete.', 'Keep the capture and resolve its diagnostics before building again.'),
    ('FINAL_BUNDLE_VALIDATION_FAILED', 'The final bundle failed installer-equivalent content or publication checks.',
     'Material binding, directory inventory or destination state may be inconsistent.',
     'Keep the inputs and capture. Use a new output run and resolve validation errors; never overwrite an existing bundle.'),
]:
    _add(code, observed, cause, action)

for name, description in [('CONFIG90', '224-byte CONFIG90 body'), ('A2', '3-byte A2 response'),
                          ('CHIP82', '4-byte chip82 response'), ('A6', '64-byte A6 response')]:
    _add(name + '_MISSING', f'The target was identified, but no valid {description} was found.',
         'Capture may have started too late or ended before OEM initialization completed.',
         RETRY + ' If offered, choose Retry with extended initialization window, then Recheck and Start capture. '
         'This provides one 60-second attempt, without guaranteeing that the missing evidence will appear. '
         'If unavailable or still incomplete, stop and report the diagnostic code.')
    _add(name + '_AMBIGUOUS', f'Multiple distinct valid candidates exist for the {description}.',
         'The recording may combine incompatible initialization evidence.', RETRY)


_add('CONFIG90_MISSING', 'The target was identified, but no valid 224-byte CONFIG90 body was found.',
     'The required OEM trigger or state may differ from passive attachment; its provenance remains incomplete.',
     'Stop and retain the capture. Report CONFIG90_MISSING for provenance review. '
     'Do not repeat attachment or extend the wait to try to force CONFIG90.')


# Closed vocabulary: never accept free-form stderr, paths or exception strings.
LIFECYCLE_STAGES = frozenset('STARTING READY STOP_RECEIVED CONTROL_EOF CONTROL_INVALID '
    'Q_REQUESTED Q_INJECTED CHILD_WAIT CHILD_WAIT_TIMEOUT RAW_FLUSH RAW_FLUSHED '
    'CLEANUP_Q CLEANUP_TERMINATE STOPPED FAILED EOF STATUS_INVALID '
    'PARENT_STOP_SENT PARENT_WAIT_TIMEOUT PARENT_STATUS_TIMEOUT PARENT_TERMINATE'.split())


def safe_lifecycle_status(value):
    if value in LIFECYCLE_STAGES:
        return True
    import re
    match = re.fullmatch(r'(CHILD_EXIT|WORKER_EXIT)=(-?[0-9]{1,10})', value)
    return bool(match and -2147483648 <= int(match[2]) <= 4294967295)


class Failure(RuntimeError):
    def __init__(self, code):
        self.diagnostic = CATALOG[code]
        super().__init__(self.diagnostic.text())


def require(condition, code):
    if not condition:
        raise Failure(code)
