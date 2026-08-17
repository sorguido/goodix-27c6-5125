# D244 — audit dello stato iniziale sensore/host

## Reset post-D241

Il codice e il report realmente usati in D241 mostrano soltanto arresto del
nuovo traffico, release dell'interfaccia, close handle, `libusb_exit`,
zeroizzazione del secret, restore di fprintd e signal mask, publication e
source reseal. Non esiste nel recovery post-timeout una chiamata device reset,
USB reset, A2 reset, re-enumeration forzata, power-cycle, protocol close o
Goodix state reset.

```text
D244_POST_D241_DEVICE_STATE_RESET_OBSERVED=false
POST_D241_DEVICE_PROTOCOL_STATE_CARRYOVER=candidate
```

## Cronologia boot host accessibile senza privilegi

`journalctl --list-boots --no-pager`, `/proc/sys/kernel/random/boot_id` e
`/proc/uptime` sono stati letti senza sudo e senza modifiche di sistema. Il
report D241, mtime `2026-08-16 22:35:26 +0200`, ricade nel boot
`704a277d1ed647ec877c90a83b2043d4` (`2026-08-16 21:03:02`–`2026-08-17
00:46:27`). I report D242 e D243, mtime `2026-08-17 22:29:55 +0200` e
`2026-08-17 23:05:17 +0200`, ricadono nel boot successivo
`bc1ec5816f8044528be0e1feeafcc4c7`, iniziato `2026-08-17 21:40:05`.

```text
D244_INITIAL_STATE_CARRYOVER_STATUS=WEAKENED_BY_INTERVENING_BOOT
```

Il reboot host tra D241 e D242 indebolisce la continuità di stato, ma non prova
che l'alimentazione elettrica del sensore sia stata rimossa. D242 e D243 sono
avvenuti nello stesso boot host. La baseline D243 fissata nel kit serve solo a
documentare un boot host diverso nella futura run D244; non è una prova
elettrica del sensore.
