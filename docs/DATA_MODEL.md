# Modello Dati

Panoramica dei modelli e delle tabelle persistenti correnti.

Documenti collegati:

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md)
- [DECISIONS.md](./DECISIONS.md)

## Modelli applicativi

### `Settings`

Definito in `src/docmolder/config.py`.

Contiene:

- token Telegram
- utenti ammessi e admin
- limiti sessione, file, burst upload e job concorrenti
- retention live dello storico job
- runtime dir e database path
- backup SQLite
- soglie alert admin
- timeout Ghostscript

Uso:

- configurazione runtime locale e VPS
- creazione directory operative
- limiti di sicurezza e carico

### `UserSession`

Definito in `src/docmolder/models.py`.

Contiene:

- `user_id`
- lista `SessionFile`
- `status`
- `pending_action`
- `created_at`
- `updated_at`

Uso:

- stato conversazionale corrente
- raccolta file
- wizard di azioni che richiedono input aggiuntivo

### `SessionFile`

Contiene:

- `telegram_file_id`
- `file_name`
- `kind`
- `received_at`

Uso:

- riferimento ai file Telegram caricati
- compatibilita tra file e azioni
- costruzione payload job

### `SupportedAction`

Enum centrale delle azioni supportate:

- immagini verso PDF
- crop immagini
- raddrizzamento foto documento
- scala di grigi
- compressione
- merge
- split
- estrazione, riordino ed eliminazione pagine
- rotazione
- watermark
- auto-orientamento

Uso:

- catalogo azioni
- tastiere e wizard Telegram
- dispatch del processor
- storico job

### `JobPayload`

Contiene:

- file di input
- preset compressione
- gradi rotazione
- selezione pagine
- testo watermark
- preferenze auto-rotate
- layout immagini verso PDF
- preferenza ZIP nello split
- profilo foto documento, quando diverso dal default leggibilita

Uso:

- payload serializzato in SQLite
- input stabile per worker e retry

### `JobRecord`

Contiene:

- `id`
- `user_id`
- `chat_id`
- `reply_to_message_id`
- `action`
- `payload_json`
- `status`
- `created_at`
- `started_at`
- `finished_at`
- `result_message`
- `error_message`
- `processing_mode`
- `input_bytes`
- `output_bytes`
- `duration_ms`
- `rerun_of_job_id`

Uso:

- coda job
- storico personale
- admin console
- metriche processing
- retry e deep link

### `AuditLogEntry`

Contiene:

- `id`
- `event_type`
- `actor_user_id`
- `target_user_id`
- `outcome`
- `detail`
- `created_at`

Uso:

- audit leggero di azioni admin sensibili
- diagnosi operativa senza loggare contenuti documento

### `UserDataDeletionReport`

Contiene:

- sessioni eliminate
- job eliminati
- usage events eliminati
- utente noto eliminato
- metadati `app_meta` eliminati
- voci audit anonimizzate

Uso:

- esito strutturato della cancellazione self-service dei dati live da `/reset`
- log operativo sintetico senza includere contenuti documento o identificativi utente nel messaggio finale

## Tabelle SQLite

Il database corrente e gestito da `SQLiteSessionStore`.

### `sessions`

Campi principali:

- `user_id`
- `status`
- `pending_action`
- `created_at`
- `updated_at`

Contiene la sessione conversazionale corrente.

### `session_files`

Campi principali:

- `user_id`
- `position`
- `telegram_file_id`
- `file_name`
- `kind`
- `received_at`

Contiene i file associati alla sessione corrente.

### `known_users`

Campi principali:

- `user_id`
- `username`
- `first_name`
- `last_name`
- `first_seen_at`

Serve a report admin e osservabilita leggera.

### `usage_events`

Campi principali:

- `user_id`
- `action`
- `created_at`

Serve a metriche aggregate e report.

### `app_meta`

Campi:

- `key`
- `value`

Uso:

- metriche Telegram aggregate
- stato applicativo leggero
- flag operativi come manutenzione o alert recenti
- accesso dinamico utente con chiavi `access:<telegram_user_id>:status`
- stato anti-burst upload con chiavi `upload_burst:<telegram_user_id>`, contenente solo timestamp recenti della finestra di rate limit
- preferenze rapide e preset con chiavi utente come `user_pref:<telegram_user_id>:*` e `user_preset:<telegram_user_id>:*`

Preferenze rapide e preset:

- `user_pref:<telegram_user_id>:compression_preset`
- `user_pref:<telegram_user_id>:split_output`
- `user_pref:<telegram_user_id>:image_pdf_layout`
- `user_pref:<telegram_user_id>:image_pdf_margin_px`
- chiavi tecniche `user_pref:<telegram_user_id>:<preferenza>:last` e `:streak` per promuovere un preset dopo scelte ripetute
- `user_preset:<telegram_user_id>:*` contiene solo impostazioni operative promosse, mai contenuti documento, nomi file o testo estratto

I preset sono usati per scorciatoie inline e default iniziali nei flussi
compatibili. La scelta manuale resta sempre disponibile e sovrascrive il preset
per il job corrente.

### `jobs`

Campi principali:

- `id`
- `user_id`
- `chat_id`
- `reply_to_message_id`
- `action`
- `payload_json`
- `rerun_of_job_id`
- `status`
- `created_at`
- `started_at`
- `finished_at`
- `result_message`
- `error_message`
- `processing_mode`
- `input_bytes`
- `output_bytes`
- `duration_ms`

Uso:

- coda asincrona
- storico personale live
- health e queue admin
- retry

### `audit_log`

Campi principali:

- `id`
- `event_type`
- `actor_user_id`
- `target_user_id`
- `outcome`
- `detail`
- `created_at`

Uso:

- traccia append-only minimale per cambio service mode, retry admin, richieste/revisioni accesso, cancellazioni self-service e future azioni admin sensibili
- supporto a diagnosi e incident response
- non deve contenere payload completi, documenti o contenuti utente
- in caso di cancellazione dati utente, le voci che riferiscono quell'utente vengono anonimizzate azzerando actor/target pertinente e dettaglio

## Stati

### Sessione

- `collecting`
- `ready`

### Job

- `queued`
- `running`
- `succeeded`
- `failed`

I job `running` troppo vecchi vanno considerati sospetti nei controlli operativi.

## Dati non persistenti come prodotto

Non sono prodotto persistente:

- file caricati
- output generati
- directory temporanee job
- copie intermedie di conversione

Questi asset devono restare nel runtime temporaneo e sotto cleanup.

## Retention e cancellazione

Regole correnti:

- lo storico job live dei record conclusi viene potato da `docmolder-reconcile` oltre `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`, default 30 giorni
- la cancellazione completa da `/reset` rimuove i dati live dell'utente: sessione, file di sessione, preferenze, preset, storico job personale, usage events, known user e metadati utente in `app_meta`
- i backup SQLite gia creati non vengono riscritti retroattivamente dalla cancellazione self-service; scadono tramite la retention breve dei backup
- audit e log devono restare sintetici e non contenere documenti, payload completi o contenuti utente

## Evoluzioni possibili

Decisioni aperte:

- metriche admin stabili da mantenere nel tempo
- eventuale migrazione fuori da SQLite se carico o retention crescono
