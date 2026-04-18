# Runbook VPS (Oracle Ubuntu)

Guida unica per setup iniziale e gestione operativa in produzione.

## Setup iniziale

Su VPS Ubuntu:

```bash
sudo apt update
sudo apt install -y git
git clone https://github.com/max23468/DocMolder.git
cd DocMolder
chmod +x deploy/oracle-setup.sh
./deploy/oracle-setup.sh
```

Configura ambiente:

```bash
sudo nano /etc/docmolder/docmolder.env
```

Variabili minime:

- `DOCMOLDER_TELEGRAM_TOKEN`
- `DOCMOLDER_RUNTIME_DIR`
- `DOCMOLDER_DATABASE_PATH`
- `DOCMOLDER_SQLITE_BACKUP_DIR`
- limiti runtime (`SESSION_TTL`, `MAX_SESSION_FILES`, burst upload, job concorrenti)
- soglie alert admin (`DOCMOLDER_ADMIN_ALERT_*`) se vuoi renderle piu o meno sensibili

Avvia servizio:

```bash
sudo systemctl enable --now docmolder
sudo systemctl enable --now docmolder-db-backup.timer
sudo systemctl status docmolder
```

## Operazioni quotidiane

Log e stato:

```bash
sudo systemctl status docmolder
sudo journalctl -u docmolder -n 50 --no-pager
sudo systemctl status docmolder-db-backup.timer
```

Restart:

```bash
sudo systemctl restart docmolder
```

Aggiornamento codice dopo push:

```bash
sudo /opt/docmolder/app/deploy/update-vps.sh
```

Backup manuale SQLite:

```bash
sudo /opt/docmolder/app/deploy/backup-db.sh
```

Ripristino da backup SQLite:

```bash
sudo /opt/docmolder/app/deploy/restore-db.sh /percorso/del/backup.db.backup
```

Verifica backup disponibili:

```bash
sudo -u docmolder ls -lah /opt/docmolder/data/runtime/backups
```

## Troubleshooting rapido

Se il bot non parte, controlla prima:

- variabili ambiente
- coerenza virtualenv
- permessi su runtime dir
- presenza/funzionamento Ghostscript

Se i job falliscono:

- controlla log servizio
- verifica input PDF corrotti/protetti
- verifica timeout Ghostscript
- verifica spazio disco e permessi
- controlla se l'admin ha ricevuto alert per failure rate o errori ripetuti

## Retention e dati

- runtime consigliato: `/opt/docmolder/data/runtime`
- database consigliato: `/opt/docmolder/data/runtime/docmolder.db`
- backup consigliati: `/opt/docmolder/data/runtime/backups`
- i file job restano temporanei e vengono puliti dal cleanup schedulato
- il timer `docmolder-db-backup.timer` crea un backup SQLite giornaliero verificato e applica retention corta

## Nota operativa

- VPS come ambiente di esecuzione, non di sviluppo
- evitare modifiche manuali del codice in produzione
