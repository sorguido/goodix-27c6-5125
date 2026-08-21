<!-- SPDX-License-Identifier: GPL-2.0-or-later -->
# Linee Guida di Progetto Goodix 27c6:5125 per AI

**Versione 2.2 — Revisione 21 agosto 2026**

Questa revisione integra la decisione D247. Il PDF v2.1 presente nella root è
una revisione storica precedente; questo file Markdown è la revisione corrente
machine-readable.

## 1. Obiettivo e sicurezza permanente

Sviluppare supporto Linux per `27c6:5125` senza alterare il percorso Windows.
Resta assoluto `factory_firmware_and_persistent_state_must_remain_untouched`:
no flash/IAP, provisioning o sostituzione PSK, OTP/factory data, configurazione
persistente, comando wire non compreso, live non autorizzato o retry implicito.

## 2. Evidence-first e avanzamento

Separare osservato, verificato, inferito, ipotizzato e ignoto. Le prove locali
specifiche di `GF_ST411SEC_APP_12509` (capture Windows canonica, `gfusb.dll`,
APP12509, evidenza live e test ripetibili) prevalgono sulle implementazioni
esterne per le affermazioni target-specific. Avanzamento reale richiede
esecuzione, nuova evidenza o un nuovo confine tecnico/hardware; una decisione
architetturale può cambiare legittimamente lo stato senza fingere avanzamento
hardware.

## 3. Architettura di licenza post-D247

```text
core/              GPL-2.0-or-later
  transport protocol tls fdt capture image
tools/             GPL-2.0-or-later
libfprint-driver/  LGPL-2.1-or-later
```

Il materiale originale già pubblicato fino a D246 sotto BSD-2-Clause conserva
quella licenza: la concessione non è revocata retroattivamente. Codice di terzi
mantiene i propri termini. Firmware/DLL OEM, capture, secret, materiale
biometrico, factory data e asset non redistribuibili non ricevono alcuna
blanket open-source license.

## 4. Rockytkg: fonte implementativa, non autorità probatoria
Repository di riferimento: [Rockytkg/goodix-linux-27c6-5125](https://github.com/Rockytkg/goodix-linux-27c6-5125)

Codice originale Rockytkg verificato come compatibile GPL-2.0-or-later può,
dopo D247, essere letto, copiato, adattato e incorporato esclusivamente nel
dominio GPL `core/`/`tools/`. Non serve una riscrittura clean-room in quel
dominio, ma sono obbligatori licenza, attribution e provenance.

Questo permesso non promuove Rocky a prova primaria del target 12509 e non
stabilisce safety, assenza di persistenza o compatibilità PSK/factory. Ogni
comportamento sensor-reaching richiede validazione differenziale locale e una
eventuale autorizzazione live separata.

## 5. Provenance permanente

Ogni import/adattamento registra: repository e commit/ref sorgente, path
sorgente, licenza/SPDX originale, copyright holder noto, data/step locale, path
di destinazione e natura delle modifiche. Preservare gli header applicabili e
verificare componenti/contributi di terzi. Il ledger operativo è
`docs/LICENSING_AND_PROVENANCE.md`.

## 6. Firewall GPL/LGPL

Non trasferire espressione GPL in `libfprint-driver/` salvo dual licensing
compatibile o licenza alternativa valida da tutti i titolari pertinenti. In
assenza, il driver LGPL deve essere implementato indipendentemente da
specifiche, fatti di protocollo, test ed evidenza, senza copiare espressione
GPL. Il consenso di un autore non relicenzia diritti altrui.

## 7. Metodo, live e Git

Usare scope minimo, Design → Implementazione → Esecuzione e aggiornare il
manuale canonico quando cambia conoscenza o stato. Prima di ripetere un live
fallito dichiarare metodo realmente diverso, nuova ipotesi e azione alternativa
in caso dello stesso fallimento. Preservare autorizzazione esplicita,
single-shot, zero retry, fail-closed, cleanup/reseal e baseline live approvata.
Non auto-approvare SHA, non riscrivere storia e non distruggere artefatti
storici o modifiche dell'Utente.

## 8. Pubblicazione

Il repository privato è il workspace canonico di sviluppo. Il pubblico resta
una superficie congelata finché uno step separato non esegue sanitizzazione e
audit di contenuto **e history**. L'uguaglianza del working tree non prova che
la storia privata sia pubblicabile: usare clean export, nuova storia o filtro
quando necessario, senza sincronizzazione automatica.

## 9. Documentazione, report e bundle

Il manuale tecnico in root è la fonte narrativa canonica, aggiornata
organicamente e non come log append-only. I bundle sono step-local e non
includono secret, PSK, firmware/DLL proprietarie, capture o dati biometrici.
Ogni output Dxxx, bundle e checksum compresi, risiede in `analysis/Dxxx/`; la
root è riservata alle fonti canoniche e alle directory di progetto. Eventuali
bundle binari storici ancora in root sono trasferiti insieme ai sidecar con una
relocation byte-preserving, non rigenerati, soltanto quando il move non rompe
consumatori eseguibili o riproducibilità; le eccezioni sono documentate.
La chiusura usa `OUTCOME`, `ADVANCEMENT`, `EXECUTABLE_CLOSURE`,
`RESIDUAL_BLOCKER_OR_RISK`, `CANONICAL_DOCUMENTATION`, `BUNDLE`.
