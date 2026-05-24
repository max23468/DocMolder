# Toolchain DocMolder

Questa pagina rende leggibile la toolchain effettiva di DocMolder. Le istruzioni
operative restano in [LOCAL_DEV.md](./LOCAL_DEV.md), [RELEASE_PROCESS.md](./RELEASE_PROCESS.md)
e [VPS_RUNBOOK.md](./VPS_RUNBOOK.md).

## Runtime

| Area | Versione/canale | Fonte |
| --- | --- | --- |
| Python applicativo | `>=3.11` | `pyproject.toml` |
| Python preferito locale/VPS | `3.13` | `Makefile`, `docs/LOCAL_DEV.md`, `docs/VPS_RUNBOOK.md` |
| Python CI | `3.11`, `3.12`, `3.13` | `.github/workflows/ci.yml` |
| Node.js | non applicabile al runtime | nessun `package.json` |
| Database | SQLite locale/VPS | `docs/DATA_MODEL.md`, `docs/VPS_RUNBOOK.md` |
| Runtime servizio | Telegram bot in polling su VPS Linux con `systemd` | `docs/ARCHITECTURE.md`, `docs/VPS_RUNBOOK.md` |

## Package manager e lockfile

- Python: `pip` dentro virtualenv.
- Lockfile Python: non presente; le dipendenze sono vincolate in `pyproject.toml`.
- JavaScript/TypeScript: non applicabile.
- Lockfile JS: non applicabile.

## Dipendenze applicative principali

- `python-telegram-bot`: integrazione Telegram.
- `pydantic` e `pydantic-settings`: configurazione e validazione.
- `pymupdf` e `pypdf`: pipeline PDF.
- `pillow` e `opencv-python-headless`: immagini e raddrizzamento foto documento.

## Tool di sviluppo

| Tool | Versione/canale | Uso |
| --- | --- | --- |
| `ruff` | `0.15.9` | lint/static check |
| `coverage` | `>=7.10.7` | copertura test |
| `build` | `>=1.2.2` | package build |
| `gh` | CLI autenticata locale | PR, issue, Actions e release |
| `make` | sistema locale | comandi standardizzati |

## Tool esterni runtime/VPS

| Tool | Uso |
| --- | --- |
| `Ghostscript` | compressione/conversione PDF quando disponibile |
| LibreOffice Calc | sblocco modifica `.xls` mantenendo formato originale |
| `python3-uno` / `libreoffice-pyuno` | bridge LibreOffice per `.xls` |
| `systemd` | servizio bot, timer backup, alert, reconcile e Duck DNS |
| Nginx | endpoint HTTPS del webhook GitHub privato e sito statico |
| Duck DNS | dominio operativo `docmolder.duckdns.org` |

## Comandi

- setup: `make setup`
- avvio locale: `make run`
- test completo: `make test`
- compilazione/import: `make compile`
- gate completo locale: `bash scripts/ci_verify.sh` o `make ci`
- static/lint: `make ci-static`
- coverage/test CI locale: `make ci-test`
- build package: `make build`
- smoke Telegram: `make smoke-ui`
- maintenance GitHub: `make github-maintenance`
- release sanity: `make release-sanity`
- publish standard PR: `scripts/publish_change.sh "<titolo conventional>"`
- publish docs-only minuscolo: `make publish-docs TITLE="chore(docs): <descrizione>"`
- deploy ordinario: webhook privato GitHub -> VPS
- deploy manuale fallback: `sudo /opt/docmolder/app/deploy/update-vps.sh` sulla VPS

## Release, deploy e verifiche

- `Release Please` è il flusso primario per changelog, tag e GitHub Release.
- Le PR ordinarie non devono modificare `CHANGELOG.md`,
  `.release-please-manifest.json`, `pyproject.toml` version o
  `src/docmolder/__init__.py`.
- Il deploy ordinario passa dal webhook privato GitHub -> VPS; GitHub Actions
  operative (`Deploy VPS`, `Rollback VPS`, `VPS Check`) restano manuali o
  fallback espliciti.
- Per cambi solo documentali non rilasciabili non sono previsti tag, GitHub
  Release o deploy VPS.

## Eccezioni e guardrail

- Il manifest resta `>=3.11` anche se sviluppo operativo e VPS preferiscono
  Python `3.13`; non introdurre sintassi o dipendenze incompatibili con `3.11`
  senza decisione esplicita.
- Su VPS non sostituire `/usr/bin/python3`: usare un interprete `3.13`
  side-by-side e virtualenv isolata.
- Non introdurre runtime web-first, API pubbliche o storage documentale
  permanente senza ADR o decisione di prodotto.
- Non committare segreti, `.env`, documenti utente, output temporanei o backup.
