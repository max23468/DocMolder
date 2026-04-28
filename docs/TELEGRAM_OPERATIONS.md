# Operatività Telegram

Panoramica pratica delle capacità operative Telegram introdotte nel bot.

Il bot è pubblico e raggiungibile da [`@docmolder_bot`](https://t.me/docmolder_bot). Se `DOCMOLDER_ALLOWED_USER_IDS` non è configurata, i nuovi utenti possono usarlo senza richiesta di abilitazione. In modalità ristretta, il primo messaggio di un utente non autorizzato crea una richiesta accesso pending per gli admin.

## Comandi utente

- `/start`: apre DocMolder e mostra le azioni principali.
- `/help`: mostra guida rapida, limiti pubblici, dati e flussi consigliati.
- `/history`: mostra gli ultimi job personali, con dettaglio e rilancio.
- `/status`: mostra accesso, service mode, sessione corrente, coda personale e ultimo job.
- `/reset`: azzera sessione, preferenze rapide e preset leggeri; da qui l'utente può anche chiedere la cancellazione completa dei propri dati live con conferma inline.

## Deep link supportati

Il bot supporta solo payload essenziali su `/start <payload>`:

- `/start help`
- `/start history`
- `/start privacy`
- `/start status`

## Tastiere inline utente

Le tastiere inline sono contestuali alla sessione:

- con immagini mostra solo le azioni consigliate per quel set di file, con le azioni meno frequenti dietro `Altre azioni`
- con un singolo PDF mette davanti le azioni più comuni e lascia modifica pagine, rotazione e watermark nella vista espansa
- con più PDF espone come scelta primaria l'unione
- quando un flusso richiede un dettaglio, come compressione, split, rotazione, impaginazione A4 o profilo foto documento, mostra solo le opzioni di quel passo
- per compressione, split e immagini verso PDF può mostrare una scorciatoia `Usa preset` quando l'utente ha ripetuto la stessa impostazione più volte

Il pulsante `Altre azioni` espande tutte le azioni compatibili con la sessione corrente; `Meno azioni` torna alla vista breve.

## Preset utente leggeri

Il bot conserva solo impostazioni operative ricorrenti:

- livello compressione PDF
- scelta output split: ZIP unico o PDF separati
- layout immagini verso PDF: A4 o formato originale, con margine A4

Il preset nasce da scelte ripetute, non da contenuti documento. I messaggi e i
callback non salvano nomi file, testo estratto o profili documentali. La scelta
manuale resta sempre disponibile e può sovrascrivere il preset nel job corrente.

## Qualità foto documento

L'azione `Raddrizza foto documento` resta una trasformazione visiva guidata,
senza OCR. Prima del job l'utente può scegliere:

- `Più leggibile`
- `Mantieni colore`
- `Bianco/nero pulito`

Il risultato può includere avvisi pratici quando la foto sembra scura, sfocata,
con poco contrasto, senza bordo leggibile o con prospettiva incerta. Gli avvisi
devono indicare come riprovare, senza far credere che il bot legga o comprenda
il contenuto del documento.

## Console admin

Se `DOCMOLDER_ADMIN_USER_IDS` è configurata, gli admin usano `/admin` come ingresso unico nascosto dalla lista comandi pubblica. La dashboard inline espone:

- panoramica generale
- coda e ultimi job
- utenti attivi recenti, job conclusi 24h e failure rate 24h
- health runtime, SQLite, backup, worker e soglie prudenziali
- manutenzione, running stale, accessi pending, pruning, cancellazioni dati e audit recente
- job lenti recenti, secondo `DOCMOLDER_ADMIN_SLOW_JOB_THRESHOLD_MS`
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
- i dettagli pubblici su dati, retention e cancellazione sono esposti in `/help`, `/status`, `/start privacy` e nella pagina statica `/privacy.html`

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

Da shell il controllo standard è:

```bash
docmolder-healthcheck
```

In produzione il timer `docmolder-alertcheck.timer` richiama `deploy/alert-check.sh` ogni 5 minuti.
Il timer `docmolder-reconcile.timer` richiama `deploy/reconcile.sh` ogni 15 minuti per recuperare job stale e pulire runtime temporaneo.
Lo stesso reconcile applica anche il pruning dei job conclusi oltre `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`, default 30 giorni.

Segnali da verificare:

- servizio `docmolder` attivo
- database SQLite leggibile
- runtime dir scrivibile
- backup recenti presenti quando il timer è abilitato
- worker job non bloccato
- nessun accumulo anomalo di job `queued` o `running`
- nessun job `running` oltre una soglia ragionevole per il tipo di lavorazione
- errori Telegram e failure rate non persistenti oltre le soglie admin configurate
- spazio disco sufficiente per runtime, job temporanei e backup
- volume giornaliero, utenti attivi e dimensione SQLite sotto le soglie di soft launch

Soglie configurabili:

- numero massimo di job in coda: `DOCMOLDER_HEALTH_MAX_QUEUED_JOBS`
- numero massimo di job in esecuzione: `DOCMOLDER_HEALTH_MAX_RUNNING_JOBS`
- età massima di un job `running`: `DOCMOLDER_HEALTH_MAX_RUNNING_JOB_AGE_SECONDS`
- dimensione massima accettabile del runtime dir: `DOCMOLDER_HEALTH_MAX_RUNTIME_DIR_BYTES`
- dimensione massima accettabile del database SQLite: `DOCMOLDER_HEALTH_MAX_DATABASE_BYTES`
- età massima dell'ultimo backup SQLite: `DOCMOLDER_HEALTH_MAX_BACKUP_AGE_SECONDS`
- volume prudenziale: `DOCMOLDER_HEALTH_MAX_FINISHED_JOBS_24H` e `DOCMOLDER_HEALTH_MAX_ACTIVE_USERS_7D`
- failure rate prudenziale: `DOCMOLDER_HEALTH_MAX_FAILURE_RATE_PERCENT` dopo almeno `DOCMOLDER_HEALTH_FAILURE_RATE_MIN_FINISHED_JOBS`
- spazio disco minimo: `DOCMOLDER_HEALTH_MIN_DISK_FREE_BYTES` e `DOCMOLDER_HEALTH_MIN_DISK_FREE_PERCENT`
- carico e memoria minimi per VPS: `DOCMOLDER_HEALTH_MAX_LOAD_PER_CPU` e `DOCMOLDER_HEALTH_MIN_MEMORY_AVAILABLE_BYTES`
- retention storico job live: `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`

Le soglie iniziali sono prudenziali: servono a fermare crescita o promozione
prima che il servizio richieda una decisione architetturale. Non sono SLA.

## Manutenzione one-shot

Il comando:

```bash
docmolder-reconcile
```

riallinea il runtime operativo:

- rimette in coda job `running` rimasti stale
- pulisce directory temporanee oltre retention
- pruna job conclusi vecchi secondo `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`
- può usare una retention diversa per una singola run con `--prune-finished-days`, oppure saltare il pruning con `--no-prune-finished`
