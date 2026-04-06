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

- [tests/test_processing_pipeline.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_pipeline.py)
  copre la pipeline documentale, compresi casi PDF e immagini, PDF vuoti o corrotti, documenti multipagina, strutture pagina insolite e flussi grayscale da immagini
- [tests/test_bot_job_processing.py](/Users/Matteo/Documents/DocMolder/tests/test_bot_job_processing.py)
  copre i flussi del bot, la coda job e varie interazioni utente
- [tests/test_processing_cleanup.py](/Users/Matteo/Documents/DocMolder/tests/test_processing_cleanup.py)
  copre la pulizia delle cartelle temporanee dei job
- [tests/test_rate_limit.py](/Users/Matteo/Documents/DocMolder/tests/test_rate_limit.py)
  copre i limiti di upload e di job concorrenti
- [tests/test_session_store.py](/Users/Matteo/Documents/DocMolder/tests/test_session_store.py)
  copre persistenza, statistiche admin, stato dei job e metriche tecniche aggregate

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

## Quando aggiungere test

Aggiungi o estendi test quando cambi:

- regole su azioni supportate per sessione
- fallback della pipeline PDF
- logica di cleanup
- payload dei job
- messaggi o callback che cambiano il flusso utente
