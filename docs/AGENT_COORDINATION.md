# Coordinamento Agenti

Questo documento e il registro operativo leggero per coordinare piu chat, agenti o istanze Codex sullo stesso repository.

Non sostituisce roadmap, issue o PR. Serve a evitare conflitti, doppio lavoro e modifiche sovrapposte quando piu istanze lavorano in parallelo.

## Principi

- Una chat principale dovrebbe fare da coordinatore quando il lavoro e ampio o distribuito.
- Ogni agente parallelo deve avere un sotto-task circoscritto, con ownership chiara su file, moduli o responsabilita.
- Ogni filone non banale dovrebbe vivere su una branch o worktree dedicato, preferibilmente `codex/<tema>`.
- La PR, appena esiste, diventa la fonte di verita per diff, check e review.
- Il registro deve restare breve: aggiorna solo cio che aiuta un'altra istanza a capire cosa non rompere.

## Protocollo di avvio

Prima di modifiche non banali, una nuova chat o istanza deve:

1. eseguire `git status --short`;
2. leggere questo documento;
3. controllare branch o PR aperte rilevanti per l'area toccata;
4. dichiarare o annotare l'ownership del lavoro;
5. evitare file e flussi gia presidiati da un'altra istanza, salvo coordinamento esplicito.

Se la nuova chat implica modifiche ai file e il worktree corrente e gia sporco
per modifiche non collegate alla richiesta, non continuare nello stesso
worktree. Considera quel diff gia posseduto da un altro filone, crea
automaticamente una branch/worktree dedicata `codex/<tema>` da una base pulita e
lavora li, mantenendo branch e PR separate. Non usare un semplice
`git switch -c` sopra modifiche non tue: gli uncommitted changes seguirebbero la
nuova branch e i filoni resterebbero mescolati.

Comando consigliato:

```bash
python3 scripts/agent_start.py --area "<area>" --owner "<owner/chat>"
```

## Uso degli agenti

Usa agenti paralleli solo quando il coordinatore puo assegnare lavori indipendenti.

Buoni esempi:

- esplorare una zona del codice e riportare evidenze;
- implementare una patch circoscritta su file assegnati;
- aggiungere test mirati per un comportamento gia deciso;
- fare review del diff o controllare impatto docs/deploy.

Evita agenti paralleli per decisioni di prodotto ambigue, modifiche sullo stesso handler o refactor trasversali senza ownership esplicita.

Per deleghe ripetibili usa:

- [CODEX_TASK_PACKET.md](./CODEX_TASK_PACKET.md) per preparare il brief del sub-agente;
- [CODEX_TASK_PROMPTS.md](./CODEX_TASK_PROMPTS.md) per prompt operativi riutilizzabili.

## Regola anti-conflitto

Se un'altra istanza sta lavorando sulla stessa area:

- non sovrascrivere le sue modifiche;
- non fare cleanup o refactor opportunistici nei file che possiede;
- integra o ribasa solo quando e necessario e comprendi il diff;
- segnala il conflitto nel registro, nella PR o in chat se il coordinamento non e chiaro.

Comando consigliato:

```bash
python3 scripts/agent_parallel_safe.py --owner "<owner/chat>"
```

## Handoff

A fine lavoro, lascia un aggiornamento sintetico con:

- file o moduli toccati;
- comportamento cambiato;
- test o check eseguiti;
- rischi residui;
- prossimo passo consigliato.

Comando consigliato:

```bash
python3 scripts/agent_handoff.py --owner "<owner/chat>" --summary "<cosa fatta>" --check "<check eseguiti>" --risk "<rischi residui>" --next-step "<prossimo passo>"
```

## Registro attivo

Aggiorna questa tabella solo per lavori non banali, paralleli o potenzialmente conflittuali.

| Stato | Owner/chat | Branch/worktree | Area posseduta | Note |
| --- | --- | --- | --- | --- |
| in corso | Codex defer-webhook-restart | codex/defer-webhook-restart | `deploy/install-github-webhook.sh`, docs VPS, test deploy script | Follow-up bot #92: applica aggiornamenti listener con restart differito via systemd-run, senza interrompere il deploy/autorelease in corso. |
| chiuso | Codex fix-release-sudo-env-and-hooks | codex/fix-release-sudo-env-and-hooks / #94 | `scripts/auto_release.py`, `deploy/auto-release.sh`, tests, release VPS | PR #94 mergiata; `docmolder-v0.11.2` generata automaticamente dalla VPS con autorelease OK. |
| chiuso | Codex fix-release-token-split | codex/fix-release-token-split / #93 | `scripts/auto_release.py`, `deploy/auto-release.sh`, release env/docs, VPS release token split | PR #93 mergiata; split token pubblicato. `docmolder-v0.11.1` sistemata con commit/tag/GitHub Release corretti. |
| chiuso | Codex fix-auto-release-followup | codex/fix-auto-release-followup / #92 | `deploy/install-github-webhook.sh`, test deploy script, release VPS | PR #92 mergiata; rilievo bot #91 risolto. Deploy ha creato release locale 0.11.1 ma serve split token per completare GitHub Release automatica. |
| chiuso | Codex fix-vps-auto-release-user | codex/fix-vps-auto-release-user / #91 | `deploy/auto-release.sh`, `deploy/install-github-webhook.sh`, test deploy script, release VPS | PR #91 mergiata; `docmolder-v0.11.0` pubblicata manualmente dopo correzione runtime user. Commento bot tardivo gestito nel follow-up dedicato. |
| chiuso | Codex remove-disabled-workflows | codex/remove-disabled-workflows / #90 | `.github/workflows/*`, docs GitHub/versioning | Rimossi i workflow disattivati con `on: []` che generavano run fallite senza job; PR #90 mergiata, nessuna nuova run Actions sul branch. |
| chiuso | Codex vps-auto-release | codex/vps-auto-release | release automation VPS, webhook deploy/release, docs versioning/deploy | Release automatica senza GitHub Actions pubblicata con #88; webhook deploy/release attivo sulla VPS. |
| chiuso | Codex no-gh-actions-default | codex/no-gh-actions-default | `.github/workflows/*`, `scripts/publish_change.sh`, docs operativi GitHub/release/deploy | Trigger automatici GitHub Actions disattivati per operare con gate locali e deploy manuale; `bash scripts/preflight_publish.sh` e `git diff --check` OK. |
| chiuso | Codex favicon Mac | codex/favicon-mac-fix / ../DocMolder-favicon-mac | `deploy/static/docmolder-site/`, favicon e meta tag del sito statico | Fallback `.ico` aggiunto al root del sito statico e referenziato anche su `privacy.html`; deploy su VPS applicato, `https://docmolder.duckdns.org/favicon.ico` risponde 200 e healthcheck servizio `ok`. |
| chiuso | Codex manual deploy | main / deploy manuale su VPS DocMolder | `docs/AGENTS.md`, `docs/VPS_RUNBOOK.md`, `docs/CODEX_CLOUD_DEPLOY.md`, `docs/AGENT_COORDINATION.md` | Deploy manuale completato sulla VPS DocMolder corretta (`ubuntu@docmolder.duckdns.org` / `130.110.9.94`); runtime bot aggiornato, sito statico e HTTPS ripristinati, verifiche HTTP/HTTPS e healthz OK. |
| chiuso | Codex privacy-duckdns-completion | main / #85 | `deploy/static/docmolder-site/`, Duck DNS deploy assets, VPS docs | Pagina privacy/dati live, Duck DNS reso riproducibile da repo e deploy manuale completato; Actions evitate con `[skip ci]`, health/Telegram/Duck DNS verificati via SSH. |
| chiuso | Codex duckdns-static-site | codex/duckdns-https-ops | `deploy/static/docmolder-site/`, `deploy/install-static-site.sh`, deploy VPS static site, docs ops | Mini sito statico DocMolder pubblicato su HTTPS e aggiornato per bot pubblico `@docmolder_bot`; verifiche desktop/mobile, asset brand e healthz OK; niente proxy runtime DocMolder. |
| chiuso | Codex duckdns-https-ops | codex/duckdns-https-ops | `docs/VPS_RUNBOOK.md`, `docs/DECISIONS.md`, `scripts/ops_report.py`, VPS nginx/certbot DocMolder vhost | HTTPS statico attivo su `docmolder.duckdns.org`, rinnovo Certbot e VPS Check verificati; nessun proxy runtime DocMolder. |
| chiuso | Codex latest-bot-comments | codex/fix-manual-ci-base | `.github/workflows/ci.yml` | Corretto commento bot tardivo su PR #78: base diff workflow_dispatch allineata a merge-base main; verificato con static/preflight mirati. |
| chiuso | Codex manual-ci-only | codex/manual-ci-only | `.github/workflows/ci.yml`, docs GitHub/release | CI resa manuale-only con input `full_tests`; verificato con `bash scripts/ci_static_verify.sh origin/main`, classificatore e `git diff --check`. |
| chiuso | Codex late review comments | codex/address-late-review-comments / #74 | Commenti Codex tardivi su PR #67/#70/#71: `processing.py`, publish/preflight scripts, test mirati | Fix pubblicato con #74, release `docmolder-v0.9.1` e Deploy VPS completati; post-merge bot check puliti su #74/#75. |
| chiuso | Codex phase-7 | codex/phase-7-robustness-performance | Fase 7 robustezza VPS e performance: health/monitoring, cleanup, batch pesanti, performance immagini, docs operative | Fase chiusa con `bash scripts/ci_verify.sh`; diff deploy-relevant, al publish seguire preflight/PR/deploy VPS. |
| chiuso | Codex gestione commenti bot | codex/codex-github-ops-integrations | review bot aperte: CI/publish, deploy wrapper, bot rerun, processing foto, Telegram messaging, git utils | Fix locali applicati e verificati con `bash scripts/ci_verify.sh`; thread GitHub storici restano aperti finche non vengono risolti su GitHub. |

## Template nuova riga

```markdown
| in corso | <chat/owner> | <branch o worktree> | <file/moduli/responsabilita> | <stato, check, rischi, PR> |
```
