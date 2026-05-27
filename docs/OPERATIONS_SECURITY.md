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
- `DUCKDNS_TOKEN` in `/etc/docmolder/duckdns.env`, se Duck DNS è gestito dalla VPS
- token release GitHub in `/etc/docmolder/release.env`, se auto-release VPS è abilitata
- eventuali credenziali o token di deploy/VPS fuori repo

Regole:

- non committare `.env` reali
- non incollare token in issue, PR, log o documentazione
- limitare permessi del file env in produzione
- non salvare copie superflue del file env fuori dai backup amministrativi controllati
- non passare token release a `sudo --preserve-env` o in argomenti CLI: usare il flusso `deploy/auto-release.sh` con env-file temporaneo

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

## Sostituzione in incidente

Nel flusso hardening corrente la sostituzione credenziali è trattata come misura
di risposta rapida a incidente, non come attività ricorrente ordinaria.

Procedura minima in incidente:

1. applicare la sostituzione del token Telegram nel runtime in modo controllato
2. aggiornare file env in produzione
3. riavviare `docmolder`
4. verificare health e smoke Telegram minimo

## Incident response minima

In caso di incidente:

1. isolare se il problema riguarda deploy, configurazione, Telegram, pipeline o storage
2. fermare il servizio se c’è rischio di leak o corruzione dati
3. preservare log e database solo quanto necessario alla diagnosi
4. sostituire credenziali coinvolte se c’è sospetto leak
5. ripristinare da backup solo dopo aver validato il backup scelto
6. annotare la correzione in documentazione operativa se cambia il modo corretto di gestire il servizio

## Rischi aperti

- SQLite locale e adatto al perimetro corrente ma non a crescita importante
- alerting esterno non è ancora formalizzato
- le soglie definitive di crescita e saturazione vanno ancora validate con dati reali di produzione

## Hardening operativo coordinato Atlas (2026-05-27)

Questa sezione aggiorna lo stato hardening operativo per il flusso senza rotazione segreti.

### Stato e rischio
- Rischio iniziale: medio-alto.
- Stato attuale: in esercizio con hardening operativo già applicato per VPS e workflow.
- Rotazione segreti: **non inclusa**.

### Verifiche rapide
- Branch operativo dedicata `codex/hardening-operativo-2026-05-27`.
- `.env` reale non tracciato (`.env.example` presente).
- Segreti citati in workflow/docs solo come riferimenti e non inline nel codice.
- Audit e backup documentati e operativi.

### Azioni concrete in corso
- Mantenimento webhook/secret GitHub nel sistema runtime (mai in repo).
- Pull/checks su backup, release e webhook documentati in `VPS_RUNBOOK.md`/`CODEX_CLOUD_DEPLOY.md`.
- Retention breve e cleanup dei job/backup già in esercizio.

### Rischi residui da monitorare
- Evoluzione del bot e nuove integrazioni rispetto alle policy di accesso.
- Coerenza tra decisioni runtime e pratica quotidiana dell’admin.
