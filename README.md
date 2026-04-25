# DocMolder

`DocMolder` è un bot Telegram-first per trasformazioni documentali semplici e guidate.

Posizionamento sintetico: utility professionale, smart e amichevole per PDF, scansioni e immagini direttamente in chat.

L'utente invia file al bot, sceglie l'azione desiderata e riceve l'output direttamente in chat.

## Obiettivi del progetto

- Esperienza molto semplice via Telegram
- Supporto multiutente
- Elaborazione asincrona delle operazioni
- Retention breve dei file temporanei

## Perimetro del Prodotto

`DocMolder` vuole restare una utility documentale chat-first:

- focalizzata su trasformazioni pratiche di PDF e foto di documenti
- semplice, guidata e affidabile
- orientata a una operazione chiara per volta

Nel perimetro attuale non vuole diventare:

- un editor PDF generalista
- un sistema completo di document management o archiviazione
- un assistente conversazionale che promette comprensione illimitata del linguaggio naturale

Questo perimetro serve come filtro per la roadmap: accettiamo soprattutto evoluzioni che aumentano chiarezza, qualità del risultato e affidabilità del servizio.

## Funzionalità attuali

- Creazione PDF da immagini
- Scelta tra formato originale immagini o impaginazione A4 con bordi configurabili
- Conversione PDF in scala di grigi
- Compressione PDF solo su richiesta
- Unione PDF
- Divisione PDF in un file per pagina, con scelta tra ZIP unico e PDF separati
- Estrazione pagine da un PDF
- Riordino pagine di un PDF
- Eliminazione pagine da un PDF
- Rotazione manuale delle pagine di un PDF
- Watermark testuale su PDF
- Correzione automatica dell'orientamento dei PDF quando serve, con possibilità di rifare il file senza auto-rotazione
- Correzione automatica orientamento per immagini
- Sessioni temporanee per raccogliere più file in messaggi successivi
- Storico ultimi job con dettaglio essenziale e possibilità di rilanciare un'elaborazione
- Self-service rapido con `/history`, `/last`, `/access`, `/request_access`, `/policy`, `/status` e `/reset`
- Deep link Telegram per scorciatoie contestuali e rilancio rapido di job
- Console admin Telegram con queue, health, metrics, manutenzione, access review, pause/resume e scorciatoie inline
- Metriche Telegram leggere e alert admin meno rumorosi
- Nomi output più leggibili, derivati dal file sorgente e dall'azione eseguita

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
- Limiti configurabili su dimensione file, numero di allegati, burst upload e carico concorrente

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
- divisione PDF in un file per pagina, con scelta tra ZIP unico e PDF separati
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
- self-service utente con `/history`, `/last`, `/access`, `/request_access`, `/policy`, `/status` e `/reset`
- console admin Telegram live con `/queue`, `/health`, `/maintenance_overview`, `/metrics`, `/job`, `/retry`, access review, `/pause`, `/resume`
- metriche e retry Bot API per i flussi Telegram più sensibili

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

Per la guida completa di setup e test locali, vedi [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md).

## Deploy Oracle

Per setup e gestione operativa su Oracle VPS con Ubuntu, vedi [`docs/VPS_RUNBOOK.md`](docs/VPS_RUNBOOK.md).

Per usare Codex su `chatgpt.com` come postazione di lavoro e deploy senza dipendere dal Mac, vedi [`docs/CODEX_CLOUD_DEPLOY.md`](docs/CODEX_CLOUD_DEPLOY.md).

Il flusso consigliato da remoto e:

- Codex o GitHub preparano il codice fino a `main`
- GitHub Actions esegue il deploy verso la VPS
- la VPS applica il deploy standard con `deploy/update-vps.sh`

Per gli aggiornamenti successivi sulla VPS, il flusso standard e:

```bash
sudo /opt/docmolder/app/deploy/update-vps.sh
```

## Documentazione

Documenti utili:

- [`CHANGELOG.md`](CHANGELOG.md)
- [`docs/BRAND.md`](docs/BRAND.md)
- [`docs/CONTEXT.md`](docs/CONTEXT.md)
- [`docs/DECISIONS.md`](docs/DECISIONS.md)
- [`docs/INDEX.md`](docs/INDEX.md)
- [`docs/LOCAL_DEV.md`](docs/LOCAL_DEV.md)
- [`docs/VPS_RUNBOOK.md`](docs/VPS_RUNBOOK.md)
- [`docs/CODEX_CLOUD_DEPLOY.md`](docs/CODEX_CLOUD_DEPLOY.md)
- [`docs/PDF_PIPELINE.md`](docs/PDF_PIPELINE.md)
- [`docs/TELEGRAM_OPERATIONS.md`](docs/TELEGRAM_OPERATIONS.md)
- [`docs/RELEASE_PROCESS.md`](docs/RELEASE_PROCESS.md)
- [`docs/VERSIONING.md`](docs/VERSIONING.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/GITHUB_ALIGNMENT.md`](docs/GITHUB_ALIGNMENT.md)
- [`docs/GITHUB_MAINTENANCE.md`](docs/GITHUB_MAINTENANCE.md)

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
- `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- `DOCMOLDER_ADMIN_DAILY_REPORT_HOUR`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_DAY`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_HOUR`
- `DOCMOLDER_ADMIN_ALERT_WINDOW_MINUTES`
- `DOCMOLDER_ADMIN_ALERT_MIN_FINISHED_JOBS`
- `DOCMOLDER_ADMIN_ALERT_FAILURE_RATE_PERCENT`
- `DOCMOLDER_ADMIN_ALERT_REPEATED_FAILURES_THRESHOLD`
- `DOCMOLDER_ADMIN_ALERT_COOLDOWN_MINUTES`
- `DOCMOLDER_HEALTH_MAX_QUEUED_JOBS`
- `DOCMOLDER_HEALTH_MAX_RUNNING_JOBS`
- `DOCMOLDER_HEALTH_MAX_RUNNING_JOB_AGE_SECONDS`
- `DOCMOLDER_HEALTH_MAX_RUNTIME_DIR_BYTES`
- `DOCMOLDER_HEALTH_MAX_BACKUP_AGE_SECONDS`
- `DOCMOLDER_HEALTH_MIN_DISK_FREE_BYTES`
- `DOCMOLDER_HEALTH_MIN_DISK_FREE_PERCENT`
- `DOCMOLDER_HEALTH_MAX_LOAD_PER_CPU`
- `DOCMOLDER_HEALTH_MIN_MEMORY_AVAILABLE_BYTES`
- `DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`
- `DOCMOLDER_SQLITE_BACKUP_DIR`
- `DOCMOLDER_SQLITE_BACKUP_RETENTION_DAYS`
- `DOCMOLDER_TELEGRAM_BRAND_SYNC_ENABLED`

## Prossimi passi suggeriti

La roadmap corrente del progetto è in [`docs/ROADMAP.md`](docs/ROADMAP.md).
Le modifiche rilevanti vengono annotate in [`CHANGELOG.md`](CHANGELOG.md), mentre policy e bump versioni sono descritte in [`docs/VERSIONING.md`](docs/VERSIONING.md).

Per il versioning ordinario, il repository e `release-please`-first: le feature PR e le fix PR non devono aggiornare manualmente versione o changelog di release. Quei file vengono gestiti dalla Release PR automatica.

In sintesi, la priorità attuale è:

- Fase 8: ottimizzazione del funzionamento interno e delle raccomandazioni utente

## Monitoraggio admin

Se configuri `DOCMOLDER_ADMIN_USER_IDS`, l'admin può usare anche:

- `/admin` per vedere un riepilogo rapido di utenti, nuovi accessi, operazioni completate, stato coda, utenti più attivi e ultimi job riusciti o falliti
- `/queue` per vedere backlog, job queued/running e ultimi falliti
- `/health` per controllare runtime, SQLite, backup e worker
- `/maintenance_overview` per backlog operativo, accessi pending, running stale e audit recente
- `/metrics` per vedere le metriche Telegram aggregate
- `/job <selector>` per aprire rapidamente il dettaglio di un job
- `/retry <selector>` per rilanciare un job esistente
- `/approve_user <id>`, `/reject_user <id>`, `/suspend_user <id>`, `/reactivate_user <id>` per gestire accessi dinamici
- `/pause` e `/resume` per mettere il bot in manutenzione o riattivarlo

Comandi utente utili:

- `/history` per vedere gli ultimi job personali, aprirne i dettagli essenziali o rilanciarli
- `/last` per rilanciare l'ultimo job personale
- `/access` per controllare accesso, sessione e coda personale
- `/request_access` per chiedere abilitazione quando il bot è ristretto
- `/policy` o `/privacy` per limiti, retention e regole operative sintetiche
- `/status` per vedere il riepilogo della sessione corrente
- `/reset` per azzerare sessione e ultime scelte rapide
