# Deploy su Oracle VPS

Questa guida prepara `DocMolder` per una VPS Oracle con Ubuntu.

## Indice

- [Perche Ubuntu](#perche-ubuntu)
- [Configurazione consigliata](#configurazione-consigliata)
- [Flusso consigliato](#flusso-consigliato)
- [Comandi iniziali](#comandi-iniziali)
- [Variabili da configurare](#variabili-da-configurare)
- [Avvio del servizio](#avvio-del-servizio)
- [Log](#log)
- [Aggiornare il bot dopo un push](#aggiornare-il-bot-dopo-un-push)
- [Note operative](#note-operative)

## Perche Ubuntu

La scelta di Ubuntu e pratica:

- pacchetti di sistema semplici da installare per `python3-venv`, `pip` e `ghostscript`
- `systemd` gia pronto per tenere vivo il bot
- documentazione molto abbondante
- meno attrito per un primo deploy rispetto a distribuzioni piu particolari

Questo non significa che Ubuntu sia l'unica scelta possibile. E la scelta piu lineare per partire.

## Configurazione consigliata

- Oracle Cloud Free Tier
- VM Ubuntu 24.04 LTS
- accesso SSH con chiave
- almeno 1 vCPU e 1-2 GB RAM se disponibili
- disco persistente standard del Free Tier

## Flusso consigliato

1. crea la VM su Oracle
2. entra in SSH
3. clona la repository
4. esegui lo script di installazione
5. compila il file environment
6. avvia il servizio `systemd`
7. testa il bot da Telegram

## Comandi iniziali

Dopo esserti collegato via SSH:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/max23468/DocMolder.git
cd DocMolder
chmod +x deploy/oracle-setup.sh
./deploy/oracle-setup.sh
```

## Variabili da configurare

Apri il file:

```bash
sudo nano /etc/docmolder/docmolder.env
```

Imposta almeno:

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_SESSION_TTL_MINUTES`
- `DOCMOLDER_MAX_SESSION_FILES`
- `DOCMOLDER_UPLOAD_BURST_LIMIT`
- `DOCMOLDER_UPLOAD_BURST_WINDOW_SECONDS`
- `DOCMOLDER_MAX_ACTIVE_JOBS_PER_USER`
- `DOCMOLDER_CLEANUP_INTERVAL_MINUTES`
- `DOCMOLDER_STALE_JOB_RETENTION_HOURS`
- `DOCMOLDER_GHOSTSCRIPT_TIMEOUT_SECONDS`
- `DOCMOLDER_ADMIN_DAILY_REPORT_HOUR`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_DAY`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_HOUR`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`

Se vuoi limitare l'accesso a utenti specifici, puoi aggiungere anche:

- `DOCMOLDER_ALLOWED_USER_IDS`

Se vuoi ricevere una notifica quando un utente usa il bot per la prima volta, puoi aggiungere anche:

- `DOCMOLDER_ADMIN_USER_IDS`

Se vuoi ricevere riepiloghi periodici admin, puoi usare anche:

- `DOCMOLDER_ADMIN_DAILY_REPORT_HOUR`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_DAY`
- `DOCMOLDER_ADMIN_WEEKLY_REPORT_HOUR`

## Avvio del servizio

```bash
sudo systemctl enable --now docmolder
sudo systemctl status docmolder
```

## Log

```bash
sudo journalctl -u docmolder -f
```

## Aggiornare il bot dopo un push

```bash
sudo /opt/docmolder/app/deploy/update-vps.sh
```

Questo script:

- imposta `safe.directory` per l'utente di servizio
- esegue `git fetch`
- riallinea il clone remoto con `git reset --hard origin/main`
- reinstalla il progetto nel virtualenv
- riavvia `docmolder`

Per evitare nuovi disallineamenti:

- non modificare il codice direttamente sulla VPS
- considera la VPS solo come ambiente di esecuzione, non di sviluppo
- se serve un update manuale, usa comunque `fetch + reset --hard origin/main` invece di `git pull --ff-only`

Percorsi consigliati per tenere separati codice e dati:

```env
DOCMOLDER_RUNTIME_DIR=/opt/docmolder/data/runtime
DOCMOLDER_DATABASE_PATH=/opt/docmolder/data/runtime/docmolder.db
```

## Note operative

- Attualmente usiamo polling, quindi non servono dominio pubblico o webhook
- SQLite e file temporanei restano sulla VPS, separati dal clone Git del progetto
- `Ghostscript` viene installato per migliorare la conversione PDF in scala di grigi
- Se in futuro il carico cresce, possiamo spostare database e storage su componenti dedicati
