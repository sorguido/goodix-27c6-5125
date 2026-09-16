# D232 exact OEM replay contract

## Closed sequence

```text
E4 -> A2 #1 -> 0x82 -> A6 -> A2 #2 -> 0x70
   -> 0x80(0220) -> 0x80(0236) -> 0x80(0238) -> 0x80(023a)
   -> 0x90 -> D1(d7) -> TLS 1.2 PSK
```

The state machine must execute all nodes in exactly this order. It may not
skip, minimize, reorder or retry a node. D4 is forbidden because it is not in
the recovered target cold-start. E0/A4/F0/F4/IAP/ClearApp/provisioning are not
members of the command vocabulary.

## Field provenance

| class | D232 meaning | examples |
| --- | --- | --- |
| `BYTE_PINNED_CONSTANT` | exact bytes approved by the target evidence | E4 selector; both A2 bodies `0114`; 0x70 body `1400`; register addresses; D1 body/control seed |
| `DERIVED_FROM_TARGET_READ_ONLY_INPUT` | target response or target-specific local material, validated by length/hash | E4 validator, 0x82/A6 responses, DAC values, 224-byte 0x90 body |
| `TRANSPORT_DERIVED` | serializer output only | LE lengths, A0/B0 outer tag, additive inner checksum |
| `SESSION_DERIVED` | synthetic TLS session state in D232; real session state only in a future authorized D233 | TLS randoms/transcript/records |
| `SECRET_RUNTIME_INPUT` | 32-byte legitimate PSK loaded at runtime and zeroized | TLS PSK; never fixture target material |

Dynamic target data is not embedded in source as a replacement constant. The
target-material loader validates a provenance manifest and a separately stored
0x90 body. Synthetic tests use a different, explicitly synthetic manifest.

## Response discipline

E4, A2, 0x82, A6 and 0x90 require their documented ACK plus typed response.
0x70 and each 0x80 require only the exact correlated ACK. D1 requires the next
frame class to be B0/TLS ClientHello, not a permissive A0 response. TLS accepts
only synthetic-oracle success for suite 0x00a8 and identity `Client_identity`.

Timeout, wrong echo/status, short/extra data, wrong target hash, malformed OTP,
wrong DAC order, config mismatch, unexpected re-enumeration, TLS alert, Bad
Record MAC or any ambiguous completion causes terminal STOP. The next phase is
never issued. Application retry count is zero and automatic reset/recovery is
forbidden.

## Safety interpretation

All pre-D1 commands belong to the exact OEM path classified operationally
factory-preserving by D231. This contract does not assert an absolute resident
NVM nonmutation proof. D232 contains no hardware transport and grants no live
authorization.

