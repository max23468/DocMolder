# Deploy Da Codex Cloud

Questa guida serve per usare `chatgpt.com` come postazione di release e deploy, senza dipendere dal Mac locale.

## Obiettivo

Il flusso e:

1. Codex cloud prepara la chiave SSH dai secret del workspace.
2. Codex cloud apre una sessione SSH verso la VPS.
3. La VPS esegue il deploy standard con `sudo /opt/docmolder/app/deploy/update-vps.sh`.
4. Codex cloud verifica servizio, timer backup e revisione live.

## Secret richiesti nel workspace Codex

Variabili ambiente normali:

- `DOCMOLDER_VPS_HOST`
- `DOCMOLDER_VPS_USER`
- `DOCMOLDER_VPS_PORT`
- `DOCMOLDER_VPS_APP_DIR`
- `DOCMOLDER_VPS_DEPLOY_CMD`

Segreti:

- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64`
- `DOCMOLDER_VPS_SSH_KNOWN_HOSTS`

Note operative:

- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64` deve contenere la chiave privata SSH in Base64.
- `DOCMOLDER_VPS_SSH_KNOWN_HOSTS` dovrebbe contenere la riga `known_hosts` della VPS, cosi il controllo host key resta stretto anche nel cloud.
- Se ometti `DOCMOLDER_VPS_SSH_KNOWN_HOSTS`, lo script usa `StrictHostKeyChecking=accept-new`. Funziona, ma e meno rigoroso.

## Comandi utili

Bootstrap SSH nel terminale cloud:

```bash
make cloud-prepare-ssh
```

Deploy standard di `origin/main`:

```bash
make deploy-vps
```

Deploy di un ref specifico:

```bash
make deploy-vps TARGET_REF=origin/main
```

## Come produrre il secret Base64

Dal Mac locale:

```bash
base64 < ~/.ssh/docmolder_oracle | tr -d '\n'
```

Per la host key:

```bash
ssh-keyscan -H <host-vps>
```

## Verifiche post deploy

Lo script remoto esegue gia:

- deploy standard `update-vps.sh`
- `systemctl is-active docmolder`
- `systemctl status docmolder --no-pager`
- `systemctl status docmolder-db-backup.timer --no-pager`
- `git rev-parse HEAD` dentro `/opt/docmolder/app`

Per smoke test applicativi, continua a seguire [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
