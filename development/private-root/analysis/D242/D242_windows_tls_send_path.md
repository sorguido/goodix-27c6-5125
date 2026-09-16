# D242 — Windows TLS send/BIO static audit

The audit starts at the existing TLS anchors in the canonical `gfusb.dll`
(SHA-256 `904eab1d…c7e2`) rather than performing a generic DLL survey.

```text
mbedTLS send callback wrapper at 0x180058d50
  -> call 0x18005c344 with callback buffer and length
  -> allocate length+4 and build one B0 wrapper
  -> copy the complete callback payload after the 4-byte header
  -> loop offset += 0x40
       copy min(remaining, 0x40) meaningful bytes
       call 0x18005a42c with r8b=0x40
  -> Sleep(10) in ordinary state, Sleep(60) in alternate states
```

The primary D175 flight corroborates one TLS record per callback/B0: a
ServerHello B0 at packets 118/120 and a separate ServerHelloDone B0 at packet
122. No non-TLS ACK, feedback, state write, or extra host command appears
between them. The next device B0 is ClientKeyExchange at packet 125.

The static callback copies one callback buffer into one B0 and does not
coalesce the two observed records. Flush semantics are therefore the return of
each synchronous fixed-chunk send plus its explicit sleep. USB errors propagate
as a negative callback result; no retry loop is present in this send callback.

The bounded scope audit also revisits only the already-known command-send
call-sites `0x18005d164` and `0x18005d407`: both load `r8b=0x40` before calling
the same length-driven `0x18005a42c` helper. Together with all 56 D175 A0/B0
bulk OUT submissions being 64 bytes, this supports a common transport staging
contract. It does not alter the declared A0 length, checksum or response
semantics, which remain properties of the logical frame inside that staging
buffer.
