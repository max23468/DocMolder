# DocMolder

`DocMolder` è un bot Telegram-first per trasformazioni documentali semplici e guidate.

L'utente invia file al bot, sceglie l'azione desiderata e riceve l'output direttamente in chat.

## Obiettivi del progetto

- Esperienza molto semplice via Telegram
- Supporto multiutente
- Elaborazione asincrona delle operazioni
- Retention breve dei file temporanei

## Funzionalità attuali

- Creazione PDF da immagini
- Scelta tra formato originale immagini o impaginazione A4 con bordi configurabili
- Conversione PDF in scala di grigi
- Compressione PDF solo su richiesta
- Unione PDF
- Estrazione pagine da un PDF
- Riordino pagine di un PDF
- Eliminazione pagine da un PDF
- Rotazione manuale delle pagine di un PDF
- Watermark testuale su PDF
- Correzione automatica dell'orientamento dei PDF quando serve, con possibilità di rifare il file senza auto-rotazione
- Correzione automatica orientamento per immagini
- Sessioni temporanee per raccogliere più file in messaggi successivi
- Storico ultimi job con dettaglio essenziale e possibilità di rilanciare un'elaborazione

## Flusso utente

1. L'utente invia uno o più file.
2. Il bot riconosce il contesto della sessione.
3. Il bot propone solo azioni compatibili con i file ricevuti.
4. L'utente sceglie l'azione con pulsanti inline.
5. Il bot elabora e restituisce il risultato.
6. I file temporanei vengono cancellati automaticamente.

## Sicurezza operativa

- Nessun salvataggio permanente dei file utente nel perimetro attuale del prodotto
- Pulizia automatica delle cartelle temporanee
- Limiti su dimensione file, numero di allegati e carico concorrente già presenti in forma iniziale e da rifinire prima di un uso più ampio

## Stato attuale

Questo repository contiene già una prima implementazione funzionante del flusso:

- configurazione dell'applicazione
- bot Telegram di base
- gestione persistente delle sessioni su SQLite
- tastiere e messaggi iniziali
- caricamento dei file da Telegram
- creazione PDF da immagini
- scelta guidata A4 / formato originale per i PDF creati da immagini
- unione PDF
- estrazione pagine PDF
- riordino pagine PDF
- eliminazione pagine PDF
- rotazione manuale pagine PDF
- watermark testuale PDF
- conversione PDF in scala di grigi
- compressione PDF con livelli semplici
- correzione automatica dell'orientamento PDF nei flussi compatibili
- correzione orientamento immagini
- storico lavori utente con recupero rapido del job via rilancio

## Nota sul motore PDF attuale

La pipeline PDF è stata resa più conservativa rispetto allo scaffold iniziale.

Compressione:

- livello `Leggera`: ottimizzazione lossless della struttura PDF
- livello `Media`: ottimizzazione conservativa con tentativo di ricompressione delle immagini mantenendo il PDF nativo
- livello `Forte`: prova prima una compressione conservativa, poi una compressione nativa via `Ghostscript`, e usa la rasterizzazione solo come soluzione di ripiego

Scala di grigi:

- se sul server è disponibile `Ghostscript`, il bot prova una conversione più fedele alla struttura del PDF
- se `Ghostscript` non è disponibile, prova prima una conversione nativa delle immagini interne del PDF
- solo come ultimo passaggio usa una soluzione visiva di ripiego che garantisce l'output ma può perdere testo ricercabile, layer o metadati avanzati

Questo ci permette di preservare meglio il contenuto nativo dei PDF quando l'ambiente lo consente, senza rinunciare a una soluzione di ripiego affidabile.

## Avvio locale

Il modo più rapido per lavorare in locale è:

```bash
make setup
cp .env.example .env
make run
```

Per la guida completa, vedi [`docs/LOCAL_SETUP.md`](docs/LOCAL_SETUP.md).

## Deploy Oracle

Per il deploy su Oracle VPS con Ubuntu, vedi [`docs/DEPLOY_ORACLE.md`](docs/DEPLOY_ORACLE.md).

## Documentazione

Documenti utili:

- [`docs/CHANGELOG.md`](docs/CHANGELOG.md)
- [`docs/CONTEXT.md`](docs/CONTEXT.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)
- [`docs/LOCAL_SETUP.md`](docs/LOCAL_SETUP.md)
- [`docs/DEPLOY_ORACLE.md`](docs/DEPLOY_ORACLE.md)
- [`docs/OPERATIONS.md`](docs/OPERATIONS.md)
- [`docs/PDF_PIPELINE.md`](docs/PDF_PIPELINE.md)
- [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/TESTING.md`](docs/TESTING.md)

## Variabili ambiente

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_ALLOWED_USER_IDS` facoltativa
- `DOCMOLDER_ADMIN_USER_IDS` facoltativa
  gli admin ricevono un messaggio privato dal bot al primo accesso di ogni nuovo utente
- `DOCMOLDER_DEFAULT_LANGUAGE`
- `DOCMOLDER_SESSION_TTL_MINUTES`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_MAX_FILE_SIZE_MB`
- `DOCMOLDER_UPLOAD_BURST_LIMIT`
- `DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS`
- `DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER`
- `DOCMOLDER_CLEANUP_INTERVAL_MINUTES`
- `DOCMOLDER_STALE_JOB_RETENTION_HOURS`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

## Prossimi passi suggeriti

La roadmap corrente del progetto è in [`docs/ROADMAP.md`](docs/ROADMAP.md).
Le modifiche rilevanti vengono annotate anche in [`docs/CHANGELOG.md`](docs/CHANGELOG.md).

In sintesi, le priorità attuali sono:

- aumentare affidabilità e copertura dei test sui PDF più difficili
- migliorare messaggi utente, fallback e tracciamento della qualità delle trasformazioni
- rafforzare metriche admin, limiti operativi e ripartenza dei job dopo crash o riavvio
- concentrarsi ora soprattutto sul consolidamento tecnico della pipeline, della coda job e dei messaggi operativi

## Monitoraggio admin

Se configuri `DOCMOLDER_ADMIN_USER_IDS`, l'admin può usare anche:

- `/admin` per vedere un riepilogo rapido di utenti, nuovi accessi, operazioni completate, stato coda, utenti più attivi e ultimi job riusciti o falliti

Comandi utente utili:

- `/history` per vedere gli ultimi job personali, aprirne i dettagli essenziali o rilanciarli
