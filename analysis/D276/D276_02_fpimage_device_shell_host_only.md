<!-- SPDX-License-Identifier: LGPL-2.1-or-later -->
# D276/02 — rescue FpImageDevice host-only

## Esito

`WIP_CLASSIFICATION=B`: il device shell è salvabile; il standalone subset
rimane proporzionato perché esercita il vero `FpImageDevice` 1.94.5, ma fake e
test richiedevano semantiche asincrone osservabili e token espliciti.

Sono confermati: aspettativa impossibile di `DEACTIVATING` dopo completion
sincrona; cancellazione `ACTIVATING` non collegata al cancellable libfprint;
ownership `GError` non trasferita; launcher che mascherava failure; stato
`INACTIVE` improprio dopo cancel non-quiescente; stale-generation test non
probante; ordering SIGFM non deterministico; policy stage promossa
indebitamente; cancellable nullable; re-arm non idempotente.

Le correzioni collegano il cancellable dell'azione durante activation,
introducono deactivation fake trattenibile, applicano `g_steal_pointer()` o una
copia owned ai confini `GError`, conservano `POISONED` per cancel successivi
all'activation, associano generation agli eventi fake e rendono re-arm
exactly-once. Il launcher usa timeout e restituisce failure se normal o
sanitizer fallisce.

## Limite di verifica

L'ambiente non contiene `flatpak`; inoltre `pkg-config` non trova GLib/GIO/
GObject. Il launcher non può quindi compilare qui. Sono passati soltanto check
statici shell/Python/diff. La milestone resta
`BLOCKED_ENVIRONMENT_VALIDATION`, senza affermazione READY.

## Safety

Il backend è esclusivamente in-memory. Nessun accesso USB, comando sensore,
TLS, secret, fprintd, registrazione VID:PID o mutazione persistente è presente
o è stato eseguito.
