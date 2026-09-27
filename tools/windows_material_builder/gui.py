# SPDX-License-Identifier: GPL-2.0-or-later
"""English-only Tkinter presentation. All material rules live in the backend."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import webbrowser
from deployment.materials import NAMES
from . import backend, windows, capture_session
from .diagnostics import CATALOG, Failure

GUIDE = 'https://github.com/sorguido/goodix-27c6-5125/blob/main/docs/learning/11_building_your_device_material_bundle.md'


class App:
    def __init__(self, root):
        self.root = root
        root.title('Goodix 5125 Material Builder — Development candidate')
        root.geometry('800x650')
        root.minsize(680, 550)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.sources = self.prerequisites = self.storage = self.run = None
        self.panel = ttk.Frame(root, padding=24)
        self.panel.pack(fill='both', expand=True)
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.report_callback_exception = self.callback_error
        self.welcome()
        root.after(100, self.poll)

    def clear(self, title):
        for child in self.panel.winfo_children():
            child.destroy()
        ttk.Label(self.panel, text=title, font=('', 18, 'bold'), wraplength=720).pack(anchor='w', pady=(0, 16))

    def label(self, text, large=False):
        value = ttk.Label(self.panel, text=text, wraplength=720, justify='left',
                          font=('', 15, 'bold') if large else ('', 11))
        value.pack(anchor='w', pady=8)
        return value

    def button(self, text, command):
        widget = ttk.Button(self.panel, text=text, command=command)
        widget.pack(anchor='w', pady=6)
        return widget

    def detailed_guide(self):
        webbrowser.open(GUIDE)

    def work(self, function, done, failure_code='FINAL_BUNDLE_VALIDATION_FAILED'):
        if self.busy:
            return
        self.busy = True
        def run():
            try:
                result = function()
                self.events.put(('DONE', (done, result)))
            except Failure as failure:
                self.events.put(('ERROR', failure.diagnostic.code))
            except Exception:
                # Never surface arbitrary exception text or traceback locals.
                self.events.put(('ERROR', failure_code))
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == 'DONE':
                    self.busy = False
                    callback, result = value
                    if not self.closing:
                        callback(result)
                elif event == 'ERROR':
                    self.busy = False
                    if not self.closing:
                        self.failure(value)
                elif event == 'RUN':
                    self.run = value
                elif event == 'STATUS' and not self.closing:
                    self.capture_status(value)
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.root.destroy()
            return
        self.root.after(100, self.poll)

    def callback_error(self, *unused):
        self.failure('FINAL_BUNDLE_VALIDATION_FAILED')

    def welcome(self):
        self.clear('Prepare private material for your Linux Goodix driver')
        self.label('Use the original qualified Windows VM and Windows user for your Goodix 27c6:5125 reader. '
                   'This development candidate observes ordinary OEM initialization; it does not modify firmware or factory state.')
        self.label('DO NOT TOUCH THE SENSOR during acquisition.', True)
        self.label('The original USB capture is retained privately, including after success or failure. '
                   'No upload or telemetry. Only Install USBPcap downloads an official installer; '
                   'Open detailed guide opens the public guide in your browser.')
        self.label('Start this app normally, not as administrator. USBPcap will request its own UAC prompt when needed.')
        self.button('Continue', self.begin)
        self.button('Open detailed guide', self.detailed_guide)

    def begin(self):
        self.work(windows.app_directory, self.source_screen, 'PLATFORM_UNSUPPORTED')

    def source_screen(self, storage=None):
        if storage is not None:
            self.storage = storage
        self.clear('Select the OEM source folder')
        self.label('Choose a private local folder containing Goodix_Cache.bin, goodix.dat and gfusb.dll '
                   'from the same original qualified Windows environment.')
        self.source_status = self.label('Goodix_Cache.bin — not selected\ngoodix.dat — not selected\ngfusb.dll — not selected')
        self.button('Select folder', self.select_sources)
        self.button('Open detailed guide', self.detailed_guide)

    def select_sources(self):
        if self.busy:
            return
        name = filedialog.askdirectory(title='Select the private OEM source folder', parent=self.root)
        if not name:
            return
        self.source_status.configure(text='Checking Goodix_Cache.bin, goodix.dat and gfusb.dll…')
        self.work(lambda: backend.validate_sources(Path(name)), self.sources_ready, 'SOURCE_UNSAFE')

    def sources_ready(self, sources):
        self.sources = sources
        self.source_status.configure(text='Goodix_Cache.bin — found and structurally valid\ngoodix.dat — valid\ngfusb.dll — qualified')
        self.button('Continue to USBPcap', self.preflight)

    def preflight(self):
        if self.busy:
            return
        self.clear('USBPcap prerequisites')
        self.label('Checking the driver, USBPcapCMD, pinned version, capture interfaces and reboot state…')
        self.work(lambda: windows.detect(self.storage), self.preflight_ready, 'USBPCAP_NOT_INSTALLED')

    def preflight_ready(self, prerequisites):
        self.prerequisites = prerequisites
        self.clear('USBPcap prerequisites')
        self.label('USBPcap driver — ' + ('running' if prerequisites.driver else 'not ready') +
                   '\nUSBPcapCMD — ' + ('found' if prerequisites.executable else 'missing') +
                   '\nPinned release — ' + (prerequisites.version or 'not installed') +
                   '\nCapture interfaces — ' + str(len(prerequisites.interfaces)) +
                   '\nReboot required — ' + ('yes' if prerequisites.reboot_required else 'no'))
        if prerequisites.executable is None:
            self.label('Install the official USBPcap driver and USBPcapCMD only. Read and accept the installer licenses yourself. '
                       'Leave the optional “Detect USB 3.0” component unchecked. Reboot Windows afterwards.')
            self.button('Install USBPcap', self.install)
        elif prerequisites.reboot_required:
            self.label('Reboot this Windows VM, relaunch the app and select your source folder again. '
                       'The app remembers the reboot requirement and returns to preflight.')
        elif prerequisites.interfaces:
            self.button('Continue to guided VM capture', self.capture_screen)
        else:
            self.label(CATALOG['USBPCAP_INTERFACE_NONE'].text())
        self.button('Recheck', self.preflight)

    def install(self):
        if self.busy:
            return
        self.clear('Install USBPcap')
        self.label('Downloading and verifying the pinned official installer. The interactive UAC installer follows. '
                   'Read its license pages. Install the driver and USBPcapCMD; leave “Detect USB 3.0” unchecked. '
                   'After installation, reboot the VM and relaunch this app.')
        self.work(lambda: windows.install(self.storage), self.preflight_ready, 'USBPCAP_INSTALL_FAILED')

    def capture_screen(self):
        self.clear('Guided Windows VM capture')
        self.label('The VM must already be running. Detach Goodix from the guest through the hypervisor USB menu '
                   'and prevent automatic attachment. Attach no other devices during recording.')
        self.label('DO NOT TOUCH THE SENSOR.', True)
        self.choice = tk.StringVar()
        self.mapped = tk.BooleanVar(value=False)
        options = self.prerequisites.interfaces
        if len(options) == 1:
            self.choice.set(options[0])
            self.label('One capture controller is available: ' + options[0])
        else:
            self.label('Multiple controllers: use the exact root hub previously mapped to Goodix in Device Manager '
                       'and the USBPcap device tree. No controller is selected automatically. '
                       'If mapping is unclear, stop and follow the detailed guide.')
            ttk.Combobox(self.panel, textvariable=self.choice, values=options, state='readonly', width=35).pack(anchor='w')
            ttk.Checkbutton(self.panel, variable=self.mapped,
                            text='I matched this controller to the exact reader using the guide.').pack(anchor='w', pady=8)
            self.button('Show selected controller device tree', self.show_tree)
        self.button('Open detailed guide', self.detailed_guide)
        self.capture_gate = self.label('Press Recheck to verify that Goodix is detached.')
        self.button('Recheck', self.recheck_target)

    def show_tree(self):
        chosen = self.choice.get()
        if chosen not in self.prerequisites.interfaces:
            messagebox.showinfo('Controller mapping', 'Select the controller to inspect first.', parent=self.root)
            return
        def show(text):
            # Display only human-readable upstream device-tree descriptions.
            import re
            lines = re.findall(r'^value .*?\{display=([^}]+)\}', text, re.M)
            messagebox.showinfo('USBPcap device tree', '\n'.join(lines) or 'No attached devices reported.', parent=self.root)
        self.work(lambda: windows.command(self.prerequisites.executable, '--extcap-config', '--extcap-interface', chosen), show)

    def recheck_target(self):
        chosen, mapped = self.choice.get(), self.mapped.get()
        def check():
            windows.choose_interface(self.prerequisites, chosen, mapped)
            windows.require_detached()
        def ready(_):
            self.capture_gate.configure(text='Goodix is absent. Capture will start before the manual-attach instruction.')
            self.button('Start capture', self.start_capture)
        self.work(check, ready, 'TARGET_QUERY_FAILED')

    def start_capture(self):
        if self.busy:
            return
        chosen, mapped = self.choice.get(), self.mapped.get()
        self.cancel.clear()
        self.run = None
        self.clear('Capture in progress')
        self.status_label = self.label('Starting capture. Approve USBPcap’s UAC prompt if shown. Keep Goodix detached.', True)
        self.label('DO NOT TOUCH THE SENSOR. Capture is retained even if cancelled.')
        self.button('Cancel capture', self.cancel.set)
        def update(event, value):
            self.events.put(('RUN', value) if event == 'RUN' else ('STATUS', event))
        self.work(lambda: capture_session.acquire(self.storage, self.prerequisites, chosen, mapped,
                                                  self.cancel, update), self.diagnose, 'CAPTURE_PROCESS_FAILED')

    def capture_status(self, event):
        texts = {'STARTING': 'Starting capture. Keep Goodix detached until the next instruction.',
                 'ATTACH': 'Now attach the Goodix to this Windows VM. Do not touch the sensor.',
                 'SETTLING': 'Goodix was observed. Waiting 30 seconds for ordinary OEM initialization. Do not touch the sensor.',
                 'ANALYZING': 'Capture stopped. Checking identity, CONFIG90 and typed responses…'}
        if event in texts:
            self.status_label.configure(text=texts[event])

    def diagnose(self, result):
        self.run, self.evidence = result
        self.clear('Diagnose and build')
        self.label('Capture container, target identity and APP12509 — valid')
        self.label('\n'.join(name + ' — ' + ('valid and unambiguous' if name in self.evidence.selected else 'failed')
                             for name in ('CONFIG90', 'A2', 'CHIP82', 'A6')))
        if self.evidence.codes:
            details = ScrolledText(self.panel, height=10, wrap='word', font=('', 11))
            details.pack(fill='both', expand=True, pady=8)
            details.insert('1.0', '\n\n'.join(CATALOG[code].text() for code in self.evidence.codes))
            details.configure(state='disabled')
            self.button('Open retained capture folder', self.open_capture)
            self.button('Recheck for a new capture', self.preflight)
            return
        self.label('The next step recovers the existing PSK in memory under your original Windows user, '
                   'checks the A6/cache binding and validates the complete five-file bundle.')
        self.button('Build private bundle', self.build)
        self.button('Open retained capture folder', self.open_capture)

    def build(self):
        self.work(lambda: backend.build(self.sources, self.evidence, self.run, windows.recover_dpapi), self.success)

    def success(self, path):
        self.clear('Private bundle validated')
        self.label('\n'.join(NAMES))
        self.label('Transfer the complete goodix-5125-materials folder privately to Linux\nand place it at:\n\n~/goodix-5125-materials')
        self.label('The raw capture remains in a separate private folder. The Linux installer validates the bundle again.')
        self.button('Open bundle folder', lambda: os.startfile(path))
        self.button('Open retained capture folder', self.open_capture)

    def open_capture(self):
        if self.run:
            os.startfile(self.run / 'raw')

    def failure(self, code):
        self.clear('Stopped — review the diagnostic')
        self.label(CATALOG[code].text())
        if self.run:
            self.label('The original capture has been retained. A retry creates a new run directory.')
            self.button('Open retained capture folder', self.open_capture)
        if self.storage:
            if code.startswith(('SOURCE_', 'FDT_', 'DLL_', 'DPAPI_', 'A6_FDT')):
                self.button('Select source folder again', self.source_screen)
            else:
                self.button('Recheck', self.preflight)
        self.button('Open detailed guide', self.detailed_guide)

    def close(self):
        if self.busy:
            self.closing = True
            self.cancel.set()
        else:
            self.root.destroy()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
