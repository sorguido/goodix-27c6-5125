# D232 pre-seal verification

- Python compile: PASS (`src/goodix5125_d232_offline.py`, D232 tests).
- Standard-library test suite: PASS, 18 tests total (6 existing codec tests,
  12 D232 methods containing the required parameterized negative cases).
- Static live/transport scan: no USB/libusb import, `/dev/bus/usb`,
  `libusb_init`, detach, subprocess or socket path in D232 source/tests.
- Hardware/USB commands executed: 0. Real secret store opens: 0.
- Udev rule `/etc/udev/rules.d/70-goodix-5125.rules`: absent and unchanged.
- Project guidelines file: absent.
- README SHA-256 unchanged:
  `e7c2aee68e20755e9b634af9568ca5e76bcb56583edfe2148361a7f6d2fcf79a`.
- EVIDENCE SHA-256 unchanged:
  `53ae59ca0aac747b8d23dde3c451e6ab140202c6e60841ba29a101310ab74739`.
- REFERENCES SHA-256 unchanged:
  `d128a4abca918bed570bab0c3dd49a536d173f55bbf385e5fda613f5688d6d6a`.
- Existing production codec and test hashes unchanged:
  `ef63eb3852e6526722ee12cc5e61e753783007f082819f20218a19fbbe41e3e9`,
  `7997880f232c124ee7ebe688dbd0623e7d2b71ef51752924937f308de6c02274`.
- Root manual updated; standalone patch dry-run: PASS.
- Raw capture, DLL, firmware, target 0x90 body, PSK, DPAPI and biometric data
  are not included in the D232 artifact set.
- Live remains hard-disabled; risk acceptance `not_granted`; authorization `no`.

