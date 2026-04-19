# Deploy Da Codex Cloud

Questa guida serve per usare `chatgpt.com` come postazione di lavoro e release senza dipendere dal Mac locale.

## Stato attuale

Il deploy SSH diretto dal runtime Codex cloud verso la VPS non e affidabile, perche l'ambiente cloud non ha connettivita garantita verso `79.72.45.89:22`.

Il percorso consigliato quindi e:

1. Codex cloud prepara e pubblica il codice su GitHub.
2. GitHub Actions esegue il deploy verso la VPS.
3. La VPS applica il flusso standard con `sudo /opt/docmolder/app/deploy/update-vps.sh`.
4. GitHub Actions verifica stato servizio e timer backup.

## Flusso consigliato da mobile

Per deploy ordinari:

1. fai lavorare Codex sul branch desiderato
2. porta la modifica su `main`
3. il workflow GitHub `Deploy VPS` parte automaticamente al push su `main`

Per deploy manuali o di una revisione specifica:

- usa il workflow `Deploy VPS` in GitHub Actions con `workflow_dispatch`
- passa `target_ref` se vuoi deployare un commit o ref specifico

Questo flusso non richiede accesso dal runtime Codex cloud alla rete privata della VPS: il ponte lo fa GitHub Actions.

## Secret richiesti in GitHub Actions

Configura questi secret nel repository GitHub:

- `DOCMOLDER_VPS_HOST`
- `DOCMOLDER_VPS_USER`
- `DOCMOLDER_VPS_PORT`
- `DOCMOLDER_VPS_DEPLOY_CMD`
- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64`
- `DOCMOLDER_VPS_SSH_KNOWN_HOSTS`

Note operative:

- `DOCMOLDER_VPS_HOST` e obbligatorio
- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64` deve contenere la chiave privata SSH in Base64
- `DOCMOLDER_VPS_USER` puo restare `opc`
- `DOCMOLDER_VPS_PORT` puo restare `22`
- `DOCMOLDER_VPS_DEPLOY_CMD` puo restare `sudo /opt/docmolder/app/deploy/update-vps.sh`
- `DOCMOLDER_VPS_SSH_KNOWN_HOSTS` e fortemente consigliato per mantenere il controllo stretto della host key

## Come produrre i secret

Chiave privata in Base64:

```bash
base64 < ~/.ssh/id_ed25519 | tr -d '\n'
```

Host key:

```bash
ssh-keyscan -H <host-vps>
```

## Fallback locale

Gli script `make cloud-prepare-ssh` e `make deploy-vps` restano utili per test locali o ambienti che abbiano connettivita diretta verso la VPS.

Su `chatgpt.com`, pero, il percorso da considerare ufficiale e quello via GitHub Actions.

## Verifiche post deploy

Il workflow GitHub esegue:

- deploy standard `update-vps.sh`
- controllo `systemctl status docmolder --no-pager`
- controllo `systemctl status docmolder-db-backup.timer --no-pager`

Per smoke test applicativi, continua a seguire [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
