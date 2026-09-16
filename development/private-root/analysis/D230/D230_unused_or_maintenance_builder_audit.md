# D230 unused and maintenance builder audit

The MUST search for a memory-dump builder absent from normal captures is
negative.

The census begins at the three concrete framing builders rather than exported
names or strings.  Every direct call-site was assigned to its PE exception
function range: 61 A0-generic, three A0-no-ack and one B0/TLS call-site.  Static
controls not seen in the recovered capture include mode/DAC/communication-test,
power-management, erase/update and other fixed state operations.  Dynamic
call-sites belong to sensor-mode subtype selection, fixed production-key enums,
the general locked-send abstraction, NOP/no-ack and TLS transport.

Maintenance-only functions A4/F0/F4 were followed separately.  They accept
firmware/control inputs and return status; they do not expose raw bytes read from
a caller-selected flash address.  Their erase/program/reset effects would make
them unusable even if a readback branch were later shown.

The transport indirection at `0x18005ddcc` routes the already classified A0/B0
frames to UMDF pipes.  It does not introduce another command namespace.  No
unreferenced vendor-control builder, CDC path, debug IOCTL serializer, descriptor
table entry, or vtable callback with `address + length → output bytes` was found.

String hits containing “dump” belong to host diagnostic/image logging.  Hits for
production reads resolve to fixed selector APIs.  String absence was not used as
the proof; serializer and consumer dataflows provide the negative evidence.

Residual scope: indirect code not present in the corpus and a future OEM module
could add a builder.  That is a new-primary-evidence reopening condition, not a
reason to repeat the same static search.
