# Specifica MVP

Questa pagina fissa il perimetro del primo MVP di `DocMolder` in modo operativo.

## Dentro MVP

- Bot Telegram come interfaccia principale
- Sessione temporanea per utente con più file inviati in messaggi successivi
- Creazione PDF da immagini
  - output predefinito in formato A4 con margini
- Compressione PDF su richiesta
- Conversione PDF in scala di grigi
- Unione di più PDF
- Azione manuale per ruotare PDF
- Correzione orientamento immagini tramite metadati EXIF
- Persistenza sessioni su SQLite
- Cancellazione dei file temporanei a fine elaborazione

## Fuori MVP

- OCR
- Supporto gruppi Telegram
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
- La sessione raccoglie file inviati in più messaggi consecutivi
- La sessione scade dopo `DOCMOLDER_SESSION_TTL_MINUTES`
- Il numero massimo di file è limitato da `DOCMOLDER_MAX_SESSION_FILES`
- La sessione viene azzerata dopo un'elaborazione completata con successo
- La sessione può essere azzerata manualmente con `/reset`
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
- Se la sessione contiene più PDF:
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
  - più immagini: restituisce un archivio ZIP

## Regole di errore

- Se non ci sono file nella sessione, il bot invita l'utente a inviare file
- Se il numero massimo di file è stato raggiunto, il bot chiede di usare `/reset`
- Se l'elaborazione fallisce, il bot restituisce un messaggio generico
- Nel MVP non mostriamo dettagli tecnici degli errori all'utente finale

## Regole tecniche del MVP

- Il bot usa polling
- L'elaborazione gira su una macchina controllata da noi
- Il database è SQLite
- I file temporanei restano su filesystem locale
- La conversione PDF deve avere sempre un fallback affidabile, anche se meno conservativo

## Definizione di pronto

Il MVP è considerato pronto quando un utente può:

1. avviare la chat col bot e ricevere un messaggio iniziale chiaro
2. inviare più immagini e ottenere un PDF finale
3. inviare un PDF e ottenere una versione compressa
4. inviare un PDF e ottenere una versione in scala di grigi
5. inviare più PDF e ottenere un PDF unificato
6. inviare un PDF e ruotarlo
7. usare una sessione che sopravvive a un riavvio del bot
8. ricevere messaggi coerenti durante il flusso principale

## Priorita immediata

Prima del deploy su Oracle dobbiamo:

1. eseguire il primo test reale del bot in locale
2. correggere i problemi emersi sul flusso Telegram
3. validare i risultati dei file prodotti
