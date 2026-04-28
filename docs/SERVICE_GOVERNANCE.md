# Governance del Servizio

Regole minime di esercizio di `DocMolder` come bot Telegram-first pubblico, con controlli admin e limiti operativi.

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
- pubblico e raggiungibile da `https://t.me/docmolder_bot`
- pensato per chat private con il bot
- utilizzabile senza allow-list quando `DOCMOLDER_ALLOWED_USER_IDS` non e configurata
- restringibile agli utenti ammessi via configurazione o approvati tramite flusso admin in chat
- amministrabile dagli user id in `DOCMOLDER_ADMIN_USER_IDS`
- ospitabile su singola VPS Linux con `systemd`
- best-effort, senza SLA formale

Il bot non offre storage documentale permanente: riceve file, li trasforma e restituisce l'output.

## Uso pubblico 1.x

Dalla linea `1.x`, il bot puo essere considerato pubblicamente utilizzabile su
Telegram, ma con un perimetro intenzionalmente prudente:

- accesso pubblico tramite `@docmolder_bot` e sito statico di ingresso
- uso consigliato in chat privata, per trasformazioni documentali puntuali
- servizio best-effort, senza SLA, piano commerciale o promessa di
  disponibilita continua
- carico atteso basso o moderato, protetto da limiti su file, sessioni, burst
  upload e job concorrenti
- possibilita di passare temporaneamente a modalita ristretta con
  `DOCMOLDER_ALLOWED_USER_IDS` o manutenzione se abuso, carico o incidenti lo
  richiedono

La 1.x stabilizza il contratto attuale, non apre automaticamente una fase di
promozione pubblica ampia. Prima di campagne, onboarding massivo o uso con dati
sensibili ricorrenti serve ancora:

- monitoraggio operativo sufficiente a capire saturazione, errori e abuso

Sono gia presenti:

- procedura self-service per cancellazione completa dei dati live da `/reset`
- pruning automatico e policy formale per lo storico job live
- testi bot e sito statico allineati su privacy, retention, limiti e uso best-effort
- preset automatici leggeri per impostazioni operative ricorrenti, cancellabili con `/reset`

Scelta operativa 1.x:

- mantenere una postura di soft launch pubblico
- mini-promozioni controllate sono possibili dopo Fase 10, mantenendo basso il volume atteso
- rimandare una promozione piu ampia a dopo l'osservabilita minima della Fase 13
- mantenere l'italiano come lingua prodotto primaria nella 1.x iniziale

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
- `/reset` cancella sessione, preferenze rapide e preset leggeri dell'utente

### Preferenze e preset

Retention:

- le preferenze rapide conservano solo l'ultima impostazione operativa scelta
- i preset vengono promossi automaticamente dopo scelte ripetute compatibili
- preset e preferenze riguardano compressione, output split e layout immagini verso PDF
- non contengono contenuti documento, nomi file, testo estratto o profili documentali

### Job e storico

Retention:

- storico leggero dei job nel database finche utile a `/history`, console admin e diagnosi
- nessuna promessa di conservazione permanente

- retention massima live predefinita di 30 giorni per job conclusi, configurabile via env
- pruning automatico dei job vecchi tramite reconcile

### Backup SQLite

Retention:

- backup giornalieri verificati quando il timer VPS e abilitato
- retention breve secondo `DOCMOLDER_SQLITE_BACKUP_RETENTION_DAYS`
- i backup possono contenere metadati utente e job, quindi vanno trattati come dati sensibili
- la cancellazione self-service dei dati live non riscrive retroattivamente i backup gia creati; i dati eventualmente presenti nei backup scadono tramite la retention breve dei backup

## Cancellazione dati

Percorsi correnti:

- `/reset` pulisce la sessione utente corrente
- la cancellazione completa self-service e esposta dentro `/reset`, con conferma inline obbligatoria, e rimuove dati live dell'utente come sessione, preferenze rapide, preset, storico job personale e metadati utente noti
- in modalita ristretta il primo messaggio di un utente non autorizzato registra una richiesta di accesso; l'admin puo approvare o rifiutare dalla console inline
- cleanup job rimuove file temporanei
- restore o manutenzione SQLite restano operazioni amministrative

Regole:

- la cancellazione completa riguarda i dati live, non i backup storici gia creati
- log e audit devono registrare solo eventi sintetici, senza contenuti documentali
- `/reset` deve distinguere il reset leggero dalla cancellazione completa dei dati
- i preset restano opzionali: ogni wizard deve lasciare visibile la scelta manuale

## Limiti operativi dichiarati

Limiti principali configurabili:

- `DOCMOLDER_MAX_FILE_SIZE_MB`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_UPLOAD_BURST_LIMIT`
- `DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS`
- `DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER`
- `DOCMOLDER_JOB_HISTORY_RETENTION_DAYS`
- `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- `DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX`
- `DOCMOLDER_HEALTH_*` per soglie operative di VPS, coda, disco, load, RAM, backup e runtime

Il servizio puo rifiutare o rimandare lavorazioni troppo pesanti per proteggere VPS, coda e utenti.

## Incident response minima

In caso di problema:

1. verificare `systemctl status docmolder`
2. leggere log recenti con `journalctl`
3. controllare la console `/admin` se Telegram e raggiungibile
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
