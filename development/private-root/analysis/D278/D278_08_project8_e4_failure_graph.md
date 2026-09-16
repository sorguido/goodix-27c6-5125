# D278/08 — grafo di failure E4 project 8

## Legenda

- `[V]`: verificato staticamente nel disassembly canonico.
- `[O]`: osservato nella capture target D255/D256.
- `[I]`: inferito da stringhe, ABI o semantica della routine.
- `-->`: call o continuazione diretta.
- `==>`: propagazione del return.
- `~~>`: edge con possibile effetto persistente.

## Provenienza del sender

```text
[V] selector 0x1805783c0 == 8 @ 0x18006abec
  --> [V] gfUpdatefirmware 0x180064a18 @ 0x18006ac4c
        | conditional inner updater 0x1800656f4 @ 0x180064b39
        |   ~~> A4 Clear App @ 0x180065bb7
        |   ~~> firmware update 0x18006bb3c @ 0x180065e3d/0x180065e93
        ` return to init_MCU @ 0x18006ac51
  --> [V] continuation @ 0x18006adc0
  --> [V] production process 0x18003c348 @ 0x18006ae04
  --> [V] production_check_psk_is_valid 0x18003b514 @ 0x18003c499
        | selector 0xbb020003 loaded @ 0x18003b77b
  --> [V] production_read_specific_data 0x18003cc90 @ 0x18003b780
  --> [V] production_read_mcu 0x18003c7f4 @ 0x18003ce0c
        | r8=0x0e, r9=0x02, body_len=8
        | ACK timeout=500 ms, typed timeout=1000 ms
  --> [V] generic sender 0x18005c148 @ 0x18003c94c
  --> [O] E4 body 03 00 02 bb 00 00 00 00 @ D255/D256 frames 54/56/58
```

Tutti gli edge che riconciliano il branch project 8 con il sender E4 sono
diretti. Il vecchio “indirect edge” era una continuazione post-return non
inclusa nel sottografo D278/07.

```text
EDGE_CLASSIFICATION=DIRECT_CALL
```

## Branch di successo

```text
first E4 generic send returns nonzero
  --> validate typed response shape/length/status
  --> compare returned specific data/hash @ 0x18003b870
  --> production_check_psk_is_valid returns 0
  --> production process returns 0
  --> init_MCU continues success @ 0x18006ae92
  --> _DeviceInit may proceed to init_FP
```

La capture D255/D256 corrobora solo questo lato: E4 è seguito dall'A2
sensor-only successful-path. Non osserva alcun ramo di failure.

## Branch di failure e retry

```text
production_read_mcu / first check
  |
  +-- generic send returns zero
  |     --> one immediate E4 retry @ 0x18003c9a1
  |           +-- zero     ==> 0xffdffffd
  |           `-- nonzero  --> typed validation
  |
  +-- malformed/short typed response ==> e.g. 0xffeffffa
  +-- typed execution status nonzero  ==> 0xffdffffc
  `-- specific-data/hash mismatch     ==> nonzero
          |
          ==> production_read_specific_data
          ==> production_check_psk_is_valid
          ==> production process
                  |
                  +-- check count < 2 --> repeat whole check once
                  |                      (new E4; same inner bound)
                  |
                  `-- two checks failed
                         ~~> production_write_key 0x18003cfd8
                               @ call 0x18003c5eb
                              ~~> production_write_mcu 0x18003d8e0
                                   @ call 0x18003d6fd
                                  ~~> E0 first send @ 0x18003da2a
                                      +-- zero --> one E0 retry
                                      |           @ 0x18003dabf
                                      `-- result
                                           |
                                           +-- success --> post-write
                                           |              production_check_psk_is_valid
                                           |              @ 0x18003c6fb
                                           |                +-- success --> process returns 0
                                           |                `-- failure --> next write iteration
                                           `-- failure --> next write iteration
```

Bounds locali:

```text
initial transport failure: 2 E4 sends/check * 2 checks = max 4 E4 sends
initial semantic failure:  1 E4 send/check  * 2 checks = max 2 E4 sends
write fallback failure:    2 E0 sends/write * 2 writes = max 4 E0 sends
post-write revalidation:   1 check/successful write * 2 writes
whole-process E4 maximum:  8 on transport failure; 4 on semantic failure
```

Non è stato trovato uno sleep fra i retry locali. Il fallback E0 e le
successive revalidation E4 sono raggiunti prima che l'errore possa risalire a
`init_MCU`.

## Propagazione terminale se anche il fallback fallisce

```text
[V] production_write_key last nonzero result
  ==> [V] production process returns nonzero @ 0x18003c7ea
  ==> [V] init_MCU stores result @ 0x18006ae09
  ==> [V] init_MCU error return @ 0x18006ae89..0x18006b0e7
  ==> [V] _DeviceInit same error @ 0x18001e11b..0x18001e252
  ==> [V] InitThread normal failure loop @ 0x180014ebe..0x180014f07
        +-- retry index < N_CFG --> whole _DeviceInit again
        |                         --> A8, updater, E4 become reachable again
        `-- exhausted/fatal      --> init failure/exit
```

`N_CFG` è un byte configurabile a offset `0x45a`; il valore target non è nel
corpus. Il bound strutturale è verificato, il numero runtime è unknown.

## Taglio di safety

```text
PRE-E4:  gfUpdatefirmware può raggiungere A4/update        persistent risk=true
E4:      read specific data 0xbb020003                     persistent risk=false
FAIL-E4: production_write_key -> production_write_mcu/E0   persistent risk=true

PROJECT8_E4_FAILURE_PATH_FACTORY_PRESERVING=false
LINUX_SAFE_E4_RECOVERY_CANDIDATE=false
```

Il grafo descrive raggiungibilità OEM, non un'autorizzazione all'esecuzione.
Nessuna live, retry USB, E0, A4, reset o update è autorizzata.

## Annotazione degli edge del grafo

La tabella seguente rende espliciti indirizzi, tipo, condizione e classe di
evidenza di ogni edge disegnato sopra. Gli attributi aggiuntivi, inclusi return
value e rischio persistente, sono nella tabella CSV machine-readable.

| ID | Source | Target | Tipo | Condizione | Evidenza |
|---|---|---|---|---|---|
| E002 | `0x18006ac4c` | `0x180064a18` | direct call | project 8 | VERIFIED |
| E003 | `0x180064b39` | `0x1800656f4` | direct call | updater state 1 | VERIFIED |
| E004 | `0x18006ad78` | `0x18006adc0` | conditional branch | updater return nonzero e non-special | VERIFIED |
| E005 | `0x18006ae04` | `0x18003c348` | direct call | post-updater gate | VERIFIED |
| E006 | `0x18003c499` | `0x18003b514` | direct call | initial check index < 2 | VERIFIED |
| E007 | `0x18003b77b` | `0x18003b780` | data flow | selector `0xbb020003` | VERIFIED |
| E008 | `0x18003b780` | `0x18003cc90` | direct call | specific-data read | VERIFIED |
| E009 | `0x18003ce0c` | `0x18003c7f4` | direct call | parameters valid | VERIFIED |
| E010 | `0x18003c94c` | `0x18005c148` | direct call | first E4 send | VERIFIED |
| E011 | `0x18003c9a1` | `0x18005c148` | direct call | first sender return zero | VERIFIED |
| E012 | `0x18003c9ed` | `0x18003cc90` | return propagation | second sender return zero | VERIFIED |
| E013 | `0x18003cb28` | `0x18003cc90` | return propagation | typed shape/length invalid | VERIFIED |
| E014 | `0x18003cb9d` | `0x18003cc90` | return propagation | typed status nonzero | VERIFIED |
| E015 | `0x18003cfbb` | `0x18003b514` | return propagation | read result nonzero | VERIFIED |
| E016 | `0x18003ba48` | `0x18003c348` | return propagation | read/hash validation nonzero | VERIFIED |
| E017 | `0x18003c53d` | `0x18003c43e` | bounded loop | first check failed; index < 2 | VERIFIED |
| E018 | `0x18003c5eb` | `0x18003cfd8` | direct call | two initial checks failed | VERIFIED |
| E019 | `0x18003d6fd` | `0x18003d8e0` | direct call | write payload packaged | VERIFIED |
| E020 | `0x18003da2a` | `0x18005c148` | direct call | first E0 send | VERIFIED |
| E021 | `0x18003dabf` | `0x18005c148` | direct call | first E0 sender return zero | VERIFIED |
| E022 | `0x18003d8c1` | `0x18003c5f0` | return propagation | write-key returns | VERIFIED |
| E031 | `0x18003c6fb` | `0x18003b514` | direct call | write-key returned zero | VERIFIED |
| E023 | `0x18003c7ea` | `0x18006ae09` | return propagation | process terminates | VERIFIED |
| E024 | `0x18006ae89` | `0x18006b0e7` | return propagation | process nonzero | VERIFIED |
| E025 | `0x18001e11b` | `0x18001e252` | return propagation | init_MCU nonzero | VERIFIED |
| E026 | `0x180014ebe` | `0x180014f07` | bounded loop | normal error; retry < `N_CFG` | VERIFIED |
| E027 | `0x180065bb7` | `0x18005c148` | direct call | updater Clear App branch | VERIFIED |
| E028 | `0x180065e3d` | `0x18006bb3c` | direct call | firmware update required | VERIFIED |
| E029 | `0x18003b870` | `0x18007ba10` | direct call | typed response valid | VERIFIED |
| E030 | `0x18006ae92` | `0x18006aeb0` | direct continuation | process return zero | VERIFIED |
