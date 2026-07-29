# Hardening tecnico-operativo (2026-05-27)

## Rischio iniziale

- Livello: **medio-alto**.
- Stato in questa ondata: **P0/P1 prioritario** su superficie pipeline+runtime.
- Rotazione segreti: **non inclusa** in questa fase (espressamente esclusa).

## Contesto operativo rilevante

- Perimetro Telegram-first con bot operativo e pipeline VPS.
- Servizi runtime: bot Telegram, job di deploy, storage temporanei e backup locale.
- Ambiente deploy: VPS con release automatizzabili.

## Piano tecnico (P0/P1/P2)

### P0

- Hardening pipeline VPS + bot Telegram:
  - confermare che segreti e identificatori operativi risiedono solo in env dedicati o secret store e non in repo;
  - separare runtime/path bot, job deploy e backup con permessi stretti;
  - bloccare commit accidentali di secret pattern e file `.env` nel pre-deploy.
- Eseguire `dry-run` obbligatorio prima di ogni deploy pubblico/produzione.
- Definire artefatto di rilascio stabile e tracciabile (`immutable` dove praticabile), così da poter ricostruire il pacchetto da deploy in modo verificabile.

### P1

- Controllo idempotenza degli script:
  - isolamento percorso di esecuzione;
  - lock/guard per run concorrenti e doppie partite;
  - zero side-effect in riavvio parziale.
- Audit backup/restore con verifica di ripristino periodica e procedure di rollback.
- Rafforzare isolamento percorsi di output e cleanup dei file temporanei.

### P2

- Policy log e anti-leak su allegati:
  - filtrare identificativi sensibili e contenuti documento nei log condivisi;
  - registrare solo metadati operativi minimi;
  - anti-leak su allegati/preview pubblicati.
- Formalizzare soglie di retention e verifica mensile.

## Piano operativo e di governo

### P0/P1

- Ridurre la superficie esposta dai workflow/script locali verso ambienti condivisi.
- Inventario esecuzioni in ogni run con owner, ora, comando e artefatto di rilascio
- Aggiornare `docs/OPERATIONS_SECURITY.md` con runbook “deploy + rollback + guard”.
- Prima di rimettere online una funzionalità nuova, chiudere checklist Telegram/VPS e verificare runbook.

### P2

- Inserire controllo ricorrente (runbook) su lock di deployment, retention e separazione output.
- Allineare eventuali nuove dipendenze runtime nel `docs/VPS_RUNBOOK.md` e `README.md` operativi.

## Audit Codex Security 2026-07-29

Input analizzato: 49 candidati grezzi della prima scansione e 8 gruppi parziali
della seconda. Le scansioni non hanno prodotto finding confermati: ogni
candidato è stato rivalidato sul commit `78beff472c9eff60e8d8cedbc163a9f12aec5d1f`
prima della classificazione.

### Cause confermate e correzioni

- **Confine root/VPS** (candidati 7-11 e gruppi root/deployment): timer e
  listener eseguivano codice sotto `/opt/docmolder` con privilegi root.
  Servizi applicativi ora usano `User=docmolder`, `Group=docmolder` e
  `UMask=0077`; deploy, rollback e timer invocano soltanto il controller
  root-owned `/usr/local/sbin/docmolder-update-vps`, che valida SHA/storia di
  `main` ed esegue checkout, `pip` e smoke come `docmolder`. I workflow non
  copiano né eseguono più il checkout come root. Regressioni:
  `tests.test_deploy_scripts`. Rischio residuo: la prima migrazione di unit,
  sudoers e controller richiede l’installer manuale da una revisione verificata.
- **Input workflow, ref e SSH** (17-22, 42-45, 48-49): valori dispatcher
  interpolati in `sed`, ref arbitrari e first-use host keys erano riproducibili.
  L’aggiornamento env usa Python con argomenti separati, il deploy accetta solo
  lo SHA corrente di `main`, il rollback solo SHA appartenenti alla sua storia
  e tutti i workflow VPS richiedono `known_hosts`. Regressioni:
  `tests.test_deploy_scripts`. Nessun rischio residuo noto nel percorso
  automatico.
- **Workflow GitHub privilegiati** (2, 31, 46-47): il workflow
  `pull_request_target` poteva eseguire lo script della PR e l’identità bot era
  troppo permissiva. Ora usa solo il branch base, limita gli `issue_comment` ad
  associazioni fidate, riconosce due login esatti e non auto-mergea major.
  Regressioni: `tests.test_codex_reports`. Il workflow Dependabot conserva
  token write, ma non esegue codice della PR.
- **Webhook deploy** (3, 5, 15-16 e gruppo health): confermati
  `Content-Length` negativo, stato pubblico verboso, replay e coda illimitata.
  Ora lunghezza e SHA sono validati, il payload non viene conservato, l’health
  espone solo stato minimo e non è pubblicato da Nginx, la coda è limitata e i
  delivery ID sono deduplicati. Il controller rifiuta push diventati obsoleti.
  Regressioni: `tests.test_github_webhook`. La deduplica in memoria è limitata
  agli ultimi 1.000 ID; replay più vecchi restano innocui per il controllo SHA.
- **Isolamento chat Telegram** (4): sessioni indicizzate per utente potevano
  attraversare chat diverse. Il bot ora rifiuta ogni update non privato prima
  degli altri handler. Regressione: `tests.test_bot_lifecycle`. Nessun rischio
  residuo noto nel modello Telegram-first corrente.
- **Budget documenti** (23-35): confermati decode immagini, espansione OOXML,
  download reali/aggregati, range pagina, raster PDF e split senza limiti
  condivisi. Sono stati introdotti budget prima del decode/loop nel processor,
  nel downloader e nell’unlocker OOXML. Regressioni:
  `tests.test_processing_pipeline`, `tests.test_excel_unlock` e
  `tests.test_bot_lifecycle`. I limiti sono intenzionalmente globali per job.
- **Permessi dati** (12-14): database, backup e directory potevano ereditare
  mode permissivi. I file SQLite sono forzati a `0600`, runtime/backup a `0700`
  e i servizi usano `UMask=0077`; `check-perms.sh` verifica anche le directory.
  Regressioni: `tests.test_session_store`, `tests.test_sqlite_backup` e
  `tests.test_deploy_scripts`. Nessun rischio residuo noto sui nuovi file.
- **Log, token e documentazione** (6, 39-40): traceback potevano bypassare il
  filtro, il token Telegram poteva finire negli argomenti processo e il runbook
  suggeriva di stampare un env segreto. Il filtro elimina `exc_info`, il tool
  legge il token solo da env/settings e il runbook usa controlli selettivi.
  Regressione: `tests.test_sensitive_logging`; gli altri controlli sono statici.
- **Filesystem e tooling locale** (41 e gruppi symlink/hook/safe.directory):
  cleanup smoke, sito statico, hook versionati e crescita `safe.directory`
  erano riproducibili. Il cleanup opera solo su asset marcati, il sito rifiuta
  target risolti fuori dal path, gli hook versionati sono rimossi e non viene
  più aggiunta configurazione Git globale. Regressioni:
  `tests.test_smoke_telegram_desktop` e `tests.test_deploy_scripts`.
- **Toolchain CI** (38): dipendenze dev/build erano installate senza hash.
  `requirements-dev.lock`, `requirements-tools.lock` e
  `requirements-build.lock` coprono ora CI, bootstrap e backend di build con
  `--require-hashes`; `make lock-check` verifica tutti i lock e il package
  build disabilita l’isolamento che riscaricherebbe tool mutabili.
  Regressione: `tests.test_deploy_scripts`.
- **Output terminale e paginazione GitHub** (1 e gruppo page limit): titoli PR
  potevano contenere controlli terminale e i primi 100 commenti GraphQL non
  coprivano l’intera PR. I controlli C0/C1 vengono rimossi e i commenti PR/review
  hanno fallback REST paginato. Regressioni: `tests.test_codex_reports`.

### Candidati non confermati come vulnerabilità

- **Profilatore locale senza limiti** (36): `profile_processing_flows.py` è un
  comando operatore locale, non riceve input Telegram o remoto. Non è stato
  aggiunto un limite speculativo.
- **Cancellazione durante un job già avviato** (37): la riproduzione conferma
  che il calcolo può terminare, ma dopo la cancellazione il risultato non viene
  inviato né persistito e la directory job viene rimossa in `finally`; i nuovi
  budget ne limitano anche il costo. È un possibile miglioramento di efficienza,
  non una violazione di cancellazione dati osservata.
