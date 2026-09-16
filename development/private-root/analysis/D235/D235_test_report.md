# D235 offline test report

Command:

```text
python3 -m unittest -v tests.test_d232_offline tests.test_d233_backend tests.test_d233_closure tests.test_d235_entrypoint
```

Result: 53 tests passed, 0 failed, 0 skipped.

The D235 subset covers the sealed shipped entrypoint, production path contract,
synthetic sysfs exact selection, protected input composition, canonical PE gate,
same-object PSK/E4/TLS binding, exact replay, phase-complete result mapping,
checkpoint/final publication, cleanup/restore, negative TLS, signal failure and
offline seam confinement.

All tests used normal user privileges. No target enumeration, real USB API call,
sudo, systemctl operation, udev mutation, protected-store read or device TLS was
performed.
