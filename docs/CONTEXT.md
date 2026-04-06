# Contesto Persistente Progetto: DocMolder

Questo file serve come handoff rapido e persistente per nuove conversazioni con IA o collaboratori tecnici.

Obiettivo:
- evitare di rispiegare ogni volta il progetto
- fornire contesto architetturale e operativo
- riassumere come e dove gira il bot
- chiarire come intervenire in locale e sulla VPS

Ultimo aggiornamento del contesto:
- data di riferimento: `2026-04-06`
- commit locale corrente quando questo file e stato scritto: `e84dadc`

Importante:
- questo file non deve contenere segreti
- puo contenere percorsi, hostname, IP, workflow operativi e metodi di login
- token, chiavi private e credenziali restano fuori dal repository

## 1. Cos'e DocMolder

`DocMolder` e un bot Telegram-first per trasformazioni documentali semplici, guidate e pensate per uso pratico rapido da chat.

L'idea di prodotto e:
- ricevere immagini o PDF via Telegram
- capire il contesto della sessione
- proporre solo le azioni compatibili
- elaborare i file in modo asincrono
- restituire il risultato direttamente in chat

Il progetto non e una web app e non usa webhook pubblici:
- il bot gira in polling
- non serve dominio pubblico
- non serve reverse proxy

## 2. Stato attuale del prodotto

Funzionalita gia presenti:
- creazione PDF da immagini
- creazione PDF da immagini con ritaglio automatico bordi
- creazione PDF da immagini direttamente in scala di grigi
- creazione PDF da immagini con ritaglio bordi + scala di grigi
- conversione PDF in scala di grigi
- compressione PDF
- unione PDF
- rotazione PDF
- correzione orientamento immagini
- supporto a richieste testuali naturali semplici
- pulsante sotto ai PDF generati per convertirli subito in scala di grigi
- supporto multiutente
- code job persistenti
- sessioni utente persistenti su SQLite
- report admin via comando Telegram

Il progetto ha superato la fase MVP e la documentazione usa linguaggio da prodotto attuale, non da fase iniziale.

## 3. Esperienza utente

Flusso standard:
1. l'utente invia immagini o PDF
2. il bot salva i riferimenti ai file nella sessione
3. il bot propone solo azioni compatibili con la sessione
4. l'utente sceglie via pulsanti oppure con testo libero
5. il job va in coda
6. il worker processa il file
7. il bot invia il risultato in chat

Tipi di sessione supportati:
- sole immagini
- un solo PDF
- piu PDF

Le sessioni miste immagini + PDF non sono ammesse per evitare ambiguita.

## 4. Linguaggio naturale supportato

Il bot oggi riconosce richieste testuali semplici quando il contesto della sessione le rende interpretabili.

Esempi funzionanti:
- `fammi un pdf`
- `fammi un pdf in scala di grigi`
- `converti in bianco e nero`
- `comprimi questo pdf`
- `unisci questi pdf`
- `ritaglia i bordi e crea un pdf`
- `ritaglia i bordi e fammi un pdf in scala di grigi`

Note:
- il parsing e euristico, non LLM-based
- la compressione da testo usa come default il livello `medium`
- il testo libero viene interpretato solo se esiste gia una sessione coerente

## 5. Architettura del codice

Entry point:
- [src/docmolder/main.py](/Users/Matteo/Documents/DocMolder/src/docmolder/main.py)

Configurazione:
- [src/docmolder/config.py](/Users/Matteo/Documents/DocMolder/src/docmolder/config.py)

Logica bot Telegram:
- [src/docmolder/bot.py](/Users/Matteo/Documents/DocMolder/src/docmolder/bot.py)

Pipeline documentale:
- [src/docmolder/processing.py](/Users/Matteo/Documents/DocMolder/src/docmolder/processing.py)

Tipi/modelli:
- [src/docmolder/models.py](/Users/Matteo/Documents/DocMolder/src/docmolder/models.py)

Regole di supporto alle azioni e nomi output:
- [src/docmolder/services.py](/Users/Matteo/Documents/DocMolder/src/docmolder/services.py)

Persistenza sessioni/job:
- [src/docmolder/session_store.py](/Users/Matteo/Documents/DocMolder/src/docmolder/session_store.py)

Messaggi:
- [src/docmolder/messages.py](/Users/Matteo/Documents/DocMolder/src/docmolder/messages.py)

Tastiere Telegram:
- [src/docmolder/keyboards.py](/Users/Matteo/Documents/DocMolder/src/docmolder/keyboards.py)

Test:
- [tests/test_processing_pipeline.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_pipeline.py)
- [tests/test_processing_cleanup.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_cleanup.py)
- [tests/test_bot_job_processing.py](/Users/Matteo/Documents/DocMolder/tests/test_bot_job_processing.py)
- [tests/test_rate_limit.py](/Users/Matteo/Documents/DocMolder/tests/test_rate_limit.py)
- [tests/test_session_store.py](/Users/Matteo/Documents/DocMolder/tests/test_session_store.py)

## 6. Componenti principali e responsabilita

### 6.1 `main.py`

Responsabilita:
- carica la configurazione
- costruisce l'applicazione Telegram
- avvia il polling con `allowed_updates=["message", "callback_query"]`

### 6.2 `config.py`

Responsabilita:
- legge variabili ambiente tramite `pydantic-settings`
- definisce i limiti operativi
- garantisce l'esistenza delle cartelle runtime e database

Variabili importanti:
- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_ALLOWED_USER_IDS`
- `DOCMOLDER_ADMIN_USER_IDS`
- `DOCMOLDER_SESSION_TTL_MINUTES`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_MAX_FILE_SIZE_MB`
- `DOCMOLDER_UPLOAD_BURST_LIMIT`
- `DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS`
- `DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER`
- `DOCMOLDER_CLEANUP_INTERVAL_MINUTES`
- `DOCMOLDER_STALE_JOB_RETENTION_HOURS`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

### 6.3 `bot.py`

Responsabilita:
- registra handler Telegram
- gestisce sessioni utente
- valida input e limiti
- mette in coda i job
- gestisce worker job e cleanup scheduler
- interpreta alcune richieste testuali naturali
- invia i risultati finali

Punti chiave:
- `handle_document()` gestisce PDF e immagini come documenti Telegram
- `handle_photo()` gestisce foto Telegram
- `handle_action_callback()` gestisce pulsanti azione standard
- `handle_result_action_callback()` gestisce il pulsante sotto i PDF restituiti
- `handle_menu_text()` gestisce testo libero e menu
- `_process_job()` esegue un job e invia il risultato
- `_send_result()` manda il file in chat

Nota importante di affidabilita:
- e gia stata corretta una regressione in cui il file temporaneo del job veniva cancellato prima dell'invio a Telegram
- oggi il cleanup del job avviene dopo `_send_result()`

### 6.4 `processing.py`

Responsabilita:
- esegue la pipeline documentale vera e propria
- crea cartelle temporanee job
- trasforma immagini in PDF
- elabora PDF esistenti
- effettua fallback conservativi quando una strategia fallisce

Azioni supportate a livello di pipeline:
- `images_to_pdf`
- `images_to_pdf_crop`
- `images_to_pdf_grayscale`
- `images_to_pdf_crop_grayscale`
- `pdf_grayscale`
- `pdf_compress`
- `pdf_merge`
- `pdf_rotate`
- `auto_orient`

Dettagli tecnici importanti:
- `Ghostscript` viene usato quando disponibile per migliorare grigio/compressione
- se `Ghostscript` manca o fallisce, ci sono fallback piu conservativi o raster
- il ritaglio automatico bordi usa un confronto con il colore medio degli angoli dell'immagine per stimare lo sfondo e ricavare il bounding box del contenuto

### 6.5 `services.py`

Responsabilita:
- determina le azioni compatibili per la sessione
- genera nomi output coerenti
- normalizza nomi file

### 6.6 `session_store.py`

Responsabilita:
- gestisce persistenza sessioni utente
- gestisce persistenza job
- costruisce statistiche admin
- permette di riaccodare job incompleti dopo riavvii

Implementazione usata in produzione:
- `SQLiteSessionStore`

Implementazione usata in test:
- `InMemorySessionStore`

### 6.7 `keyboards.py`

Responsabilita:
- definisce i pulsanti inline e la tastiera principale

Punti rilevanti:
- esiste un pulsante per il flusso `Ritaglia bordi e crea PDF`
- esiste un pulsante sotto al PDF risultato per `Converti in scala di grigi`

## 7. Regole di sessione e coda

Regole principali:
- una sessione contiene solo immagini oppure solo PDF
- per immagini il bot puo accumulare piu file prima di proporre l'azione
- per PDF singolo supporta grigio/compressione/rotazione
- per PDF multipli supporta unione
- esistono limiti di burst upload e di numero massimo job attivi per utente

Persistenza:
- le sessioni e i job sono persistiti su SQLite
- all'avvio il bot prova a riaccodare i job incompleti

## 8. File temporanei e retention

Dati non persistenti a lungo termine:
- file input scaricati da Telegram
- cartelle job temporanee
- output intermedi e finali di job

Persistenza prevista:
- il database SQLite resta sulla VPS
- i file temporanei vengono ripuliti
- non e previsto storage permanente dei file utente nel perimetro attuale del prodotto

## 9. Librerie e dipendenze principali

Python:
- `python-telegram-bot`
- `pydantic`
- `pydantic-settings`
- `pillow`
- `pymupdf`
- `pypdf`

Sistema:
- `python3`
- `python3-venv`
- `python3-pip`
- `git`
- `ghostscript`

## 10. Setup locale

Workflow locale rapido:

```bash
make setup
cp .env.example .env
make run
```

Note:
- il repo usa `.venv`
- i test sono stati spesso eseguiti con `.venv/bin/python -m unittest ...`

## 11. Deploy VPS

Documentazione principale:
- [docs/DEPLOY_ORACLE.md](/Users/Matteo/Documents/DocMolder/docs/DEPLOY_ORACLE.md)

Script bootstrap VPS:
- [deploy/oracle-setup.sh](/Users/Matteo/Documents/DocMolder/deploy/oracle-setup.sh)

Service unit:
- [deploy/docmolder.service](/Users/Matteo/Documents/DocMolder/deploy/docmolder.service)

Percorsi standard su VPS:
- codice app: `/opt/docmolder/app`
- virtualenv: `/opt/docmolder/venv`
- dati runtime: `/opt/docmolder/data/runtime`
- env file: `/etc/docmolder/docmolder.env`

Service:
- nome servizio `systemd`: `docmolder`

Exec start:
- `/opt/docmolder/venv/bin/docmolder`

Utente di servizio:
- `docmolder`

## 12. Stato VPS verificato

Questo blocco e temporale e puo cambiare nel tempo.

Stato verificato il `2026-04-06`:
- provider: Oracle Cloud
- OS: Ubuntu `24.04.4 LTS`
- kernel osservato dopo update: `6.17.0-1009-oracle`
- servizio `docmolder`: attivo
- deploy tramite `systemd`
- pacchetti chiave presenti: `python3`, `python3-venv`, `python3-pip`, `git`, `ghostscript`, `ufw`, `unattended-upgrades`
- il bot gira in polling e risponde senza webhook pubblici

## 13. Login VPS e metodi di accesso

Metodo di accesso usato nelle sessioni recenti:
- SSH con chiave privata locale

Host verificato:
- server: `ubuntu@130.110.9.94`

Percorso chiave usato localmente:
- `/Users/Matteo/.ssh/docmolder_oracle`

Esempio comando:

```bash
ssh -i '/Users/Matteo/.ssh/docmolder_oracle' ubuntu@130.110.9.94
```

Note di sicurezza:
- il repository non deve contenere la chiave privata
- questo file puo dire quale chiave viene usata, ma non deve includerne il contenuto
- i segreti applicativi stanno nel file environment della VPS, non nel repo

## 14. Segreti e dati sensibili

Non salvare nel repo:
- token Telegram
- contenuto di `/etc/docmolder/docmolder.env`
- chiavi private SSH
- dump del database con dati utente

Dove stanno i segreti in produzione:
- `/etc/docmolder/docmolder.env`

Permessi previsti:
- owner `root:root`
- permessi `600`

## 15. Comandi operativi utili

Controllo servizio:

```bash
sudo systemctl status docmolder
```

Log live:

```bash
sudo journalctl -u docmolder -f
```

Ultimi log:

```bash
sudo journalctl -u docmolder -n 50 --no-pager
```

Aggiornare il bot dopo un push:

```bash
cd /opt/docmolder/app
sudo -u docmolder git pull --ff-only
sudo -u docmolder /opt/docmolder/venv/bin/pip install -e /opt/docmolder/app
sudo systemctl restart docmolder
```

## 16. Problemi recenti gia risolti

### 16.1 PDF generato ma non inviato

Sintomo:
- l'utente inviava immagini
- il job generava il PDF
- il bot non riusciva a restituirlo

Causa:
- la cartella temporanea del job veniva cancellata prima dell'apertura del file da inviare a Telegram

Fix:
- cleanup spostato a dopo `_send_result()`

### 16.2 Shortcut grigio sul PDF risultato

E stato aggiunto:
- un pulsante sotto al PDF restituito per convertire subito il file in scala di grigi

### 16.3 Linguaggio naturale

E stato aggiunto:
- parsing leggero per richieste testuali contestuali

### 16.4 Ritaglio automatico bordi

E stato aggiunto:
- flusso esplicito e testuale per ritagliare i bordi delle immagini prima di creare il PDF

## 17. Cose da sapere prima di modificare il progetto

- il bot e fortemente centrato su Telegram e sul concetto di sessione
- il file piu delicato e [src/docmolder/bot.py](/Users/Matteo/Documents/DocMolder/src/docmolder/bot.py)
- la pipeline piu delicata e [src/docmolder/processing.py](/Users/Matteo/Documents/DocMolder/src/docmolder/processing.py)
- quando si aggiunge una nuova azione conviene allineare almeno:
  - `SupportedAction` in [src/docmolder/models.py](/Users/Matteo/Documents/DocMolder/src/docmolder/models.py)
  - `infer_supported_actions()` e `build_output_stem()` in [src/docmolder/services.py](/Users/Matteo/Documents/DocMolder/src/docmolder/services.py)
  - tastiere in [src/docmolder/keyboards.py](/Users/Matteo/Documents/DocMolder/src/docmolder/keyboards.py)
  - parsing testo in [src/docmolder/bot.py](/Users/Matteo/Documents/DocMolder/src/docmolder/bot.py) se serve
  - implementazione in [src/docmolder/processing.py](/Users/Matteo/Documents/DocMolder/src/docmolder/processing.py)
  - test

## 18. Test consigliati dopo modifiche

Suite spesso usate:

```bash
.venv/bin/python -m unittest tests.test_bot_job_processing
.venv/bin/python -m unittest tests.test_processing_pipeline tests.test_processing_cleanup tests.test_rate_limit tests.test_session_store
```

## 19. Dove guardare per orientarsi velocemente

Se una nuova IA deve capire il progetto in pochi minuti:
1. leggere questo file
2. leggere [README.md](/Users/Matteo/Documents/DocMolder/README.md)
3. leggere [src/docmolder/bot.py](/Users/Matteo/Documents/DocMolder/src/docmolder/bot.py)
4. leggere [src/docmolder/processing.py](/Users/Matteo/Documents/DocMolder/src/docmolder/processing.py)
5. leggere [docs/DEPLOY_ORACLE.md](/Users/Matteo/Documents/DocMolder/docs/DEPLOY_ORACLE.md)

## 20. Limitazioni attuali

- niente webhook pubblici
- niente UI web
- niente storage permanente file utente
- parsing linguaggio naturale basato su regole, non semantico avanzato
- il ritaglio automatico dei bordi e utile sui casi tipici ma non garantisce perfezione su immagini con sfondi irregolari o contrasti strani

## 21. File correlati utili

- [README.md](/Users/Matteo/Documents/DocMolder/README.md)
- [docs/DEPLOY_ORACLE.md](/Users/Matteo/Documents/DocMolder/docs/DEPLOY_ORACLE.md)
- [docs/ROADMAP.md](/Users/Matteo/Documents/DocMolder/docs/ROADMAP.md)
