# D279/48 — confronto controllato Rockytkg / NBIS / SIGFM

## Aggiornamento post-run — aggregate autentico e classe B

Il gate descritto sotto è stato attraversato con una nuova autorizzazione sulla
baseline completa `36999004b9971f7004aaaa4da85d7c2d1afc79d1`, dopo il
corrective di dependency closure del reduced snapshot. Il summary autentico,
SHA-256 `71ec1922eb97f4804d7e228b09ef3edede04cbc4b3799eff433a418c1efa1ff3`,
passa il validator D279/48.

La review classifica l'esito come
`B_SIGFM_MATERIALLY_OUTPERFORMS_NBIS_ON_SAME_INPUT`: NBIS ha zero frame
Bozorth-computable su 42 sia a R1 sia a R2; SIGFM supera il gate keypoint su
tutti i 42 frame e produce 40/42 score paired-cycle diretti nonzero e almeno
20. Limiti single-session/same-finger e soglia non validata restano invariati.

```text
D279_48_AUTHENTIC_RUN=PASS
D279_48_CLASS=B
EXTRACTOR_DIRECTION=SIGFM
NBIS_PARAMETER_SEARCH=STOP
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
```

La fonte primaria aggregate-only è conservata byte-identica in
`analysis/D279/D279_48_SUCCESS_summary.json`, SHA-256
`71ec1922eb97f4804d7e228b09ef3edede04cbc4b3799eff433a418c1efa1ff3`.
Il JSON di review è derivato e non sostituisce tale fonte.

La preparazione pre-run e il testo del gate sotto restano provenance storica.
La closure corrente è in `D279_48_post_run_sigfm_pivot.md` e
`D279_48_authentic_aggregate_review.json`.

## Esito dello step offline

D279/48 non seleziona ancora un extractor. Ha costruito e chiuso offline
l'esperimento causale minimo che può distinguere il limite del preprocessing
dal limite della strategia biometric feature su un frammento APP12509 80×64.
Il prossimo confine è una sola lettura protetta di ATTEMPT02; non è una run
USB/live e non è attualmente autorizzata.

```text
OUTCOME=READY_AT_PROTECTED_HUMAN_GATE
ADVANCEMENT=MATERIAL_ARCHITECTURAL_EXPERIMENT_AND_EXECUTABLE_CLOSURE
EXECUTABLE_CLOSURE=PASS_OFFLINE
CURRENT_PROTECTED_EVALUATION_AUTHORIZED=false
CURRENT_LIVE_AUTHORIZED=false
PRODUCTION_PATH_CHANGED=false
```

## Cosa fa realmente Rockytkg

L'audit del commit upstream preservato
`227eba219fa9e3fbac5bd59aca79f624f67cd11b` conferma che ChicagoHS/type 12
produce 5120 sample packed 12-bit, trasposti in un raster intermedio
80×64×16-bit (`Rockytkg/src/goodix_capture.c`). Rockytkg acquisisce inoltre
una vera immagine no-finger 80×64 e la mantiene come `img_base`; la forma
persistita misura 10240 byte (`goodix_capture.c`, `goodix_base.c`). Questo
corrobora l'uso di una baseline immagine, ma non prova che il B0 iniziale di
ATTEMPT02 abbia identica semantica OEM.

La parte matcher-independent, compilata direttamente da
`Rockytkg/src/goodix_imgproc.c`, è:

```text
raw u12
→ clamp(2048 + raw - baseline, 0, 4095)
→ flat-field separabile r=12
→ stretch percentile intero 1/99
→ u8 nativo 80×64
```

Il solo stadio SIGFM-specifico aggiunge l'unsharp esatto con boost `0.8f` e
sigma `1.5f`. `goodixgf.c` consegna direttamente la 80×64 finale a SIGFM,
senza resize; `ppmm=500/25.4` non guida SIFT. Il fork materializzato al commit
`7ebe0c809b4d1df3400e84299a4ec4acdea84590` usa SIFT OpenCV, rifiuta meno di
25 keypoint, conserva un oggetto feature separato per ogni pressione accettata
e confronta il probe con i campioni enrollment. Non esegue image fusion.

Il nostro percorso production corrente differisce in modo rilevante soltanto
dopo il decode: converte linearmente u12→u8 e usa NBIS/Bozorth. Protocollo,
TLS, PSK, FDT, USB, lifecycle e sender factory-preserving non sono riaperti né
modificati da D279/48.

## Matrice esatta

- **R0 storico:** summary autentico D279/46 digest-pinned, con signed baseline
  delta, normalizzazione post-delta, resize x2 e NBIS. Non viene riletta la PSK
  per ricostruirlo.
- **R1:** pipeline comune Rockytkg esatta, nativa 80×64, senza enhancement né
  resize. La medesima sequenza di 5120 byte viene consegnata prima a NBIS e poi
  a SIGFM prima del cleanse.
- **R2:** R1 più l'unsharp Rockytkg SIGFM esatto. Lo stesso raster viene dato a
  entrambi gli extractor. R2-NBIS è un controllo causale, non una proposta
  production e non altera l'attribuzione matcher-specifica dell'enhancement.

Per NBIS vengono aggregati minutiae, tier quality-map, frame con feature e
frame con almeno 10 minutiae Bozorth-computable. Per SIGFM vengono aggregati
keypoint e passaggio del gate del fork a 25. Per entrambi vengono calcolati
score same-session su: coppie primary/auxiliary dello stesso ciclo, tutte le
coppie entro primary, entro auxiliary e tutte le coppie cross-role. Ogni
coppia logica viene valutata nelle due direzioni, perché nessun matcher viene
assunto simmetrico. Le soglie di riferimento 40 NBIS e 20 SIGFM sono marcate
esplicitamente come non validate sul target.

Il risultato esporta soltanto count/min/mediana/max e conteggi sopra soglia:
nessun raster, metrica per-frame, minutia, XYT, keypoint, descriptor o template.

## Implementazione e fedeltà

Il preprocessor host-only GPL compila direttamente la sorgente Rocky
preservata. Le macro R1/R2 sono quelle del relativo header. Le override via
environment e i dump a path vengono resi irraggiungibili con sostituzione
compile-time di `getenv()` e link LTO/garbage collection; il binario risultante
non importa `getenv`, `open`, `fopen`, socket, USB o TLS. Una KAT deterministica
fissa i digest R1
`2b586d2f2615f3eff4a2ed20570dace02956b26705edff509a92d6ccc0012b45`
e R2
`2ff834cdef0316b3280d86a46fa75881c50bff3f4240e03dc31c24f6fc4153b3`.

L'helper NBIS chiama `get_minutiae()` e Bozorth dal tree Fedora 44/libfprint
1.94.100 pinned, a 80×64, `ppmm=0` e senza perimeter removal. La conversione
XYT è quella del medesimo `fpi-print.c`. L'helper SIGFM compila direttamente
`sigfm.cpp` preservato contro gli RPM Fedora 44 OpenCV 4.13.0 hash-pinned. Una
KAT SIFT reale produce 33 keypoint e score identico 36 nelle due direzioni.

Il preflight completo ha passato 26 test, build reale dei tre helper, controllo
RPM/source hash, seam source/symbol/runtime, KAT R1/R2 e confronto end-to-end
con 43 raster sintetici. Preprocessor e NBIS hanno inoltre passato ASan/UBSan
nell'SDK con LeakSanitizer disabilitato per l'incompatibilità ptrace del
sandbox. SIGFM/OpenCV ha passato build ed esecuzione reali; non si dichiara un
sanitizer SIGFM, perché l'SDK glibc 2.42 non può caricare le librerie Fedora 44
glibc 2.43 e l'host non dispone del runtime ASan corrispondente. Forzare quel
mix ABI non sarebbe una verifica valida.

## Decisione D279/02 e albero di review

`NBIS_PIPELINE_COMPATIBLE=true` resta una proprietà strutturale. La scelta
NBIS non è annullata prima dell'evidenza comparativa, ma la sua suitability è
`CHALLENGED_BY_TARGET_EVIDENCE_PENDING_CONTROLLED_COMPARISON`.

La review del summary autentico dovrà scegliere una sola classe motivata:

- **A — ROCKY_PREPROCESSING_RESCUES_NBIS:** il limite principale era il
  preprocessing; progettare una successiva integrazione licensing-safe, senza
  inventare altri filtri;
- **B — SIGFM_MATERIALLY_OUTPERFORMS_NBIS_ON_SAME_INPUT:** supersedere D279/02
  sul piano biometrico e progettare il minimo delta extractor, lasciando
  invariato il percorso factory-preserving;
- **C — BOTH_FAIL:** fermare il parameter search e spostare il blocker a monte
  (semantica B0/baseline, derivazione raster o divergenza strutturale);
- **D — BOTH_WORK:** riportare la scelta a dipendenze, manutenzione,
  upstreamability e qualità osservata.

Il dataset contiene un solo contesto sessione/dito, nessun negative control e
nessun different-finger control. Nessuna classe può autorizzare claim FAR/FRR,
accuratezza, soglia production o prontezza fprintd.

## Operator boundary

Il kit
`operator_kit/d279-48-offline-protected-rocky-nbis-sigfm/` costruisce da
snapshot Git dello SHA approvato, verifica manifest completi e dipendenze,
consuma il grant prima della lettura e applica un limite di 20 minuti solo
host-side. Non contiene entry point USB e non avvia fprintd. L'assenza delle
famiglie persistenti note non viene usata come prova di assenza di qualunque
persistenza sensor-side: il sensore non è raggiunto.

Human Gate proposto, one-shot e non riutilizzabile:

```text
Autorizzo esclusivamente una singola
D279_48_ONE_OFFLINE_PROTECTED_ROCKY_NBIS_SIGFM_COMPARISON
sul commit SHA_COMPLETO_APPROVATO, con una sola lettura in memoria del
transport/PSK production per decrittare ATTEMPT02 già catturato, zero USB/live,
zero retry e solo output aggregate-only privo di PSK, plaintext, raster,
minutiae, keypoint, descriptor e template. L'autorizzazione è consumata anche
in caso di failure.
```
