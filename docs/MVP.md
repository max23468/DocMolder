# Specifica MVP

Questa pagina fissa il perimetro del primo MVP di `DocMolder` in modo operativo.

## Dentro MVP

- Bot Telegram come interfaccia principale
- Accesso limitato a utenti in whitelist
- Italiano come lingua primaria dell'interfaccia
- Sessione temporanea per utente con piu file inviati in messaggi successivi
- Creazione PDF da immagini
- Compressione PDF su richiesta
- Conversione PDF in scala di grigi
- Unione di piu PDF
- Azione manuale per ruotare PDF
- Correzione orientamento immagini tramite metadati EXIF
- Persistenza sessioni su SQLite
- Cancellazione dei file temporanei a fine elaborazione

## Fuori MVP

- OCR
- Supporto gruppi Telegram
- Accesso pubblico senza whitelist
- Dashboard web
- Storico lavori per l'utente
- Storage permanente dei file caricati
- Webhook e infrastruttura HTTP pubblica
- Gestione amministrativa da interfaccia
- Estrazione pagine, watermark, firma o modifica avanzata dei PDF

## Tipi di file accettati

- PDF
- JPG
- JPEG
- PNG
- WEBP

## Regole della sessione

- Una sessione appartiene a un singolo utente Telegram
- La sessione raccoglie file inviati in piu messaggi consecutivi
- La sessione scade dopo `DOCMOLDER_SESSION_TTL_MINUTES`
- Il numero massimo di file e limitato da `DOCMOLDER_MAX_SESSION_FILES`
- La sessione viene azzerata dopo un'elaborazione completata con successo
- La sessione puo essere azzerata manualmente con `/reset`
- Se l'utente invia file non compatibili con la sessione corrente, il bot non prova a combinarli automaticamente

## Regole del bot

- Comandi supportati nel MVP:
  - `/start`
  - `/status`
  - `/reset`
- Il bot propone solo azioni compatibili con i file presenti nella sessione
- Se la sessione contiene solo immagini:
  - `Crea PDF da immagini`
  - `Correggi orientamento`
- Se la sessione contiene un solo PDF:
  - `Comprimi PDF`
  - `Scala di grigi`
  - `Ruota pagine`
- Se la sessione contiene piu PDF:
  - `Unisci PDF`
- Se arriva un file non supportato, il bot risponde con un errore semplice e comprensibile

## Regole di output

- `Crea PDF da immagini` restituisce un singolo PDF
- `Comprimi PDF` restituisce un singolo PDF
- `Scala di grigi` restituisce un singolo PDF
- `Unisci PDF` restituisce un singolo PDF
- `Ruota pagine` restituisce un singolo PDF
- `Correggi orientamento`:
  - una sola immagine: restituisce l'immagine corretta
  - piu immagini: restituisce un archivio ZIP

## Regole di errore

- Se non ci sono file nella sessione, il bot invita l'utente a inviare file
- Se il numero massimo di file e stato raggiunto, il bot chiede di usare `/reset`
- Se l'elaborazione fallisce, il bot restituisce un messaggio generico in italiano
- Nel MVP non mostriamo dettagli tecnici degli errori all'utente finale

## Regole tecniche del MVP

- Il bot usa polling
- L'elaborazione gira su una macchina controllata da noi
- Il database e SQLite
- I file temporanei restano su filesystem locale
- La conversione PDF deve avere sempre un fallback affidabile, anche se meno conservativo

## Definizione di pronto

Il MVP e considerato pronto quando un utente autorizzato puo:

1. avviare la chat col bot e ricevere un messaggio iniziale chiaro
2. inviare piu immagini e ottenere un PDF finale
3. inviare un PDF e ottenere una versione compressa
4. inviare un PDF e ottenere una versione in scala di grigi
5. inviare piu PDF e ottenere un PDF unificato
6. inviare un PDF e ruotarlo
7. usare una sessione che sopravvive a un riavvio del bot
8. ricevere messaggi coerenti in italiano durante il flusso principale

## Priorita immediata

Prima del deploy su Oracle dobbiamo:

1. eseguire il primo test reale del bot in locale
2. correggere i problemi emersi sul flusso Telegram
3. validare i risultati dei file prodotti
