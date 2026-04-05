# Checklist Progetto

Questa pagina raccoglie in un unico posto le decisioni, lo stato attuale e i prossimi passi di `DocMolder`.

## Visione

- `DocMolder` è un bot Telegram-first per trasformazioni documentali semplici e guidate
- l'utente invia file al bot, sceglie un'azione e riceve l'output direttamente in chat
- il processing gira sulla nostra VPS
- i file non vengono archiviati in modo permanente, ma passano da uno storage temporaneo locale durante l'elaborazione

## Scope Attuale

- bot Telegram come interfaccia principale
- supporto multiutente
- sessioni temporanee per raccogliere più file
- immagini in PDF
- compressione PDF su richiesta
- PDF in scala di grigi
- unione PDF
- rotazione PDF
- correzione orientamento immagini
- onboarding guidato via `/start`, `/help` e menu rapido
- monitoraggio admin base via notifiche primo accesso e comando `/admin`

## Fuori Scope Attuale

- UI web
- OCR
- supporto gruppi Telegram
- dashboard web amministrativa
- storage permanente dei file utente
- webhook e infrastruttura HTTP pubblica
- storico lavori per l'utente
- funzioni PDF avanzate come watermark, firma, estrazione pagine o editing avanzato

## MVP

### Dentro MVP

- bot Telegram come interfaccia principale
- sessione temporanea per utente con più file inviati in messaggi successivi
- creazione PDF da immagini
  output predefinito in formato A4 con margini
- compressione PDF su richiesta
- conversione PDF in scala di grigi
- unione di più PDF
- azione manuale per ruotare PDF
- correzione orientamento immagini tramite metadati EXIF
- persistenza sessioni su SQLite
- cancellazione dei file temporanei a fine elaborazione

### Regole principali

- una sessione appartiene a un singolo utente Telegram
- la sessione scade dopo `DOCMOLDER_SESSION_TTL_MINUTES`
- il numero massimo di file è limitato da `DOCMOLDER_MAX_SESSION_FILES`
- il limite dimensione file è controllato da `DOCMOLDER_MAX_FILE_SIZE_MB`
- non vengono combinate automaticamente sessioni miste con immagini e PDF
- il bot usa polling
- il database è SQLite
- i file temporanei restano su filesystem locale della VPS

## Stato Attuale

### Fatto

- definizione del prodotto Telegram-first
- definizione del perimetro MVP
- repo GitHub privata
- deploy Oracle VPS
- vero clone Git sulla VPS
- deploy key SSH dedicata per la repo privata
- dati runtime separati dal codice in `/opt/docmolder/data/runtime`
- servizio `systemd` attivo
- ambiente locale pronto con Python 3.11 e `.venv`
- test reali base in ambiente VPS
- gestione sessioni persistenti su SQLite
- immagini aggregate correttamente in sessione
- PDF da immagini in formato A4 con margini
- miglioramento testi e onboarding del bot
- accesso pubblico del bot
- notifiche admin al primo accesso di nuovi utenti
- `/admin` con riepilogo base di utenti, accessi e operazioni
- limiti base sui file
- errori PDF più leggibili per file corrotti o protetti

### Parzialmente fatto

- qualità pipeline PDF
  già migliorata rispetto allo scaffold iniziale, ma ancora migliorabile
- monitoraggio admin
  esiste `/admin`, ma non ci sono ancora report periodici o analytics più evoluti
- robustezza edge case PDF
  coperti i casi più comuni, non ancora un catalogo ampio di PDF anomali
- setup locale user-friendly
  l'ambiente locale è pronto, ma l'uso quotidiano da sviluppatore non è ancora documentato in modo completo

## Deploy Oracle

### Fatto

- VM Oracle creata
- Python e dipendenze native installate
- env vars configurate
- repo presente come clone Git
- bot avviato
- `systemd` configurato
- runtime e database spostati fuori dal clone Git

### Struttura attuale

- codice: `/opt/docmolder/app`
- virtualenv: `/opt/docmolder/venv`
- env file: `/etc/docmolder/docmolder.env`
- runtime: `/opt/docmolder/data/runtime`
- database: `/opt/docmolder/data/runtime/docmolder.db`

## Verifica VPS

### Verificato

- il bot risponde correttamente lato servizio
- i log mostrano operazioni reali di download, elaborazione e invio output
- i file temporanei dei job vengono puliti correttamente
- `systemctl restart docmolder` non rompe il servizio
- il bot riparte correttamente dopo restart

### Nota

- la verifica lato server è forte, ma non sostituisce ogni possibile test umano in chat
- i flussi principali risultano comunque già usati realmente e visibili nei log

## Admin

### Attuale

- unico admin: `573159993`
- notifica privata al primo accesso di ogni nuovo utente
- comando `/admin` per riepilogo rapido

### `/admin` mostra

- utenti unici totali
- nuovi utenti ultime 24 ore
- nuovi utenti ultimi 7 giorni
- operazioni completate totali
- operazioni completate ultime 24 ore
- operazioni completate ultimi 7 giorni
- sessioni attive
- dettaglio per tipo di operazione

## Privacy e Storage

- i file inviati dagli utenti toccano la VPS durante l'elaborazione
- non esiste storage permanente dei file utente
- i file vengono scaricati in una cartella di job temporanea
- a fine elaborazione la cartella di job viene rimossa
- il database SQLite conserva solo stato, sessioni e dati minimi necessari al funzionamento

## Prossimi Miglioramenti

### Priorità consigliata

1. tabella `jobs`
2. coda operazioni più robusta
3. cleanup schedulato
4. rate limit
5. admin tools più evoluti
6. pipeline PDF ancora migliore
7. setup locale più user-friendly

### Dettaglio

- `jobs`
  tracciare stato, tempi, esiti ed errori di ogni operazione
- `coda`
  evitare collisioni, migliorare stabilità e serializzare meglio i carichi
- `cleanup schedulato`
  ripulire eventuali residui in caso di crash o interruzioni anomale
- `rate limit`
  proteggere il bot da abuso, flood e uso troppo pesante
- `admin tools`
  top utenti, report periodici, metriche giornaliere, diagnostica più utile
- `pipeline PDF`
  preservare ancora meglio testo, struttura e qualità nei PDF nativi
- `setup locale`
  documentare meglio attivazione del venv, avvio locale e flussi tipici di sviluppo
