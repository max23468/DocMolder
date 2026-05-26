# Allineamento GitHub per DocMolder (solo maintainer)

Questa guida raccoglie setup e pratiche per mantenere il repository il più possibile "GitHub-native", pur restando un progetto gestito da una sola persona.

## 1) Struttura repository consigliata

Elementi già presenti o introdotti:

- `README.md` chiaro su obiettivi e avvio rapido
- `SECURITY.md` per policy vulnerabilità
- `docs/` per runbook, decisioni e roadmap
- `.github/workflows/ci.yml` per gate PR prudente e test manuali completi via `workflow_dispatch`
- `.github/workflows/dependabot-auto-merge.yml` per automerge prudente delle PR Dependabot dopo CI riuscita
- `.github/workflows/github-maintenance.yml` per report mensile leggero
- `.github/workflows/codex-pr-comments.yml` per sincronizzare la issue `Codex feedback inbox`
- `.github/workflows/release-sanity.yml` per controlli manuali su metadata release
- `.github/dependabot.yml` per aggiornamenti dipendenze
- `.github/ISSUE_TEMPLATE/` per bug/feature standardizzati
- `.github/pull_request_template.md` per PR coerenti

Non aggiungere un workflow separato `pr-title.yml`: il titolo PR è già validato
dal job `PR policy` dentro `.github/workflows/ci.yml`, tramite
`scripts/check_pr_policy.py`. Duplicare quel controllo creerebbe due gate con lo
stesso scopo.

Per un maintainer unico questa struttura riduce il carico cognitivo quando torni sul progetto dopo settimane.

## 2) Impostazioni GitHub repository (consigliate)

Configura da **Settings**:

1. **General → Pull Requests**
   - abilita "Automatically delete head branches".
2. **Branches → Branch protection (main)**
   - se disponibile sul piano/account, richiedi PR prima del merge, linear history e status check `CI result`.
   - non rendere obbligatori i singoli job condizionali della CI: usa solo `CI result`.
3. **Actions → General**
   - consenti solo actions verificate (GitHub + verified creators) per ridurre rischio supply-chain.
4. **Security → Code security and analysis**
   - abilita secret scanning e Dependabot alerts.

Se branch protection non è disponibile, considera questi workflow come guardrail operativi e non come enforcement assoluto: aiutano a intercettare errori, ma non sostituiscono la disciplina del flusso PR.

Su repository privati senza GitHub Code Security/GHAS, la Dependency Review Action
non è disponibile: abilita la repository variable
`DOCMOLDER_ENABLE_DEPENDENCY_REVIEW=true` solo dopo aver attivato la feature sul
repo.

## 3) Flusso operativo consigliato (solo maintainer)

Anche da solo conviene mantenere un mini-flusso PR:

1. branch feature (`feat/...`, `fix/...`)
2. commit piccoli e coesi
3. PR verso `main` con titolo Conventional Commits
4. squash merge dopo verifiche locali rilevanti e `CI result` verde sulla PR non draft
5. lasciare release, changelog e tag alla Release PR generata da `Release Please`
6. usare i workflow deploy solo come fallback manuali espliciti

Regola pratica: `main` non si usa per push diretti. Anche da solo, lavora sempre con branch dedicato + PR + squash merge.
Eccezione operativa: per modifiche minuscole, solo documentali e a basso rischio (`chore(docs):`, limitate a `AGENTS.md`, `README.md` o `docs/**`), il maintainer può pubblicare direttamente da `main` con `make publish-docs TITLE="chore(docs): <descrizione>"`, che esegue preflight/check mirati e salta branch/PR.

Vantaggi principali:

- storico decisioni più chiaro;
- rollback più semplice;
- minor rischio di rompere deploy con commit diretti su `main`;
- versioni e GitHub Releases allineate senza doppia manutenzione manuale.

Questa non è una preferenza soft: per DocMolder il flusso ufficiale resta PR squashate verso `main`, salvo la scorciatoia documentale esplicita descritta sopra. Con budget Actions ripristinato, `CI result` è il guardrail remoto prudente da richiedere sulle PR non draft.

Regola aggiuntiva fondamentale:

- le PR ordinarie non devono toccare `CHANGELOG.md`, `.release-please-manifest.json`, il campo `version` di `pyproject.toml` o `src/docmolder/__init__.py`;
- quei file vengono aggiornati solo dalla Release PR generata da `Release Please` o da manutenzione esplicita del flusso;
- se compaiono in una PR normale, la PR va corretta prima del merge;
- per il dettaglio operativo della policy, fai sempre riferimento a [VERSIONING.md](./VERSIONING.md).

Regola commenti Codex:

- usa la issue `Codex feedback inbox` come backlog globale dei commenti del Codex connector bot;
- non mantenere file Markdown/JSON committati per lo stato dei commenti;
- prima di ready/merge controlla sia la inbox sia la PR corrente con `scripts/check_codex_bot_comments.py --pr <numero> --fail`;
- quando restano azioni aperte, indicare in chat il prossimo passo concreto: fix nella PR corrente, follow-up dedicato o falso positivo motivato.

## 4) Convenzioni leggere ad alto rendimento

- Label minime: `bug`, `enhancement`, `chore`, `docs`, `infra`.
- Milestone solo se hai una release pianificata.
- Usa Issues anche personali come backlog, evitando TODO sparsi nel codice.
- Mantieni `CHANGELOG.md` come changelog ufficiale di release.
- Usa `docs:` solo per documentazione davvero rilasciabile; per housekeeping documentale preferisci `chore:`.

## 5) Integrazioni opzionali (quando servono)

Per non complicare troppo in fase iniziale, abilita solo se c'è beneficio chiaro:

- **CodeQL**: opzionale, solo se vuoi riattivarlo esplicitamente in una finestra di budget.
- **Release Please**: attivo su push a `main` per versioning, changelog e GitHub Releases.
- **Dependabot auto-merge**: attivo solo per aggiornamenti Dependabot conservativi e dopo `CI` riuscita.
- **Deploy workflow**: utile solo come fallback esplicito; il percorso automatico di deploy usa webhook VPS e hook locali.

## 6) Checklist rapida di igiene GitHub

- verifiche locali rilevanti eseguite prima del merge
- Dependabot attivo
- Template issue/PR presenti
- Policy sicurezza presente
- Documentazione operativa aggiornata (`docs/`)
- Nessun segreto nel repository
