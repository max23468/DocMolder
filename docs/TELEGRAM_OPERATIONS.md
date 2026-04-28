# Operatività Telegram

Panoramica pratica delle capacità operative Telegram introdotte nel bot.

Il bot e pubblico e raggiungibile da [`@docmolder_bot`](https://t.me/docmolder_bot). Se `DOCMOLDER_ALLOWED_USER_IDS` non e configurata, i nuovi utenti possono usarlo senza richiesta di abilitazione. In modalita ristretta, il primo messaggio di un utente non autorizzato crea una richiesta accesso pending per gli admin.

## Comandi utente

- `/start`: apre DocMolder e mostra le azioni principali.
- `/help`: mostra guida rapida e flussi consigliati.
- `/history`: mostra gli ultimi job personali, con dettaglio e rilancio.
- `/status`: mostra accesso, service mode, sessione corrente, coda personale e ultimo job.
- `/reset`: azzera sessione e preferenze rapide.

## Deep link supportati

Il bot supporta solo payload essenziali su `/start <payload>`:

- `/start help`
- `/start history`
- `/start status`

## Tastiere inline utente

Le tastiere inline sono contestuali alla sessione:

- con immagini mostra solo le azioni consigliate per quel set di file, con le azioni meno frequenti dietro `Altre azioni`
- con un singolo PDF mette davanti le azioni piu comuni e lascia modifica pagine, rotazione e watermark nella vista espansa
- con piu PDF espone come scelta primaria l'unione
- quando un flusso richiede un dettaglio, come compressione, split, rotazione o impaginazione A4, mostra solo le opzioni di quel passo

Il pulsante `Altre azioni` espande tutte le azioni compatibili con la sessione corrente; `Meno azioni` torna alla vista breve.

## Console admin

Se `DOCMOLDER_ADMIN_USER_IDS` è configurata, gli admin usano `/admin` come ingresso unico nascosto dalla lista comandi pubblica. La dashboard inline espone:

- panoramica generale
- coda e ultimi job
- health runtime, SQLite, backup e worker
- manutenzione, running stale, accessi pending e audit recente
- metriche Telegram aggregate da `app_meta`
- pausa e ripresa servizio
- dettaglio rapido degli ultimi job per stato, solo quando esiste almeno un job in quello stato

Le azioni admin sensibili scrivono anche un audit log minimale in SQLite:

- cambio service mode tramite dashboard inline
- richieste e revisioni accesso utente

## Dashboard inline admin

La dashboard inline mantiene sempre le scorciatoie operative principali e aggiunge le scorciatoie ai job solo quando sono utili:

- panoramica, coda, health, metriche e manutenzione restano sempre raggiungibili
- pausa/ripresa servizio cambia in base al service mode corrente
- ultimo job e ultimi job per stato compaiono solo se il database contiene job pertinenti

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
