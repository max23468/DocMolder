# Testing

Questa guida raccoglie il minimo utile per eseguire e interpretare i test di `DocMolder`.

## Indice

- [Ambiente consigliato](#ambiente-consigliato)
- [Suite principali](#suite-principali)
- [Comandi utili](#comandi-utili)
- [Note pratiche](#note-pratiche)
- [Quando aggiungere test](#quando-aggiungere-test)

## Ambiente consigliato

Usa il virtualenv del progetto:

```bash
.venv/bin/python -m unittest discover -s tests
```

In alternativa:

```bash
make test
```

## Suite principali

- [tests/test_models.py](/Users/Matteo/Documents/DocMolder/tests/test_models.py)
  copre il roundtrip tipizzato dei payload job
- [tests/test_processing_pipeline.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_pipeline.py)
  copre la pipeline documentale, compresi casi PDF e immagini, PDF vuoti o corrotti, documenti multipagina, strutture pagina insolite, flussi grayscale da immagini, timeout `Ghostscript` e operazioni native sulle pagine PDF
- [tests/test_bot_job_processing.py](/Users/Matteo/Documents/DocMolder/tests/test_bot_job_processing.py)
  copre i flussi del bot, la coda job, lo storico lavori e varie interazioni utente
- [tests/test_processing_cleanup.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_cleanup.py)
  copre la pulizia delle cartelle temporanee dei job, inclusi casi di cartella gia assente
- [tests/test_rate_limit.py](/Users/Matteo/Documents/DocMolder/tests/test_rate_limit.py)
  copre i limiti di upload e di job concorrenti
- [tests/test_session_store.py](/Users/Matteo/Documents/DocMolder/tests/test_session_store.py)
  copre persistenza, statistiche admin, stato dei job, metriche tecniche aggregate, meta-informazioni operative e stato conversazionale minimo delle sessioni
- [tests/test_services.py](/Users/Matteo/Documents/DocMolder/tests/test_services.py)
  copre helper trasversali come la generazione dei nomi file in output e l'allineamento tra azioni esposte e catalogo centrale

## Comandi utili

Eseguire solo i test piu vicini alla pipeline:

```bash
.venv/bin/python -m unittest tests.test_processing_pipeline
```

Eseguire solo i test del bot:

```bash
.venv/bin/python -m unittest tests.test_bot_job_processing
```

Eseguire tutta la suite:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Note pratiche

- se usi `python3` di sistema invece del virtualenv, potresti non avere dipendenze come `Pillow` o `python-telegram-bot`
- alcuni test usano PDF volutamente invalidi; messaggi come `invalid pdf header` o `EOF marker not found` possono comparire in output senza indicare un fallimento della suite
- prima di considerare verde una modifica alla pipeline, conviene eseguire almeno i test di `processing` e `bot_job_processing`
- i test sui timeout `Ghostscript` possono produrre una riga di warning nei log senza indicare un fallimento della suite

## Quando aggiungere test

Aggiungi o estendi test quando cambi:

- regole su azioni supportate per sessione
- fallback della pipeline PDF
- logica di cleanup
- payload dei job
- messaggi o callback che cambiano il flusso utente
- storico lavori, dettaglio job o meccanismi di rilancio
