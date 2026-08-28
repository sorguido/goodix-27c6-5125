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
