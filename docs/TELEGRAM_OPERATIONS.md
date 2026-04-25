# Operatività Telegram

Panoramica pratica delle capacità operative Telegram introdotte nel bot.

## Comandi utente

- `/history`: mostra gli ultimi job personali, con dettaglio e rilancio.
- `/last`: rilancia l'ultimo job personale senza dover reinviare i file.
- `/access`: mostra stato accesso, sessione corrente e coda personale.
- `/request_access`: invia una richiesta di abilitazione all'admin quando il bot è ristretto.
- `/policy` o `/privacy`: mostra limiti, retention e regole operative del servizio.
- `/status`: riepilogo rapido della sessione corrente.
- `/reset`: azzera sessione e preferenze rapide.

## Deep link supportati

Il bot supporta anche payload su `/start <payload>` per scorciatoie contestuali:

- `/start help`
- `/start history`
- `/start status`
- `/start access`
- `/start last`
- `/start retry_<id>`
- `/start retry_latest`

I deep link di retry sono limitati ai job dell'utente che li apre.

## Console admin

Se `DOCMOLDER_ADMIN_USER_IDS` è configurata, gli admin possono usare:

- `/admin`: panoramica generale.
- `/queue`: stato coda, job queued/running e ultimi falliti.
- `/health`: stato runtime, SQLite, backup e worker.
- `/maintenance_overview`: backlog operativo, running stale, accessi pending e audit recente.
- `/metrics`: metriche Telegram aggregate da `app_meta`.
- `/job <selector>`: dettaglio rapido di un job.
- `/retry <selector>`: rilancia un job esistente.
- `/approve_user <id>`, `/reject_user <id>`, `/suspend_user <id>`, `/reactivate_user <id>`: gestiscono accesso dinamico persistito in `app_meta`.
- `/pause`: mette il bot in modalità manutenzione.
- `/resume`: riattiva il servizio.

Le azioni admin sensibili scrivono anche un audit log minimale in SQLite:

- cambio service mode tramite `/pause`, `/resume` o dashboard inline
- retry admin di un job esistente
- richieste e revisioni accesso utente

Selector supportati per `/job` e `/retry`:

- id numerico
- `latest`
- `failed`
- `running`
- `queued`
- `succeeded`

Per `/retry` è disponibile anche:

- `--no-auto-rotate`

utile per rilanciare un job disabilitando la correzione automatica dell'orientamento PDF.

## Dashboard inline admin

La dashboard inline permette scorciatoie veloci per:

- panoramica
- coda
- health
- metriche
- manutenzione
- pausa/ripresa servizio
- ultimo fallito
- ultimo running
- ultimo queued
- ultimo succeeded
- ultimo job in assoluto

## Resilienza Bot API

I flussi Telegram più sensibili usano retry automatici su:

- `429 RetryAfter`
- `TimedOut`
- `NetworkError`

Le metriche aggregate tengono traccia di:

- comandi
- callback
- upload documento/foto
- retry `sendMessage`
- retry `sendDocument`

## Anti-spam e hardening

- callback admin con anti-replay leggero a finestra breve
- validazione più stretta dei callback più importanti
- messaggi uniformi per callback invalide o scadute
- digest sugli alert admin ripetuti
- throttling delle notifiche admin per nuovi utenti

## Note operative

- il bot resta in polling, coerentemente con le decisioni architetturali correnti
- i file utente restano temporanei; non è stato introdotto storage permanente dei file
- le metriche Telegram attuali sono volutamente leggere e persistono in `app_meta`

## Standard eventi e log

I log operativi devono essere correlabili senza esporre contenuti documento.

Campi consigliati quando disponibili:

- `job_id`
- `update_id`
- `telegram_user_id`, solo quando serve alla diagnosi
- `action`
- `job_status`
- `duration_ms`
- `input_bytes`
- `output_bytes`

Regole:

- non loggare contenuti dei documenti
- non loggare payload completi dei job
- non usare nomi file come identificativo principale se possono contenere dati personali
- preferire messaggi sintetici e stabili, utili a cercare nel journal

## Criteri minimi di salute

Un controllo operativo del servizio non deve fermarsi al solo `systemctl active`.

Da shell il controllo standard e:

```bash
docmolder-healthcheck
```

In produzione il timer `docmolder-alertcheck.timer` richiama `deploy/alert-check.sh` ogni 5 minuti.
Il timer `docmolder-reconcile.timer` richiama `deploy/reconcile.sh` ogni 15 minuti per recuperare job stale e pulire runtime temporaneo.

Segnali da verificare:

- servizio `docmolder` attivo
- database SQLite leggibile
- runtime dir scrivibile
- backup recenti presenti quando il timer e abilitato
- worker job non bloccato
- nessun accumulo anomalo di job `queued` o `running`
- nessun job `running` oltre una soglia ragionevole per il tipo di lavorazione
- errori Telegram e failure rate non persistenti oltre le soglie admin configurate
- spazio disco sufficiente per runtime, job temporanei e backup

Soglie configurabili:

- numero massimo di job in coda: `DOCMOLDER_HEALTH_MAX_QUEUED_JOBS`
- numero massimo di job in esecuzione: `DOCMOLDER_HEALTH_MAX_RUNNING_JOBS`
- eta massima di un job `running`: `DOCMOLDER_HEALTH_MAX_RUNNING_JOB_AGE_SECONDS`
- dimensione massima accettabile del runtime dir: `DOCMOLDER_HEALTH_MAX_RUNTIME_DIR_BYTES`
- eta massima dell'ultimo backup SQLite: `DOCMOLDER_HEALTH_MAX_BACKUP_AGE_SECONDS`
- spazio disco minimo: `DOCMOLDER_HEALTH_MIN_DISK_FREE_BYTES` e `DOCMOLDER_HEALTH_MIN_DISK_FREE_PERCENT`
- carico e memoria minimi per VPS: `DOCMOLDER_HEALTH_MAX_LOAD_PER_CPU` e `DOCMOLDER_HEALTH_MIN_MEMORY_AVAILABLE_BYTES`

## Manutenzione one-shot

Il comando:

```bash
docmolder-reconcile
```

riallinea il runtime operativo:

- rimette in coda job `running` rimasti stale
- pulisce directory temporanee oltre retention
- puo prunare job conclusi vecchi se invocato con `--prune-finished-days`
