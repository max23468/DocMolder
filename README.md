# DocMolder

`DocMolder` e un bot Telegram-first per trasformazioni documentali semplici, guidate e prevalentemente in italiano.

L'utente invia file al bot, sceglie l'azione desiderata e riceve l'output direttamente in chat.

## Obiettivi del progetto

- Esperienza molto semplice via Telegram
- Linguaggio italiano come default
- Supporto multiutente con whitelist iniziale
- Elaborazione asincrona dei job
- Retention breve dei file temporanei

## MVP previsto

- Creazione PDF da immagini
- Conversione PDF in scala di grigi
- Compressione PDF solo su richiesta
- Unione PDF
- Rotazione manuale pagine
- Correzione automatica orientamento per immagini
- Sessioni temporanee per accumulare piu file in messaggi successivi

## Flusso utente

1. L'utente invia uno o piu file.
2. Il bot riconosce il contesto della sessione.
3. Il bot propone solo azioni compatibili con i file ricevuti.
4. L'utente sceglie l'azione con pulsanti inline.
5. Il bot elabora e restituisce il risultato.
6. I file temporanei vengono cancellati automaticamente.

## Sicurezza operativa

- Accesso limitato a utenti in whitelist
- Nessun salvataggio permanente dei file utente nel MVP
- Pulizia automatica delle cartelle temporanee
- Limiti su dimensione file e numero di allegati da introdurre prima del deploy pubblico

## Stato attuale

Questo repository contiene gia una prima implementazione funzionante del flusso:

- configurazione dell'applicazione
- bot Telegram di base
- whitelist utenti
- session store persistente su SQLite
- tastiere e messaggi iniziali in italiano
- download dei file da Telegram
- creazione PDF da immagini
- unione PDF
- conversione PDF in scala di grigi
- compressione PDF con preset semplici
- rotazione manuale PDF
- correzione orientamento immagini

## Nota sul motore PDF attuale

La pipeline PDF e stata resa piu conservativa rispetto allo scaffold iniziale.

Compressione:

- preset `Leggera`: ottimizzazione lossless della struttura PDF
- preset `Media`: ottimizzazione conservativa con tentativo di ricompressione immagini mantenendo il PDF nativo
- preset `Forte`: prova prima una compressione conservativa e usa la rasterizzazione solo come fallback

Scala di grigi:

- se sul server e disponibile `Ghostscript`, il bot prova una conversione piu fedele alla struttura del PDF
- se `Ghostscript` non e disponibile, usa un fallback visivo che garantisce l'output ma puo perdere testo ricercabile, layer o metadati avanzati

Questo ci permette di preservare meglio il contenuto nativo dei PDF quando l'ambiente lo consente, senza rinunciare a un fallback affidabile.

## Avvio locale

1. Crea un ambiente virtuale Python.
2. Installa le dipendenze con `pip install -e .`
3. Copia `.env.example` in `.env`
4. Inserisci il token del bot e gli utenti autorizzati
5. Avvia con `docmolder`

## Variabili ambiente

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_ALLOWED_USER_IDS`
- `DOCMOLDER_DEFAULT_LANGUAGE`
- `DOCMOLDER_SESSION_TTL_MINUTES`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

## Prossimi passi suggeriti

1. Aggiungere coda job e stati avanzati
2. Introdurre retention e cleanup schedulato
3. Introdurre `Ghostscript` o strumenti equivalenti nel runtime di deploy
4. Gestire limiti, rate limit e osservabilita
5. Introdurre test automatici sui flussi principali
