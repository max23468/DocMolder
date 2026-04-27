# Deploy Da Codex Cloud

Questa guida serve per usare `chatgpt.com` come postazione di lavoro e release senza dipendere dal Mac locale.

## Stato attuale

La VPS corretta di DocMolder e `docmolder.duckdns.org` (host operativo della macchina), non altri host del perimetro personale. Il deploy SSH diretto dal runtime Codex cloud verso la VPS non e affidabile, perche l'ambiente cloud non ha connettivita garantita verso la macchina.

Il percorso consigliato quindi e:

1. Codex cloud prepara e pubblica il codice su GitHub.
2. GitHub Actions sincronizza il repository sulla VPS via SSH.
3. La VPS applica installazione o aggiornamento locale senza fare `git pull`.
4. GitHub Actions verifica stato servizio e timer backup.

## Flusso consigliato da mobile

Per deploy ordinari, il default operativo e manuale:

1. fai lavorare Codex sul branch desiderato
2. porta la modifica su `main` quando serve pubblicarla
3. aggiorna la VPS con `sudo /opt/docmolder/app/deploy/update-vps.sh`

Per deploy tramite GitHub Actions o di una revisione specifica:

- usa il workflow `Deploy VPS` in GitHub Actions con `workflow_dispatch` solo se lo chiedi esplicitamente o se il canale manuale non e disponibile
- passa `target_ref` se vuoi deployare un commit o ref specifico
- usa `VPS Check` se vuoi solo verificare stato servizio, timer, disco e healthcheck senza copiare file
- usa `Rollback VPS` con un tag o SHA precedente se devi ripristinare una revisione gia nota

Il deploy automatico su `main` e limitato a codice applicativo, packaging e asset operativi applicati alla macchina (`src/**`, `deploy/**`, `pyproject.toml`, lock/requirements). Cambi solo documentali, test, changelog, issue template, istruzioni agent o workflow GitHub non attivano deploy; se serve comunque aggiornare la VPS dopo uno di quei cambi, usa il percorso manuale sulla VPS oppure `workflow_dispatch` solo se lo chiedi esplicitamente.

Questo flusso non richiede accesso dal runtime Codex cloud alla rete privata della VPS: il ponte lo fa GitHub Actions.

## Secret richiesti in GitHub Actions

Configura questi secret nel repository GitHub:

- `DOCMOLDER_VPS_HOST`
- `DOCMOLDER_VPS_USER`
- `DOCMOLDER_VPS_PORT`
- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64`
- `DOCMOLDER_VPS_SSH_KNOWN_HOSTS`

Note operative:

- `DOCMOLDER_VPS_HOST` e obbligatorio
- `DOCMOLDER_VPS_SSH_PRIVATE_KEY_B64` deve contenere la chiave privata SSH in Base64
- `DOCMOLDER_VPS_USER` puo restare `opc`
- `DOCMOLDER_VPS_PORT` puo restare `22`
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

- sincronizzazione del repository verso `/opt/docmolder/app`
- installazione o aggiornamento locale con `deploy/install-vps.sh`
- controllo `systemctl status docmolder --no-pager`
- controllo `systemctl status docmolder-db-backup.timer --no-pager`
- smoke test applicativo con `getMe` verso Telegram Bot API eseguito dalla VPS
- riepilogo finale nel job summary con target ref, stato e hint di rollback

Per smoke test applicativi, continua a seguire [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
