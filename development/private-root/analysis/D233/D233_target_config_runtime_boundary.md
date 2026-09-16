# D233 target config `0x90` runtime boundary

The D232 loader is reused. It requires a regular, root-owned, exact-mode `0600`
non-symlink; fixed manifest hash; exactly 224 config bytes; SHA-256
`e1988b1115ade748f6cf5dca8d31aadf99871a7865b97d7ec0971d0da21d4d82`;
valid additive-u16 finalizer; exact DAC order and equality of the four
register/value tuples at offsets 117, 121, 125 and 129.

The local provenance-valid source is
`analysis/D230/work/GoodixExport/rilevamento.pcapng`, capture SHA-256
`50071c0f97fa12d8f3201be015cb632c83687006e2d703c5d3f2a7d9719c184b`.
The existing clean-room offline parser identifies one OUT A0 frame at packet
index 103: control `0x90`, frame length 232, body length 224, pinned body hash
and finalizer `519a`. D233 verified these metadata in memory but did not write
the raw body or read `/var/lib`.

## Future D234 materialization procedure (not executed)

Under a separately authorized root session, D234 must first verify the capture
hash above. It may then reuse
`analysis/D230/tools/offline_census.py::{iter_pcapng_packets,decode_usbpcap,split_bulk_frames}`
to select endpoint `0x01`, host OUT, unique `first_packet_index == 103`, require
wire control `0x90`, and extract only `frame[7:-1]`. Before installation it must
check exact length, pinned SHA-256, finalizer and manifest DAC correlation using
the D232 loader logic. Materialize through an owner-root mode-0600 temporary
regular file in the destination directory, fsync, atomically rename to
`/var/lib/goodix-5125-poc/target-config-90.bin`, fsync the directory, and rerun
the protected loader. Abort on any ambiguity or existing/symlink destination.

No Rockytkg source or raw is permitted. The capture, extracted body and target
store are excluded from the D233 bundle.

`TARGET_CONFIG_RUNTIME_BOUNDARY_READY=yes`
