# D242 — transport contract conclusion

```text
BEFORE_FIX=USB_SEGMENTATION_DIVERGENCE_PROVEN
AFTER_FIX=TRANSPORT_MATCH_VERIFIED_OFFLINE
D241_SERVER_FLIGHT_USB_STATUS=SERVER_FLIGHT_USB_FULLY_TRANSMITTED
```

TLS emission and USB transmission are distinct. In D241, each trace row is
created before `write_frame()`, but the terminal timeout is reached only after
both server-flight `write_frame()` calls return and the subsequent `read_frame()`
raises `UsbTimeout`. `LibusbSystemApi.bulk_out()` rejects a libusb error, and
`ProductionUsbTransport.write_frame()` rejects any completion shorter than the
requested chunk. Thus D241 fully transmitted its own requested `64+26` and
`13` byte segmentation; it did not, however, reproduce Windows segmentation.

D175 proves that the 90-byte ServerHello B0 used two 64-byte OUT submissions
and the 13-byte ServerHelloDone B0 used one 64-byte OUT. Static Windows code at
`0x18005c344` copies at most 64 meaningful bytes into a staging buffer but
always passes `r8b=0x40` to `0x18005a42c`. D241 previously submitted only the
meaningful final suffix. The captured bytes beyond each declared B0 are not
all zero; they are non-semantic staging tail and are not published.

D242 preserves the B0 declared length/tag and initializes only the USB staging
tail with deterministic zeros rather than retaining unrelated buffer content.
Every submitted 64-byte chunk must complete at 64 or
the run fails closed. The closure fixture proves `ServerHello: 64+64`,
`ServerHelloDone: 64`, three submits, three full completions and zero retry.

The scope is not inferred from the two TLS records alone. The D175 capture has
56 bulk OUT submissions across A0 and B0, including continuations, and every
one is 64 bytes. At the already-known command-send call-sites `0x18005d164` and
`0x18005d407`, as at the B0 path, `r8b=0x40` is passed to `0x18005a42c`; that
helper submits the caller-provided length. Therefore:

```text
D242_FIXED64_SCOPE=OEM_COMMON_A0_B0_TRANSPORT_CONTRACT_VERIFIED
```

D242 keeps the logical A0 bytes, declared length, tag/checksum and parser/ACK
semantics unchanged. A synthetic regression submits the logical A0 in one
64-byte zero-initialized staging buffer, parses only its declared frame and
receives the same typed response. This preserves the already live-verified
pre-D1 path rather than treating the staging suffix as new A0 semantics.
