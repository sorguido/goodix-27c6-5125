# D276/04 corrective — integrazione TLS/router/backend host-only

## Stato executor

`OUTCOME=READY`, `EXECUTABLE_CLOSURE=PASS_HOST_ONLY` e
`D276_04_EXECUTOR_STATUS=READY_FOR_AI_PM_REVIEW`. La review finale AI-PM resta
`PENDING`; non viene dichiarato merge-ready.

## Correzione architetturale

L'unico `GoodixDeviceContext` dell'open epoch possiede ora `GoodixUsbRouter`,
`GoodixTlsServer` e `GoodixFpiUsbBackend`, oltre a generation, cancellable e
terminal fence già introdotti da D276/02. I consumer reali del router sono
collegati: A0 resta sul percorso logico non-TLS; B0 valida il solo wrapper
neutrale a quattro byte e passa esclusivamente il payload al Memory-BIO TLS.

OpenSSL resta il provider unico. La state machine distingue handshake,
established/application-data e terminal. Il plaintext è opaco e viene
consegnato borrowed/transfer-none; lo stesso vale per l'output TLS. L'output è
avvolto nel B0 neutrale canonico (`b0`, length LE16, tag additivo) e attraversa
il path OUT dello stesso backend owner. Nessun test raggiunge il submit reale.

Il callback production `FpiUsbTransfer` usa un `PendingTransfer` con generation
catturata al submit. Un callback N-1 non viene attribuito a N e non consuma il
token corrente. Free richiede drain completo. Il cancellable è una ref a quello
dell'activation e l'autorità semantica resta il context.

## Secret e confine API

Il progetto pulisce con `OPENSSL_cleanse` la propria copia subito dopo l'unico
handoff, o al teardown se l'handoff non avviene. Una seconda richiesta fallisce
chiusa. `PROJECT_OWNED_SECRET_COPY_ZEROIZED=true`; non viene fatta alcuna
asserzione sulle copie interne del provider:
`OPENSSL_INTERNAL_SECRET_COPY_ZEROIZATION=NOT_ASSERTED`.

## Evidenza host-only

La suite copre TLS 1.2/cipher effettivi, identity/PSK errate, terminal fence,
handoff/zeroizzazione exactly-once, application record multipli byte-identical,
frammentazione receive, B0→TLS, A0 bypass, stale generation, single reader,
cancel/drain e TLS OUT seam. Compila contro il vero header libfprint 1.94.5 e
`gusb.h` di sistema; lo stub è soltanto link-time e abortisce se un submit reale
viene raggiunto. D276/02 e D276/03 restano regressioni normal+sanitizer.

Il workflow installa Git prima di checkout, usa `fetch-depth: 2`, installa
`libgusb-dev`, esegue due run e gli audit Git/JSON/statici. La conferma Actions
resta `PENDING_AI_PM_NON_GATING`.

Restano invariati tutti i boundary irrisolti: lifetime TLS cross-activation,
quiescenza device dopo cancel arbitrario, timeout, stage enrollment,
orientation, polarity, ppmm ed equivalenza hardware. Nessun live è autorizzato.
`NEXT_PRIMARY_BOUNDARY=AI_PM_REVIEW_AFTER_D276_04`.

## Corrective closure post-merge — generation authority e CI

Il correttivo rende `GoodixDeviceContext` l'unica autorità della generation di
activation. Il context incrementa il proprio token non-zero e lo passa
esplicitamente sia al router sia al backend: il router non genera più epoch e
`goodix_usb_router_cancel()` chiude receive/pending/fence senza mutare il token.
La cancellazione context-side è strutturalmente unica: il terminal fence
cancella TLS e backend, mentre il backend cancella il router una sola volta e in
modo idempotente. Anche gli errori B0/TLS OUT usano lo stesso terminal fence.

La regressione host-only integrata `FpImageDevice` copre activation N con receive
armata, teardown, activation N+1 con una nuova receive, callback tardiva N e
callback corrente N+1. Prova che le generation differiscono, la callback N è
ignorata senza consumare il token N+1, la callback N+1 viene consegnata e il
massimo di receive logiche outstanding resta uno. La regressione router prova
inoltre cancel ripetuto, assenza di mutazione nascosta della generation e
stale/current completion dopo riattivazione, usando soltanto A0 sintetico.

I workflow installano ora `ca-certificates` prima di checkout per D276/04 e
`libssl-dev`/`libgusb-dev` nel regression environment D276/03. Le prove locali
normal e ASAN/UBSAN sono host-only; nessun submit USB reale è raggiunto. Le
GitHub Actions del corrective non sono verificabili dall'executor:
`GITHUB_ACTIONS_CONFIRMATION=NOT_VERIFIED_BY_EXECUTOR` e
`EXECUTABLE_CLOSURE=PENDING_AI_PM_GITHUB_VERIFICATION`.

## Final corrective — cancel request, callback drain e lifetime

Il terminal fence e il drain sono ora stati separati. La richiesta di cancel
non azzera i contatori IN/OUT: ogni token fisico-shaped resta outstanding finché
il callback matching, incluso `G_IO_ERROR_CANCELLED`, rientra e rilascia
esattamente il proprio token. Nessun callback dopo il fence consegna byte o
incrementa le delivery. Una callback stale non corrisponde al token della
nuova generation e non può consumarlo.

`begin_generation()` è ora checked e rifiuta una generation finché IN o OUT non
sono drained. Il backend espone una notifica di drain exactly-once; il context
mantiene la deactivation pending e la completa soltanto dopo l'ultimo callback.
Il cancellable USB è activation-local e distinto da quello dell'azione
libfprint. `can_free()` rende verificabile che il backend non è liberabile prima
del drain. La seam asincrona esplicita mantiene pending sia IN sia OUT fino
all'iniezione sintetica della completion.

I test normal e ASAN/UBSAN provano cancel/drain IN, cancel/drain OUT, free gate,
reject/allow di begin-generation e l'intero ordine N → fence → callback drain →
deactivation → N+1 → stale/current. Il massimo IN fisico-shaped è uno e nessun
submit USB reale viene eseguito. `HOST_ASYNC_IO_DRAIN=PROVEN_HOST_ONLY` non
promuove la quiescenza device-side:
`DEVICE_PROTOCOL_QUIESCENCE=UNRESOLVED`.
