# DocMolder

`DocMolder` è un bot Telegram-first per trasformazioni documentali semplici e guidate.

L'utente invia file al bot, sceglie l'azione desiderata e riceve l'output direttamente in chat.

## Obiettivi del progetto

- Esperienza molto semplice via Telegram
- Supporto multiutente
- Elaborazione asincrona delle operazioni
- Retention breve dei file temporanei

## MVP previsto

- Creazione PDF da immagini
- Conversione PDF in scala di grigi
- Compressione PDF solo su richiesta
- Unione PDF
- Rotazione manuale pagine
- Correzione automatica orientamento per immagini
- Sessioni temporanee per raccogliere più file in messaggi successivi

La specifica operativa del MVP è in [`docs/MVP.md`](docs/MVP.md).

## Flusso utente

1. L'utente invia uno o più file.
2. Il bot riconosce il contesto della sessione.
3. Il bot propone solo azioni compatibili con i file ricevuti.
4. L'utente sceglie l'azione con pulsanti inline.
5. Il bot elabora e restituisce il risultato.
6. I file temporanei vengono cancellati automaticamente.

## Sicurezza operativa

- Nessun salvataggio permanente dei file utente nel MVP
- Pulizia automatica delle cartelle temporanee
- Limiti su dimensione file e numero di allegati da introdurre o rifinire prima di un uso piu ampio

## Stato attuale

Questo repository contiene già una prima implementazione funzionante del flusso:

- configurazione dell'applicazione
- bot Telegram di base
- gestione persistente delle sessioni su SQLite
- tastiere e messaggi iniziali
- caricamento dei file da Telegram
- creazione PDF da immagini
- unione PDF
- conversione PDF in scala di grigi
- compressione PDF con livelli semplici
- azione manuale per ruotare PDF
- correzione orientamento immagini

## Nota sul motore PDF attuale

La pipeline PDF è stata resa più conservativa rispetto allo scaffold iniziale.

Compressione:

- livello `Leggera`: ottimizzazione lossless della struttura PDF
- livello `Media`: ottimizzazione conservativa con tentativo di ricompressione delle immagini mantenendo il PDF nativo
- livello `Forte`: prova prima una compressione conservativa e usa la rasterizzazione solo come soluzione di ripiego

Scala di grigi:

- se sul server è disponibile `Ghostscript`, il bot prova una conversione più fedele alla struttura del PDF
- se `Ghostscript` non è disponibile, usa una soluzione visiva di ripiego che garantisce l'output ma può perdere testo ricercabile, layer o metadati avanzati

Questo ci permette di preservare meglio il contenuto nativo dei PDF quando l'ambiente lo consente, senza rinunciare a una soluzione di ripiego affidabile.

## Avvio locale

1. Crea un ambiente virtuale Python.
2. Installa le dipendenze con `pip install -e .`
3. Copia `.env.example` in `.env`
4. Inserisci il token del bot e le altre variabili ambiente necessarie
5. Avvia con `docmolder`

## Deploy Oracle

Per il deploy su Oracle VPS con Ubuntu, vedi [`docs/DEPLOY_ORACLE.md`](docs/DEPLOY_ORACLE.md).

## Variabili ambiente

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_ALLOWED_USER_IDS` facoltativa
- `DOCMOLDER_ADMIN_USER_IDS` facoltativa
  gli admin ricevono un messaggio privato dal bot al primo accesso di ogni nuovo utente
- `DOCMOLDER_DEFAULT_LANGUAGE`
- `DOCMOLDER_SESSION_TTL_MINUTES`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

## Prossimi passi suggeriti

1. Aggiungere una coda delle operazioni e stati avanzati
2. Introdurre retention e cleanup schedulato
3. Introdurre `Ghostscript` o strumenti equivalenti nel runtime di deploy
4. Gestire limiti, rate limit e osservabilità
5. Introdurre test automatici sui flussi principali

## Monitoraggio admin

Se configuri `DOCMOLDER_ADMIN_USER_IDS`, l'admin puo usare anche:

- `/admin` per vedere un riepilogo rapido di utenti, nuovi accessi, operazioni completate e sessioni attive
