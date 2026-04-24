# Governance del Servizio

Regole minime di esercizio di `DocMolder` come bot Telegram-first con accesso controllato.

## Scopo

Questo documento fissa:

- perimetro del servizio
- dati trattati
- retention minima
- cancellazione dati
- limiti dichiarati

Descrive il servizio reale corrente, non un assetto futuro teorico.

## Modello di servizio

Il bot e oggi:

- servizio Telegram-first
- pensato per chat private con il bot
- utilizzabile dagli utenti ammessi via configurazione o approvati tramite flusso admin in chat
- amministrabile dagli user id in `DOCMOLDER_ADMIN_USER_IDS`
- ospitabile su singola VPS Linux con `systemd`
- best-effort, senza SLA formale

Il bot non offre storage documentale permanente: riceve file, li trasforma e restituisce l'output.

## Perimetro prodotto

Il prodotto e:

- utility documentale guidata
- trasformazione rapida di PDF e immagini
- esperienza conversazionale semplice
- servizio operativo con coda, admin console e retention breve

Il prodotto non e:

- archivio documentale
- editor PDF generalista
- suite OCR completa
- piattaforma collaborativa
- dashboard web-first

## Dati trattati

### Dati Telegram

Il servizio puo trattare:

- `telegram_user_id`
- `telegram_chat_id`
- username e nomi visibili quando forniti da Telegram
- messaggi di comando o callback
- identificativi file Telegram

Uso:

- autorizzazione
- routing risposte
- storico job personale
- metriche operative leggere

### Dati documento

Il servizio tratta:

- file PDF caricati
- immagini caricate
- output PDF, ZIP o file derivati
- metadati tecnici come nome file, dimensioni e tipo

Regole:

- i contenuti dei documenti non vanno loggati
- i documenti non vanno copiati in fixture, report o documentazione
- i file temporanei vanno rimossi a fine job o dal cleanup schedulato
- eventuali esempi di test devono usare file sintetici o dati non sensibili

### Dati job e metriche

Il database puo conservare:

- azione richiesta
- payload tecnico del job
- stato job
- tempi di inizio/fine
- messaggio risultato o errore sintetico
- dimensioni input/output
- durata
- relazione con job rilanciato

Uso:

- storico personale
- retry
- admin console
- health e metriche operative

### Dati amministrativi

Il servizio conserva o calcola:

- utenti noti
- usage events
- metriche Telegram aggregate in `app_meta`
- stato manutenzione
- ultimo alert admin inviato
- informazioni di backup SQLite
- richieste accesso e stato dinamico utente in `app_meta`
- audit log minimale delle azioni admin sensibili

## Retention

### File temporanei

Retention:

- solo per il tempo necessario alla lavorazione
- cleanup schedulato secondo `DOCMOLDER_CLEANUP_INTERVAL_MINUTES`
- job stale oltre `DOCMOLDER_STALE_JOB_RETENTION_HOURS` da considerare rimovibili

### Sessioni

Retention:

- sessione attiva secondo `DOCMOLDER_SESSION_TTL_MINUTES`
- `/reset` cancella sessione e preferenze rapide dell'utente

### Job e storico

Retention:

- storico leggero dei job nel database finche utile a `/history`, `/last`, admin e diagnosi
- nessuna promessa di conservazione permanente
- se la retention job diventa lunga, va definita esplicitamente in roadmap o decisione

### Backup SQLite

Retention:

- backup giornalieri verificati quando il timer VPS e abilitato
- retention breve secondo `DOCMOLDER_SQLITE_BACKUP_RETENTION_DAYS`
- i backup possono contenere metadati utente e job, quindi vanno trattati come dati sensibili

## Cancellazione dati

Percorsi correnti:

- `/reset` pulisce la sessione utente corrente
- `/request_access` registra una richiesta di accesso; l'admin puo approvare, rifiutare, sospendere o riattivare
- `/policy` mostra in chat limiti, retention e regole operative sintetiche
- cleanup job rimuove file temporanei
- restore o manutenzione SQLite restano operazioni amministrative

Decisioni ancora aperte:

- cancellazione completa self-service dello storico utente
- pruning automatico dei vecchi job riusciti o falliti
- retention massima formale dello storico job

## Limiti operativi dichiarati

Limiti principali configurabili:

- `DOCMOLDER_MAX_FILE_SIZE_MB`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_UPLOAD_BURST_LIMIT`
- `DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS`
- `DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER`
- `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- `DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX`
- `DOCMOLDER_HEALTH_*` per soglie operative di VPS, coda, disco, load, RAM, backup e runtime

Il servizio puo rifiutare o rimandare lavorazioni troppo pesanti per proteggere VPS, coda e utenti.

## Incident response minima

In caso di problema:

1. verificare `systemctl status docmolder`
2. leggere log recenti con `journalctl`
3. controllare `/health`, `/queue` e `/metrics` se Telegram e raggiungibile
4. verificare spazio disco, permessi runtime e backup
5. se sono coinvolti dati utente, evitare copie non necessarie e non condividere contenuti documento
6. ripristinare da backup solo se necessario e dopo aver conservato una copia amministrativa dello stato corrente

## Criterio di sufficienza della VPS

La VPS corrente e considerata sufficiente finche:

- numero utenti e basso
- job concorrenti restano entro i limiti configurati
- runtime dir non cresce in modo anomalo
- backup giornalieri sono presenti
- errori Telegram o pipeline non aumentano in modo persistente

Se questi vincoli saltano, le prime aree da rivalutare sono:

- concorrenza job
- retention e cleanup
- storage dati
- alerting esterno
- risorse CPU/RAM/disco
