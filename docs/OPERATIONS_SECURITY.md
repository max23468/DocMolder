# Sicurezza Operativa

Nota operativa sulla sicurezza corrente di `DocMolder`.

Per dati trattati, retention e cancellazione vedere anche [SERVICE_GOVERNANCE.md](./SERVICE_GOVERNANCE.md).

## Stato corrente

Assetto previsto:

- deploy su VPS Linux con `systemd`
- bot Telegram in polling
- configurazione tramite file env fuori dal repository
- runtime dir dedicata
- SQLite locale con backup verificati
- accesso admin Telegram limitato da `DOCMOLDER_ADMIN_USER_IDS`

## Segreti

Segreti principali:

- `DOCMOLDER_TELEGRAM_TOKEN`
- eventuali credenziali o token di deploy/VPS fuori repo

Regole:

- non committare `.env` reali
- non incollare token in issue, PR, log o documentazione
- limitare permessi del file env in produzione
- ruotare il token Telegram in caso di sospetto leak
- non salvare copie superflue del file env fuori dai backup amministrativi controllati

## Dati utente

Dati sensibili per questo progetto:

- documenti caricati
- output generati
- metadati job riconducibili a un utente Telegram
- backup SQLite
- log che contengono identificativi utente o errori operativi

Regole:

- non loggare contenuti documentali
- non loggare testo watermark o selezioni utente se potrebbero rivelare contenuto sensibile
- non includere documenti reali in test o fixture
- non allegare output utente a report di debug
- rimuovere file temporanei dopo lavorazione o secondo cleanup schedulato

## Log

I log devono essere utili ma minimali.

Consentito:

- `job_id`
- stato job
- azione richiesta
- durata
- dimensioni input/output
- tipo errore
- identificativi Telegram solo quando servono alla diagnosi

Da evitare:

- contenuto dei documenti
- testo integrale di messaggi utente non necessari
- nomi file se contengono dati personali, salvo contesto strettamente locale
- token, path segreti o payload completi

## Backup

Backup SQLite:

- vanno trattati come dati sensibili
- possono contenere metadati utente e storico job
- devono restare nella directory prevista o in backup amministrativi controllati
- devono avere retention corta e verificabile

Restore:

- prima di restore in-place, conservare lo stato corrente se possibile
- dopo restore, verificare avvio servizio e percorso utente minimo
- non usare restore per aggirare bug applicativi senza prima capire la causa

Check permessi operativo:

```bash
sudo /opt/docmolder/app/deploy/check-perms.sh
```

## Permessi e runtime

In produzione:

- runtime dir scrivibile solo dall'utente servizio
- database SQLite e backup non pubblici
- file env leggibile solo dagli utenti necessari
- nessun documento utente servito da web server pubblico

## Rotazione segreti

Ruotare `DOCMOLDER_TELEGRAM_TOKEN` quando:

- viene esposto accidentalmente
- cambia manutentore o accesso alla VPS
- si sospetta compromissione del server
- il token e stato usato in ambienti non controllati

Procedura minima:

1. generare nuovo token lato Telegram
2. aggiornare file env in produzione
3. riavviare `docmolder`
4. verificare health e smoke Telegram minimo
5. revocare o invalidare il token precedente

## Incident response minima

In caso di incidente:

1. isolare se il problema riguarda deploy, configurazione, Telegram, pipeline o storage
2. fermare il servizio se c'e rischio di leak o corruzione dati
3. preservare log e database solo quanto necessario alla diagnosi
4. ruotare segreti se c'e sospetto leak
5. ripristinare da backup solo dopo aver validato il backup scelto
6. annotare la correzione in documentazione operativa se cambia il modo corretto di gestire il servizio

## Rischi aperti

- SQLite locale e adatto al perimetro corrente ma non a crescita importante
- alerting esterno non e ancora formalizzato
- pruning completo dei vecchi job non e ancora definito come policy prodotto
- cancellazione completa self-service dei dati utente e ancora decisione aperta
