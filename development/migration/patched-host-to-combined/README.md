# Migrazione PC patchato → combined candidate: decisione sui materiali

**OUTCOME=HUMAN_REQUIRED — GATE=MATERIAL_MANIFEST_COMPATIBILITY_DECISION**

L'inventario privilegiato è stato consegnato dall'Utente con stderr vuoto e
riesaminato. Non ripetere `inventory.py`, `su` o pkexec. Il prossimo passo non
è ancora installare o disinstallare: è risolvere un'incompatibilità fra il
loader del runtime installato e quello della candidate canonica.

## Risultato della review

- D285 possiede esattamente il selettore sudo di guido; PAM, wrapper e drop-in
  corrispondono ai pin software dello state. Rimane il PASS sudo umano già
  attestato, senza una nuova autenticazione eseguita dall'AI.
- La selezione è D285/90 → D293/95 → login-early/96, aggiornato da login-three.
  KScreenLocker e B5 sono integrazioni aggiuntive. I due runtime D297 sono
  presenti ma non selezionati; lo state D297/02 `ACTIVE` è stale.
- È presente un file template, root:root, 521555 byte. I cinque file dei
  materiali sono presenti con owner/mode attesi. Si tratta di metadata,
  non di una validazione dei contenuti o del riconoscimento.
- I tre `UNKNOWN_STOP` sono limiti di profondità in archivi storici sotto
  `/var/lib/goodix-5125-poc`; questi alberi restano interamente preservati.
  Non sono errori di lettura del selettore o dei backup necessari.

La review dettagliata, le classificazioni degli oggetti e i limiti sono in
[INVENTORY-REVIEW.md](INVENTORY-REVIEW.md). Il report ricevuto rimane nel path
indicato dall'Utente; non è stato copiato nel repository o in una candidate.

## Blocker verificato offline

Il runtime login-three conserva quattro sorgenti del loader D293
`e61fce313794922a2dab156a1b38a8ddc5837f19`. Quel loader accetta un manifest di
2305 byte tramite pin SHA-256. Il manifest di analisi D232 **già versionato e
non segreto** coincide con quel pin, ma ha uno schema diverso dal v1 canonico.
La prova con il vero loader corrente lo rifiuta `PROTECTED_CONTENT`, prima
di leggere transport o CONFIG90. Un v1 interamente sintetico, portato alla
stessa dimensione, supera invece il parser: la lunghezza non è il problema.

Il manifest installato ha anch'esso 2305 byte. La sua identità con D232 è una
forte inferenza da metadata, provenance software e storia, **non una lettura
o un hash del file protetto attuale**. Non si dichiara verificato il contenuto
host. Il manager controlla presenza/permessi dei materiali, non lo schema:
`PROTECTED_MATERIAL_READY=true` non può chiudere questo blocker.

## Decisione necessaria prima di continuare

Proposta: autorizzare la **preparazione offline di una transizione locale,
reversibile, del solo `target-material-manifest.json` al formato canonico**,
con esecuzione futura esclusivamente umana dopo un nuovo handoff completo.
Il delta consentito sarebbe precisamente:

1. Qualificare nella futura transazione umana l'originale atteso; STOP su
   differenze, senza stampare i suoi valori. Derivare i campi del v1 soltanto
   da evidenze già qualificate, mai da valori inventati.
2. Conservare l'originale root-only e sostituire atomicamente il solo manifest;
   recovery simmetrico dell'originale in caso di mancata installazione o FAIL.
3. Lasciare invariati i quattro file binari del bundle, staging, template,
   firmware e stato del sensore. Nessuna lettura di segreti reali da parte AI,
   nessuna esportazione, provisioning, nuova PSK o nuova acquisizione.
4. Completare apply/rollback degli overlay, prove sintetiche e riproduzione
   della candidate canonica, quindi fermarsi prima di ogni operazione host.

Questa proposta **non è implementata né autorizzata** dal task attuale.
L'alternativa da decidere esplicitamente è una candidate privata con loader
storico: conserverebbe anche il manifest, ma cambierebbe la candidate
canonica richiesta e richiederebbe nuova provenance e validazione.
Reintrodurre tacitamente i quattro loader, indebolire il parser o importare
un nuovo bundle non sono correzioni ordinarie di questa migrazione.

La conferma serve perché il prompt Utente §0 dice «materiale protetto restano
intoccabili» e §4 vieta di leggerne il contenuto; [AGENTS.md](../../../AGENTS.md)
§6.2 impone il gate per «accesso o manipolazione di […] protected material non
già specificamente autorizzati», e §6.4 per un cambio materiale di strategia.
Questo caso non soddisfa né il caso A (ripetere il medesimo inventario non
risolve il formato), né il caso B del prompt (migrazione pronta alla live).
Si esplicita quindi il gate aggiuntivo, senza dichiarare uno dei due esiti
falsamente chiuso. Non è una richiesta di approvazione dello SHA.

## Verifiche di sviluppo già eseguite

Da utente normale, dalla root Git; sono prove offline, non comandi operatore:

```bash
python3 -I -B development/migration/patched-host-to-combined/test_inventory.py -v
production/check-source.sh
development/private-root/libfprint-driver/tests/run_goodix_runtime_inputs_test.sh
bash development/migration/patched-host-to-combined/check-material-boundary.sh
python3 -I -B deployment/managed-install/test_offline.py ManagedInstallContract.test_status_repairs_legacy_runtime_root_and_reports_material_readiness -v
```

Risultati: inventario 8/8; source checks PASS; loader 27/27 normale e 27/27
ASan/UBSan; due verifiche sul confine formato in entrambi i modi; test mirato
del manager 1/1. Il test del manager dimostra soltanto il controllo metadata
con file sintetici, non una candidate installata sul PC. LeakSanitizer non è
supportato nell'ambiente SDK/ptrace: è disabilitato come nella suite materiali
esistente; nessun claim di leak-check. Nessuna libreria USB/daemon viene
collegata dal nuovo test. Il fixture D232 privato non entra nel build canonico.

Apply/rollback, build completa della candidate, riproducibilità, simulazione
della migrazione e piano live finale restano da completare dopo la decisione.
Le prove candidate precedenti conservano il loro scope storico: non sono
state riattribuite al PC post-migrazione. Finché questo gate resta aperto,
conservare lo stack attuale e non eseguire gli uninstall storici.
