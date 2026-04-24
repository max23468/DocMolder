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
- soglie health (`DOCMOLDER_HEALTH_*`) per coda, job stale, runtime dir, backup, disco, load e RAM
- `DOCMOLDER_IMAGE_PDF_MAX_SOURCE_SIDE_PX` per controllare il downscale preventivo delle immagini molto grandi

Avvia servizio:

```bash
sudo systemctl enable --now docmolder
sudo systemctl enable --now docmolder-db-backup.timer
sudo systemctl enable --now docmolder-alertcheck.timer
sudo systemctl enable --now docmolder-reconcile.timer
sudo systemctl status docmolder
```

## Operazioni quotidiane

Log e stato:

```bash
sudo systemctl status docmolder
sudo journalctl -u docmolder -n 50 --no-pager
sudo systemctl status docmolder-db-backup.timer
sudo systemctl status docmolder-alertcheck.timer
sudo systemctl status docmolder-reconcile.timer
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

Backup manuale via GitHub Actions, senza deploy:

```bash
gh workflow run vps-backup.yml --ref main
```

Healthcheck operativo:

```bash
sudo /opt/docmolder/venv/bin/docmolder-healthcheck --check-service-active --service-name docmolder
```

Report operations completo:

```bash
sudo /opt/docmolder/venv/bin/python /opt/docmolder/app/scripts/ops_report.py --check-service
```

Profilo locale/VPS dei flussi pesanti:

```bash
sudo -u docmolder /opt/docmolder/venv/bin/python /opt/docmolder/app/scripts/profile_processing_flows.py
```

Smoke check post-deploy con retry:

```bash
sudo /opt/docmolder/app/deploy/smoke-check.sh
```

Manutenzione one-shot:

```bash
sudo -u docmolder /opt/docmolder/venv/bin/docmolder-reconcile
```

Timer reconcile:

```bash
sudo systemctl status docmolder-reconcile.timer
sudo journalctl -u docmolder-reconcile.service -n 50 --no-pager
```

Verifica permessi:

```bash
sudo /opt/docmolder/app/deploy/check-perms.sh
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
- il timer `docmolder-alertcheck.timer` esegue un healthcheck operativo ogni 5 minuti
- il timer `docmolder-reconcile.timer` riallinea periodicamente job stale e runtime temporaneo
- journald viene configurato con retention corta tramite `/etc/systemd/journald.conf.d/docmolder.conf`

## Nota operativa

- VPS come ambiente di esecuzione, non di sviluppo
- evitare modifiche manuali del codice in produzione
