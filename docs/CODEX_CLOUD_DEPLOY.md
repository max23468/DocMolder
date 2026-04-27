# Deploy Da Codex Cloud

Questa guida serve per usare `chatgpt.com` come postazione di lavoro e release senza dipendere dal Mac locale.

## Stato attuale

La VPS corretta di DocMolder e `docmolder.duckdns.org` (host operativo della macchina), non altri host del perimetro personale. Il deploy SSH diretto dal runtime Codex cloud verso la VPS non e affidabile, perche l'ambiente cloud non ha connettivita garantita verso la macchina.

In modalita standard senza GitHub Actions, il percorso consigliato e:

1. Codex cloud prepara e pubblica il codice su GitHub.
2. Il maintainer lascia che il webhook privato GitHub -> VPS lanci `sudo /opt/docmolder/app/deploy/update-vps.sh` quando il merge raggiunge `main`.
3. La VPS applica installazione o aggiornamento locale senza fare `git pull`.
4. Se la release automatica e abilitata in `/etc/docmolder/release.env`, la VPS crea bump, changelog, tag e GitHub Release senza usare Actions.
5. Le verifiche operative si eseguono via SSH diretto o con i comandi locali del repo.

## Flusso consigliato da mobile

Per deploy ordinari, il default operativo e il webhook privato GitHub -> VPS:

1. fai lavorare Codex sul branch desiderato
2. porta la modifica su `main` quando serve pubblicarla
3. lascia che il webhook GitHub esegua il deploy, oppure aggiorna la VPS manualmente con `sudo /opt/docmolder/app/deploy/update-vps.sh` se il webhook non e disponibile

Per deploy di una revisione specifica:

- usa il webhook privato o il deploy manuale sulla VPS per un commit o ref specifico
- passa `target_ref` a `update-vps.sh` se vuoi deployare un commit o ref specifico
- usa `VPS Check` solo se vuoi verificare stato servizio, timer, disco e healthcheck senza copiare file
- usa `Rollback VPS` solo se devi ripristinare una revisione gia nota

Il deploy automatico su `main` non usa GitHub Actions. I cambi solo documentali, test, changelog, issue template, istruzioni agent o workflow GitHub non attivano deploy; se serve comunque aggiornare la VPS dopo uno di quei cambi, usa il percorso manuale sulla VPS.

Questo flusso non richiede accesso dal runtime Codex cloud alla rete privata della VPS: il ponte lo fa il webhook GitHub verso la VPS.

## Secret richiesti per il webhook

Configura questi valori sulla VPS in `/etc/docmolder/github-webhook.env`:

- `DOCMOLDER_GITHUB_WEBHOOK_SECRET`
- `DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY`
- `DOCMOLDER_GITHUB_WEBHOOK_BRANCH`
- `DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT`
- `DOCMOLDER_RELEASE_GITHUB_TOKEN`, solo in `/etc/docmolder/release.env` se vuoi release automatiche complete senza Actions

Note operative:

- `DOCMOLDER_GITHUB_WEBHOOK_SECRET` deve combaciare con il secret del webhook GitHub
- `DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY` dovrebbe restare `max23468/DocMolder`
- `DOCMOLDER_GITHUB_WEBHOOK_BRANCH` dovrebbe restare `main`
- `DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT` dovrebbe restare `/opt/docmolder/app/deploy/update-vps.sh`
- `DOCMOLDER_RELEASE_GITHUB_TOKEN` deve avere permessi sufficienti a pushare su `main`, creare tag e creare GitHub Release; non va mai committato

## Fallback locale

Gli script `make cloud-prepare-ssh` e `make deploy-vps` restano utili per test locali o ambienti che abbiano connettivita diretta verso la VPS.

Su `chatgpt.com`, il percorso da considerare ufficiale e il webhook GitHub quando la VPS e configurata; il deploy manuale sulla VPS resta il fallback operativo.

## Verifiche post deploy

Il webhook GitHub esegue:

- sincronizzazione del repository verso `/opt/docmolder/app`
- installazione o aggiornamento locale con `deploy/update-vps.sh`
- release automatica con `deploy/auto-release.sh`, solo se abilitata e se ci sono commit rilasciabili
- controllo `systemctl status docmolder --no-pager`
- controllo `systemctl status docmolder-db-backup.timer --no-pager`
- stato operativo del listener nel journal di systemd

Per smoke test applicativi, continua a seguire [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
