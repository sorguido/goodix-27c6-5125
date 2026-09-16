# D235 pre-seal verification

- `NO_USB_DEVICE_OPEN`: pass.
- `NO_TARGET_ENUMERATION`: pass; selector used synthetic sysfs only.
- `NO_SENSOR_COMMAND`: pass.
- `NO_SUDO`: pass.
- `NO_UDEV_CHANGE`: pass; rule remains absent.
- `NO_FPRINTD_REAL_CHANGE`: pass; injected facades only.
- `NO_REAL_SECRET_READ`: pass.
- `NO_REAL_CONFIG90_READ`: pass.
- `NO_REAL_TLS_WITH_DEVICE`: pass.
- `NO_IAP`: pass.
- `NO_PROVISIONING`: pass.
- `NO_GPL_CODE_COPIED`: pass; composition is local clean-room Python.
- `D235_LIVE_HARD_DISABLED`: pass.
- `USB_OPEN_REACHABLE_FROM_SHIPPED_ENTRYPOINT=no`: pass.
- `ROOT_MANUAL_UPDATED`: pass.
- `GUIDELINES_UNCHANGED`: pass; named path remains absent.
- `README_UNCHANGED`: pass; SHA-256 `e7c2aee68e20755e9b634af9568ca5e76bcb56583edfe2148361a7f6d2fcf79a`.
- `EVIDENCE_UNCHANGED`: pass; SHA-256 `53ae59ca0aac747b8d23dde3c451e6ab140202c6e60841ba29a101310ab74739`.
- `REFERENCES_UNCHANGED`: pass; SHA-256 `d128a4abca918bed570bab0c3dd49a536d173f55bbf385e5fda613f5688d6d6a`.

Terminal decision:
`D235_REAL_LIVE_ENTRYPOINT_OFFLINE_VERIFIED_READY_FOR_D236`.
