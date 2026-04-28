# Architettura

Panoramica rapida dell'architettura corrente di `DocMolder`.

## Indice

- scopo del progetto
- moduli principali
- flussi principali
- persistenza e runtime
- osservabilita minima
- limiti da tenere presenti

Documenti collegati:

- [INDEX.md](./INDEX.md)
- [CONTEXT.md](./CONTEXT.md)
- [DECISIONS.md](./DECISIONS.md)
- [PDF_PIPELINE.md](./PDF_PIPELINE.md)
- [TELEGRAM_OPERATIONS.md](./TELEGRAM_OPERATIONS.md)
- [DATA_MODEL.md](./DATA_MODEL.md)

## Scopo

`DocMolder` e un bot Telegram-first per trasformazioni guidate di PDF e immagini.

Il prodotto resta:

- chat-first
- orientato a una trasformazione documentale chiara per volta
- best-effort, senza SLA formale
- focalizzato su output immediato e retention breve dei file temporanei

Non e:

- un gestionale documentale completo
- uno storage permanente di file utente
- un editor PDF collaborativo o generalista
- una dashboard web-first

## Moduli principali

### Entry point e configurazione

- `src/docmolder/main.py`
  - carica configurazione e avvia il bot
- `src/docmolder/config.py`
  - legge variabili `DOCMOLDER_*`, runtime dir, limiti e soglie operative

### Bot Telegram

- `src/docmolder/bot.py`
  - handler Telegram, wizard utente, admin console, queue worker e messaggi
- `src/docmolder/action_catalog.py`
  - catalogo centrale di azioni, analisi sessione, naming output e compatibilita tra file e operazioni
- `src/docmolder/telegram_messaging.py`
  - chunking messaggi lunghi e fallback parse-mode per invii Telegram gestiti
- limiti leggeri per upload e job utente
  - gestiti nel runtime Telegram in `src/docmolder/bot.py`, con stato anti-burst minimo e temporaneo in `app_meta`

### Pipeline documentale

- `src/docmolder/processing.py`
  - trasformazioni PDF e immagini, dispatch azione -> handler, fallback, downscale preventivo immagini enormi, cleanup job e metriche di processing
- `docs/PDF_PIPELINE.md`
  - dettaglia compromessi tra percorsi nativi, Ghostscript e fallback raster

### Persistenza

- `src/docmolder/session_store.py`
  - facciata compatibile per store sessioni/job
- `src/docmolder/session_store_protocol.py`
  - protocollo condiviso dello store
- `src/docmolder/sqlite_session_store.py`
  - sessioni, file associati alla sessione, job, utenti noti, usage events e `app_meta` su SQLite
- `src/docmolder/in_memory_session_store.py`
  - store in memoria per test e runtime isolati
- `src/docmolder/sqlite_backup.py`
  - backup e restore verificati di SQLite
- `src/docmolder/healthcheck.py`
  - healthcheck CLI con output testo/JSON ed exit code
- `src/docmolder/reconcile.py`
  - manutenzione one-shot di job stale e runtime temporaneo
- `src/docmolder/logging_utils.py` e `src/docmolder/retry.py`
  - logging strutturato leggero e retry/backoff condiviso
- `src/docmolder/errors.py` e `src/docmolder/git_utils.py`
  - gerarchia errori applicativi e piccoli tool di manutenzione Git locale
- `src/docmolder/models.py`
  - modelli tipizzati di sessione, job, payload, azioni e report admin

## Flussi principali

### Upload e sessione

1. L'utente invia PDF o immagini via Telegram.
2. Il bot valida tipo, dimensione e limiti operativi.
3. La sessione utente viene aggiornata in SQLite.
4. Il bot propone azioni compatibili tramite il catalogo centrale.

### Job documentale

1. L'utente sceglie un'azione o completa un wizard.
2. Il bot crea un record `jobs` con payload serializzato.
3. Il worker marca il job `running` e scarica i file Telegram necessari.
4. `DocumentProcessor` produce output in una directory temporanea del job.
5. Il bot invia il risultato, registra metriche essenziali e pulisce i temporanei.

### Tastiere inline contestuali

1. Il catalogo costruisce una analisi strutturata della sessione: inventario file, azioni supportate, azioni esposte, azioni consigliate, azioni avanzate, warning e prossimo passo.
2. Recap e tastiera riusano la stessa analisi per evitare inferenze duplicate nello stesso passaggio.
3. La tastiera azioni deriva dalla sessione corrente e mostra prima un set breve di azioni consigliate.
4. Le azioni compatibili ma meno frequenti restano dietro `Altre azioni`, senza cambiare i callback storici delle singole azioni.
5. I wizard di dettaglio mostrano solo le opzioni del passo corrente, ad esempio compressione, split, rotazione o impaginazione A4.
6. La tastiera admin mostra scorciatoie agli ultimi job solo per gli stati presenti nel database.

### Storico e retry

1. I job conclusi restano come storico leggero nel database.
2. `/history` risolve solo job dell'utente corrente e permette il rilancio tramite callback.
3. I retry mantengono il riferimento al job di origine tramite `rerun_of_job_id`.

### Admin e operativita

1. Gli admin configurati con `DOCMOLDER_ADMIN_USER_IDS` usano `/admin` come ingresso unico.
2. La dashboard inline legge stato runtime, SQLite, worker, accessi pending, ultimi job e metriche leggere.
3. I callback della dashboard governano la modalita manutenzione.
4. Le richieste accesso automatiche e i callback admin di review gestiscono accesso dinamico persistito in `app_meta`.

## Persistenza e runtime

Runtime tipico:

- locale: `./data/runtime`
- VPS: `/opt/docmolder/data/runtime`

Asset principali:

- database SQLite: `docmolder.db`
- directory job temporanei: `jobs/`
- backup SQLite: `backups/`

Regole:

- i file utente sono temporanei e non sono prodotto permanente
- lo storico persistente riguarda job, metadati e metriche leggere, non il contenuto dei documenti
- SQLite e il target corrente per singola VPS e carico controllato
- una crescita rilevante di concorrenza o retention richiede una nuova decisione architetturale

## Path operativi stabili

- `deploy/` resta il percorso degli script e delle unità `systemd` usate dalla VPS
- `deploy/` include anche il listener webhook GitHub privato che avvia l'aggiornamento automatico della VPS senza usare GitHub Actions
- `scripts/` resta il percorso degli strumenti locali, CI e publishing richiamati da Makefile, workflow e runbook
- eventuali riorganizzazioni future di questi percorsi devono introdurre prima wrapper compatibili nei path storici, poi aggiornare workflow e documentazione

## Osservabilita minima

Canali attuali:

- log `systemd` del servizio `docmolder`
- log `systemd` del listener `docmolder-github-webhook`
- comando CLI `docmolder-healthcheck`
- console admin Telegram `/admin` con health, queue e metriche via dashboard inline
- metriche job in `jobs`
- metriche Telegram aggregate in `app_meta`
- timestamp recenti anti-burst upload in `app_meta`, limitati alla finestra di rate limit
- backup giornaliero verificato tramite timer `docmolder-db-backup.timer`
- alert check periodico tramite timer `docmolder-alertcheck.timer`
- reconcile periodico tramite timer `docmolder-reconcile.timer`
- soglie leggere per disco, runtime dir, load medio per CPU, RAM disponibile, coda e job running stale

Eventi e log devono permettere di correlare almeno:

- `job_id`
- `telegram_user_id`, solo quando serve e senza dati documento
- `update_id` o contesto callback quando disponibile
- azione richiesta
- stato job e durata

## Limiti da tenere presenti

- il bot usa polling Telegram, non webhook pubblici
- l'automazione deploy puo usare un webhook GitHub privato sulla VPS, ma non espone il bot come servizio web generale
- il runtime e pensato per un singolo nodo applicativo
- i file temporanei devono restare sotto cleanup attivo
- i log non devono contenere contenuti dei documenti
- i fallback raster possono produrre output meno ricchi del PDF nativo
- Ghostscript e opzionale ma utile per alcuni flussi PDF
