# Sviluppo Locale e Testing

Questa guida unifica setup locale e test.

## Setup iniziale

1. Crea virtualenv e installa il progetto:

```bash
make setup
```

2. Crea `.env`:

```bash
cp .env.example .env
```

3. Imposta almeno:

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

Opzionale per funzioni admin:

- `DOCMOLDER_ADMIN_USER_IDS`

## Avvio rapido

```bash
make run
```

## Testing

Gate completo locale:

```bash
bash scripts/ci_verify.sh
```

Il gate usa `ruff`, `coverage` e `build` quando le dipendenze dev sono installate:

```bash
.venv/bin/pip install -e ".[dev]"
```

Suite completa:

```bash
make test
```

Oppure direttamente con unittest:

```bash
.venv/bin/python -m unittest discover -s tests
```

Suite mirate:

```bash
.venv/bin/python -m unittest tests.test_processing_pipeline
.venv/bin/python -m unittest tests.test_bot_job_processing
```

## Check veloci utili

Compilazione/import:

```bash
make compile
```

Git maintenance locale:

```bash
docmolder-fix-git-lock .
docmolder-git-safe -- status --short
```

Publish readiness:

```bash
make publish-doctor
```

Il controllo blocca i casi che rendono rumorosa la pubblicazione: `HEAD detached`, branch indietro o divergente da `origin/main`, file riservati a `release-please`, run GitHub fallite sullo SHA corrente e commenti aperti del Codex connector bot.

## Flusso quotidiano consigliato

1. aggiorna dipendenze solo se necessario (`make setup`)
2. avvia bot in locale (`make run`)
3. esegui test rilevanti (`make test` o suite mirate)

## Note pratiche

- database locale tipico: `./data/runtime/docmolder.db`
- job temporanei: `./data/runtime/jobs`
- per reset locale, puoi svuotare `./data/runtime`
- i test su PDF corrotti possono stampare warning senza fallimento suite
