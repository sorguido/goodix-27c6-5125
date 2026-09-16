# D231 — failure mode e blast radius per il futuro D233

## Decisione di rischio

`HARDWARE_BLAST_RADIUS_STATUS=BOUNDED_NONZERO_RECOVERY_REQUIRED`

Il replay esatto OEM non contiene erase, IAP, provisioning, boot-mode change o
write persistenti note. Il peggior esito credibile resta però un sensore in
stato protocollo ignoto, disconnesso/non enumerato o temporaneamente non
utilizzabile da Windows/fprintd. Poiché i receiver resident A2/0x70 non sono
disponibili, una mutazione persistente non documentata non può essere esclusa
in senso assoluto; non è supportata da alcun dataflow host, nome, sequenza OEM o
cross-version evidence.

D233 deve essere un esperimento separato, esplicitamente autorizzato, con una
sola progressione lineare, capture completa, fail-closed e nessun retry cieco.

## Matrice dei failure mode

| failure mode | trigger / osservabile | ultimo comando noto | classe stato possibile | evidenza mutazione persistente | recuperabilità attesa | evidenza recovery | azione immediata sicura | azione automatica vietata | escalation | peggior blast radius credibile | conf. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A0 timeout/no response | nessun ACK entro budget | comando corrente | completion ambigua | nessuna | probabile via re-enumerazione | comportamento USB ordinario, non testato D231 | stop I/O, conserva capture, osserva enumerazione | resend/restart sequenza | operatore | protocollo ignoto/non enumerato | media |
| ACK/irqstatus inatteso | control/status/len differente | A2/90 | device vivo ma stato rifiutato | nessuna | alta senza altri invii | parser e response typed OEM | abort immediato | normalizzare/ignorare status | operatore | init incompleto | alta |
| opcode/length inatteso | frame IN non ammesso | qualunque | desync/parser ambiguity | nessuna | media-alta dopo reset esterno ordinario | framing canonico | stop e salva raw redatto | interpretazione permissiva | operatore | stato ignoto | alta |
| USB stall | errore endpoint | qualunque | pipe/device bloccato | nessuna | media | stack USB standard | chiudi handle; nessun clear/retry automatico | clear-halt + replay | operatore | non enumerato fino a power cycle | media |
| disconnect/re-enumeration | VID/PID sparisce/torna | soprattutto A2 | reset completato o fault | nessuna | probabile | A2 è reset sensore host-side | non inviare finché identità non rivalidata | continuare su nuovo handle | operatore | bind a device errato/init parziale | alta |
| A2 inatteso | ACK/typed/irqstatus fuori allowlist | A2 | reset parziale/ambigua | nessuna nota | probabile | due response OEM disponibili | abort | secondo A2 cieco | operatore | sensor offline | media-alta |
| 0x70 inatteso | ACK mancante/errato | 70 | mode ignoto | nessuna nota | probabile | OEM lo usa prima dei DAC | abort prima di 0x80 | procedere alle write DAC | operatore | mode/config incoerente | media-alta |
| 0x80/0x90 rejection | ACK/status non OEM | 80 o 90 | config parziale | write runtime note | probabile con fresh OEM init | D230 classifica volatile | abort; annota indice esatto | completare il resto “per coerenza” | operatore | calibrazione runtime incoerente | alta |
| D1 rejection | nessun ClientHello B0 | D1 | pre-TLS completo, TLS non avviato | nessuna | alta con sessione nuova | capture mostra B0 in 2.099 ms | chiudi sessione | D1 ripetuto sullo stesso stato | operatore | Windows session temporarily unavailable | alta |
| TLS alert | record alert valido | B0/TLS | sessione TLS fallita | nessuna | alta, nuova sessione controllata | TLS standard | close_notify se già sicuro, poi stop | fallback suite/identity | operatore | init non completato | alta |
| Bad Record MAC/auth failure | alert o errore AEAD | B0/TLS | PSK/transcript/sequence mismatch | nessuna | alta dopo diagnosi offline | profilo PSK canonico | stop e zeroizza memoria effimera | provare altre key | operatore sicurezza | lockout non evidenziato; sessione fallita | alta |
| TLS timeout | nessun record entro budget | B0/TLS | sessione half-open | nessuna | media-alta | capture baseline | stop e chiudi handle | keepalive/rehandshake cieco | operatore | sessione bloccata fino a reset ordinario | media |
| enumerato ma protocollo ignoto | VID/PID presente, precondizione fallisce | variabile | unknown | ignota | media | status/read-only allowlist prevista | sole verifiche passive/read-only autorizzate | riprendere dal mezzo | operatore | incompatibilità Windows finché recovery | media |
| non enumerato | VID/PID assente oltre budget | variabile | offline | ignota | incerta; power-cycle manuale possibile | nessun test D231 | stop software, nessun comando | USB reset/IAP automatico | operatore + backup device | perdita temporanea o durevole del sensore | media |
| restore fprintd/kernel fallisce | servizio/driver non torna | nessuno | host integration broken | nessuna device-side | alta lato host | procedure di servizio da preflight | lascia log, non manipolare device | reinstall/blacklist automatica | operatore sistema | biometria host indisponibile | alta |
| identity/state mismatch post-run | serial/hash/E4/status differente | fine/abort | target o stato errato | possibile ma non provata | incerta | baseline pre/post obbligatoria | quarantena e stop | “repair”/provisioning | operatore sicurezza | perdita compatibilità factory | alta |
| E0/A4/F0/F4/IAP/provisioning raggiungibile | qualsiasi control fuori allowlist | prima dell'invio | bug di piano | tali path possono mutare | non assunta | D230 maintenance audit | non inviare; hard abort | conferma permissiva | revisione codice | erase/firmware/key mutation | alta |
| SIGINT/crash | processo termina asincrono | qualunque | completion ambigua | dipende dall'ultimo comando | media | cleanup host non prova device state | handler minimo: stop submit, flush capture, restore host | restart automatico | operatore | init parziale/non enumerato | alta |

## Invarianti D233

1. allowlist esatta: sola sequenza OEM approvata e byte-pinned;
2. device identity, DLL/capture/config hash e PSK-store identity verificati prima;
3. denylist hard di E0/A4/F0/F4/IAP/ClearApp/provisioning/boot operations;
4. nessun automatic retry dopo un OUT la cui completion è ambigua;
5. ogni mismatch ferma la macchina prima del comando successivo;
6. niente secret, TLS plaintext, immagini o template in log/capture pubblici;
7. baseline e post-check read-only, ripristino servizio e verifica Windows;
8. power-cycle solo manuale e già autorizzato come recovery, mai come parte del
   flusso automatico.

La first capture perduta riduce la replica packet-level disponibile e deve
comparire nel briefing D233. Non aumenta l'allowlist e non giustifica tolleranze
più ampie.

