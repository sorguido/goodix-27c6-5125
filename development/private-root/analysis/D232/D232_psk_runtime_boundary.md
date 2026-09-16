# D232 PSK runtime boundary

## Scope

D232 implements and tests only the protected-input boundary that a separately
authorized D233 source patch could consume. D232 never calls `load_root_psk`,
never opens `/var/lib/goodix-5125-poc/transport-material.bin`, and has no live
transport to which a secret could be sent.

The sole admissible future dataflow is:

```text
legitimately exported material from the original machine
-> /var/lib/goodix-5125-poc/transport-material.bin
-> regular root-owned non-symlink file, exact mode 0600
-> exact 32-byte mutable owned buffer
-> TLS 1.2 PSK suite 0x00a8 / identity Client_identity
-> unconditional zeroization in finally
```

`_open_protected_regular` performs `lstat`, rejects symlinks and non-regular
files, pins owner and exact mode, opens with `O_NOFOLLOW` where available, then
compares inode/device and metadata through `fstat`. `_read_exact_protected`
checks the regular-file size, bounds the read to 33 bytes, accepts exactly 32,
and wipes its temporary buffer on error. `SecretBuffer` owns a mutable buffer;
`close` overwrites it in place and is idempotent.

There is no zero, random, generated, replacement or cross-device fallback. A
missing file, wrong owner/mode, symlink, short/long read or metadata race is a
terminal input-gate failure. The synthetic integration seam publishes a mode
`0600` redacted failure report before any command. It never records the secret.

The test fixture stores only a recipe and constructs a clearly synthetic
32-byte value in test memory. Tests cover exact length, 31/33 bytes, symlink,
successful ownership/mode policy injection, in-place zeroization, report
redaction and exactly-once accepted-backend cleanup. No production secret or
DPAPI material is present in source, fixture, report or bundle.

## D233 boundary

Using the root loader does not authorize D233. A future live implementation
must require a reviewable source patch, human blast-radius acceptance and live
authorization. It must not weaken this boundary or add E0/provisioning.

