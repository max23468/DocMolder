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
sudo systemctl status nginx
sudo journalctl -u docmolder -n 50 --no-pager
sudo systemctl status docmolder-db-backup.timer
sudo systemctl status docmolder-alertcheck.timer
sudo systemctl status docmolder-reconcile.timer
sudo systemctl status docmolder-duckdns.timer
sudo systemctl status certbot-renew.timer
```

Restart:

```bash
sudo systemctl restart docmolder
```

Deploy ordinario dopo merge su `main`:

```bash
sudo systemctl status docmolder-github-webhook.service
sudo journalctl -u docmolder-github-webhook.service -n 50 --no-pager
sudo journalctl -u docmolder -n 50 --no-pager
sudo -u docmolder git -C /opt/docmolder/app rev-parse --short HEAD
```

Il percorso standard e il webhook privato GitHub -> VPS: riceve il push su
`main`, verifica firma/repository/branch e lancia `update-vps.sh`. Dopo un
deploy riuscito puo lanciare anche `deploy/auto-release.sh`.

Deploy manuale mirato, solo come fallback esplicito:

```bash
sudo /opt/docmolder/app/deploy/update-vps.sh
```

Usa `Deploy VPS` in GitHub Actions solo se lo chiedi esplicitamente; il
percorso normale resta webhook VPS, con deploy manuale diretto sulla VPS come
fallback operativo.

Deploy automatico senza Actions:

```bash
sudo systemctl status docmolder-github-webhook.service
sudo journalctl -u docmolder-github-webhook.service -n 50 --no-pager
sudo cat /etc/docmolder/github-webhook.env
```

Il listener webhook riceve gli eventi GitHub su `/webhooks/github/deploy`, verifica la firma HMAC e lancia `update-vps.sh` sul commit ricevuto. L'endpoint di health del listener e `/webhooks/github/healthz`.
Quando il deploy aggiorna unit o script del listener gia attivo, `install-github-webhook.sh` evita il restart dentro al processo che sta servendo il webhook: se gira nel worker scrive un marker in `/run/docmolder-github-webhook/restart-requested`, poi il listener lo consuma a fine job e pianifica il restart con `systemd-run --on-active=1s`. Fuori dal worker il restart e immediato.

Dopo un deploy riuscito il listener lancia anche `deploy/auto-release.sh`. Se `/etc/docmolder/release.env` contiene `DOCMOLDER_AUTO_RELEASE_ENABLED=true`, un `DOCMOLDER_RELEASE_GITHUB_TOKEN` valido per le API GitHub e, quando diverso, un `DOCMOLDER_RELEASE_GIT_TOKEN` valido per push Git HTTPS, la VPS crea automaticamente bump, changelog, tag e GitHub Release quando ci sono commit rilasciabili dal tag precedente. Per usare un nome diverso da `DOCMOLDER_RELEASE_GIT_TOKEN`, imposta `DOCMOLDER_RELEASE_GIT_TOKEN_ENV` al nome della variabile custom. Quando lo script parte da root, i token non vengono passati a `sudo --preserve-env`: vengono letti da una copia temporanea `600` del file release env, rimossa a fine esecuzione, cosi non compaiono nella riga comando del journal. Se il file manca o la flag e disattivata, la fase release viene saltata senza interrompere il deploy.

Per una promozione intenzionale a `1.0.0`, dopo aver completato la checklist
1.0 puoi aggiungere temporaneamente `DOCMOLDER_RELEASE_TARGET_VERSION=1.0.0` a
`/etc/docmolder/release.env`. Rimuovilo subito dopo la release per tornare al
bump automatico standard.

Per configurarlo:

```bash
sudo /opt/docmolder/app/deploy/install-github-webhook.sh
sudo nano /etc/docmolder/github-webhook.env
sudo nano /etc/docmolder/release.env
sudo systemctl restart docmolder-github-webhook.service
```

Il file `/etc/docmolder/github-webhook.env` contiene il secret da copiare nel webhook GitHub. Il file `/etc/docmolder/release.env` contiene invece i token GitHub per push/tag/release automatici e deve restare `root:root` con permessi `600`. Dopo modifiche al flusso release, controlla i log recenti del webhook senza stampare il file env e verifica che non compaiano valori token nelle righe `sudo`.

Backup manuale SQLite:

```bash
sudo /opt/docmolder/app/deploy/backup-db.sh
```

Backup manuale via GitHub Actions, senza deploy, solo se lo chiedi esplicitamente:

```bash
gh workflow run vps-backup.yml --ref main
```

Il percorso normale resta comunque il backup locale con lo script sulla VPS.

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

Aggiornamento Duck DNS manuale:

```bash
sudo /opt/docmolder/bin/update-duckdns.sh
sudo journalctl -u docmolder-duckdns.service -n 20 --no-pager
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

## Dominio pubblico e HTTPS

Il dominio operativo e `docmolder.duckdns.org`; il bot pubblico e raggiungibile da `https://t.me/docmolder_bot`.
Questa e la VPS corretta di DocMolder: usare questo host/dominio per deploy e verifiche, non altri host del perimetro personale. La combinazione SSH da usare e `ssh -i ~/.ssh/docmolder_oracle ubuntu@docmolder.duckdns.org`.

Duck DNS e mantenuto dalla VPS con:

- config root-only: `/etc/docmolder/duckdns.env`
- updater versionato: `deploy/update-duckdns.sh`, installato come `/opt/docmolder/bin/update-duckdns.sh`
- timer: `docmolder-duckdns.timer`

Config minima:

```bash
sudo install -d -m 755 /etc/docmolder
sudo nano /etc/docmolder/duckdns.env
sudo chown root:root /etc/docmolder/duckdns.env
sudo chmod 600 /etc/docmolder/duckdns.env
```

Valori:

```dotenv
DUCKDNS_DOMAIN=docmolder
DUCKDNS_TOKEN=<token-duckdns>
# opzionale: DUCKDNS_IP=<ip-statico>
```

Il timer aggiorna periodicamente il record Duck DNS verso l'IP pubblico della VPS. Per verifica:

```bash
dig +short docmolder.duckdns.org
sudo systemctl status docmolder-duckdns.timer
sudo /opt/docmolder/bin/update-duckdns.sh
```

HTTPS e predisposto con Nginx e Certbot:

- vhost Nginx: `/etc/nginx/conf.d/docmolder.conf`
- sorgente sito statico: `/opt/docmolder/app/deploy/static/docmolder-site/`
- contenuto pubblicato: `/usr/share/nginx/docmolder/`
- certificato: `/etc/letsencrypt/live/docmolder.duckdns.org/`
- rinnovo automatico: `certbot-renew.timer`

Nel perimetro attuale il bot pubblico resta in polling Telegram: il vhost pubblico non proxya verso
un'app DocMolder. Espone il mini sito statico del tool, il link al bot Telegram e `/healthz` statico
per verificare certificato, DNS e reverse proxy senza cambiare il runtime del bot. Il solo endpoint
web esposto oltre al sito e il listener deploy GitHub privato; un endpoint HTTP, webhook Telegram,
API o UI web per il bot richiederebbe una decisione esplicita e un servizio applicativo dedicato.

Il deploy standard aggiorna il sito statico con:

```bash
sudo /opt/docmolder/app/deploy/install-static-site.sh
```

Se il certificato HTTPS e gia presente, lo stesso script genera anche il vhost con proxy al listener webhook locale.

Verifiche rapide:

```bash
curl -I http://docmolder.duckdns.org/
curl -I https://docmolder.duckdns.org/
curl https://docmolder.duckdns.org/healthz
sudo certbot certificates
sudo systemctl status certbot-renew.timer
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
- il timer `docmolder-duckdns.timer` mantiene aggiornato il dominio Duck DNS della VPS
- il timer `certbot-renew.timer` mantiene rinnovabili i certificati HTTPS gestiti da Certbot
- journald viene configurato con retention corta tramite `/etc/systemd/journald.conf.d/docmolder.conf`

## Nota operativa

- VPS come ambiente di esecuzione, non di sviluppo
- evitare modifiche manuali del codice in produzione
