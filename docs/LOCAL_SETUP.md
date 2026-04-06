# Setup Locale

Questa guida serve per riprendere `DocMolder` in locale senza dover ricordare ogni volta i passaggi.

## Indice

- [Primo avvio](#primo-avvio)
- [Avvio rapido](#avvio-rapido)
- [Verifiche utili](#verifiche-utili)
- [Flusso quotidiano consigliato](#flusso-quotidiano-consigliato)
- [Note pratiche](#note-pratiche)

## Primo avvio

1. Crea il virtualenv e installa il progetto:

```bash
make setup
```

2. Crea il file ambiente:

```bash
cp .env.example .env
```

3. Apri `.env` e imposta almeno:

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

Se vuoi ricevere funzioni admin in locale, aggiungi anche:

- `DOCMOLDER_ADMIN_USER_IDS`

## Avvio rapido

Per avviare il bot in locale:

```bash
make run
```

## Verifiche utili

Per eseguire i test:

```bash
make test
```

Per controllare rapidamente compilazione e import:

```bash
make compile
```

## Flusso quotidiano consigliato

1. attiva o ricrea il virtualenv con `make setup` se serve
2. aggiorna `.env` solo quando cambiano configurazioni o token
3. prova il bot con `make run`
4. verifica rapidamente con `make test`

## Note pratiche

- il database locale puo stare in `./data/runtime/docmolder.db`
- i file temporanei dei job stanno sotto `./data/runtime/jobs`
- se vuoi ripartire pulito, puoi cancellare il contenuto di `./data/runtime`
