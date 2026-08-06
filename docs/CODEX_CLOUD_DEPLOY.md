# Deploy Da Codex Cloud

Questa guida serve per usare `chatgpt.com` come postazione di lavoro e release senza dipendere dal Mac locale.

## Stato attuale

La VPS corretta di DocMolder è `docmolder.duckdns.org` (host operativo della macchina), non altri host del perimetro personale. Il deploy SSH diretto dal runtime Codex cloud verso la VPS non è affidabile, perché l'ambiente cloud non ha connettività garantita verso la macchina.

Nel flusso standard con GitHub Actions prudente, il percorso consigliato è:

1. Codex cloud prepara e pubblica il codice su GitHub.
2. La PR non draft verso `main` passa `CI result` e `codex-review` sull'HEAD esatto.
3. Il maintainer mergea la PR e lascia che il webhook privato GitHub -> VPS lanci il controller root-owned `/usr/local/sbin/docmolder-update-vps`.
4. Se la PR richiede un rilascio, completa la procedura release manuale documentata da una copia pulita del `main`.
5. La procedura release manuale documentata crea changelog, tag e GitHub Release; il webhook VPS deploya anche il commit di release.
6. Le verifiche operative si eseguono via SSH diretto o con i comandi locali del repo.

## Flusso consigliato da mobile

Per deploy ordinari, il default operativo è il webhook privato GitHub -> VPS:

1. fai lavorare Codex sul branch desiderato
2. porta la modifica su `main` quando serve pubblicarla
3. lascia che il webhook GitHub esegua il deploy, oppure aggiorna la VPS manualmente con `sudo /usr/local/sbin/docmolder-update-vps deploy origin/main` se il webhook non è disponibile

Per deploy manuali:

- usa il webhook privato o il controller root-owned per la revisione corrente di `main`
- usa `Rollback VPS` solo per uno SHA completo già appartenente alla storia di `main`
- usa `VPS Check` solo se vuoi verificare stato servizio, timer, disco e healthcheck senza copiare file

Il deploy automatico su `main` non usa GitHub Actions. I cambi solo documentali, test, changelog, issue template, istruzioni agent o workflow GitHub non attivano deploy; se serve comunque aggiornare la VPS dopo uno di quei cambi, usa il percorso manuale sulla VPS.

Questo flusso non richiede accesso dal runtime Codex cloud alla rete privata della VPS: il ponte lo fa il webhook GitHub verso la VPS.

### Rete di sicurezza: timer di auto-deploy

Il webhook è immediato ma non ha ritentativi: se una consegna fallisce (VPS
irraggiungibile o listener giù al momento del push), quel commit non verrebbe mai
deployato. Per questo la VPS esegue anche il controller root-owned
`/usr/local/sbin/docmolder-update-vps` da un timer systemd
(`docmolder-autodeploy.timer`, ~ogni 10 min): confronta il commit deployato
(`HEAD` del checkout) con `origin/main` e, se il checkout è rimasto indietro,
applica l’aggiornamento — con **rollback** automatico al commit
precedente se il deploy fallisce. Webhook e timer sono serializzati dallo stesso
lock in `update-vps.sh`, quindi non possono sovrapporsi.

Verifiche utili sulla VPS:

```bash
systemctl list-timers docmolder-autodeploy.timer --all
sudo journalctl -u docmolder-autodeploy.service --since "-2 days"
```

## Secret richiesti per il webhook

Configura questi valori sulla VPS in `/etc/docmolder/github-webhook.env`:

- `DOCMOLDER_GITHUB_WEBHOOK_SECRET`
- `DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY`
- `DOCMOLDER_GITHUB_WEBHOOK_BRANCH`
- `DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT`
- `DOCMOLDER_RELEASE_GITHUB_TOKEN` è stato rimosso dalla macchina VPS nel flusso attuale.

Note operative:

- `DOCMOLDER_GITHUB_WEBHOOK_SECRET` deve combaciare con il secret del webhook GitHub
- `DOCMOLDER_GITHUB_WEBHOOK_REPOSITORY` dovrebbe restare `max23468/DocMolder`
- `DOCMOLDER_GITHUB_WEBHOOK_BRANCH` dovrebbe restare `main`
- `DOCMOLDER_GITHUB_WEBHOOK_DEPLOY_SCRIPT` deve restare `/usr/local/sbin/docmolder-update-vps`
- in questa fase non sono previsti automatismi release aggiuntivi lato VPS; i permessi token sono documentati solo per i flussi ufficiali previsti da procedura release manuale documentata.

## Fallback locale

Gli script `make cloud-prepare-ssh` e `make deploy-vps` restano utili per test locali o ambienti che abbiano connettività diretta verso la VPS.

Su `chatgpt.com`, il percorso da considerare ufficiale è il webhook GitHub quando la VPS è configurata; il deploy manuale sulla VPS resta il fallback operativo.

## Verifiche post deploy

Il webhook GitHub esegue:

- validazione del push e dello SHA corrente di `origin/main`
- aggiornamento del checkout e delle dipendenze come utente `docmolder` tramite
  il controller root-owned
- eventuale fallback esterno di release non è attivo nel flusso standard
- restart del solo servizio noto e smoke check come utente `docmolder`

Per smoke test applicativi, continua a seguire [docs/SMOKE_TESTS.md](./SMOKE_TESTS.md).
