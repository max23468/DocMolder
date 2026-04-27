# Allineamento GitHub per DocMolder (solo maintainer)

Questa guida raccoglie setup e pratiche per mantenere il repository il più possibile "GitHub-native", pur restando un progetto gestito da una sola persona.

## 1) Struttura repository consigliata

Elementi già presenti o introdotti:

- `README.md` chiaro su obiettivi e avvio rapido
- `SECURITY.md` per policy vulnerabilità
- `docs/` per runbook, decisioni e roadmap
- `.github/workflows/ci.yml` per test manuali completi via `workflow_dispatch`
- `.github/dependabot.yml` per aggiornamenti dipendenze
- `.github/ISSUE_TEMPLATE/` per bug/feature standardizzati
- `.github/pull_request_template.md` per PR coerenti

Per un maintainer unico questa struttura riduce il carico cognitivo quando torni sul progetto dopo settimane.

## 2) Impostazioni GitHub repository (consigliate)

Configura da **Settings**:

1. **General → Pull Requests**
   - abilita "Automatically delete head branches".
2. **Branches → Branch protection (main)**
   - se disponibile sul piano/account, richiedi PR prima del merge e linear history.
   - evita di rendere obbligatori i workflow Actions: in modalita senza budget il controllo locale con hook Git resta la fonte di verita.
3. **Actions → General**
   - consenti solo actions verificate (GitHub + verified creators) per ridurre rischio supply-chain.
4. **Security → Code security and analysis**
   - abilita secret scanning e Dependabot alerts.

Se branch protection non e disponibile, considera questi workflow come guardrail operativi e non come enforcement assoluto: aiutano a intercettare errori, ma non sostituiscono la disciplina del flusso PR.

## 3) Flusso operativo consigliato (solo maintainer)

Anche da solo conviene mantenere un mini-flusso PR:

1. branch feature (`feat/...`, `fix/...`)
2. commit piccoli e coesi
3. PR verso `main` con titolo Conventional Commits
4. squash merge dopo verifiche locali rilevanti; esegui `CI` manualmente solo quando serve un gate remoto
5. lasciare a `Release Please` la Release PR e il changelog finale solo se riattivi esplicitamente il workflow; altrimenti gestisci release e changelog con il flusso manuale concordato
6. se vuoi automazione deploy senza Actions, configura il webhook privato sulla VPS e i hook locali nel repo

Regola pratica: `main` non si usa per push diretti. Anche da solo, lavora sempre con branch dedicato + PR + squash merge.
Eccezione operativa: per modifiche minuscole, solo documentali e a basso rischio (`chore(docs):`, limitate a `AGENTS.md`, `README.md` o `docs/**`), il maintainer puo pubblicare direttamente da `main` con `make publish-docs TITLE="chore(docs): <descrizione>"`, che esegue preflight/check mirati e salta branch/PR.

Vantaggi principali:

- storico decisioni più chiaro;
- rollback più semplice;
- minor rischio di rompere deploy con commit diretti su `main`;
- versioni e GitHub Releases allineate senza doppia manutenzione manuale.

Questa non e una preferenza soft: per DocMolder il flusso ufficiale resta PR squashate verso `main`, salvo la scorciatoia documentale esplicita descritta sopra. In modalita senza budget GitHub Actions, i guardrail automatici restano spenti e non vanno considerati una dipendenza del flusso base.

Regola aggiuntiva fondamentale:

- le PR ordinarie non devono toccare `CHANGELOG.md`, `.release-please-manifest.json`, il campo `version` di `pyproject.toml` o `src/docmolder/__init__.py`;
- quei file vengono aggiornati solo dalla Release PR automatica;
- se compaiono in una PR normale, la PR va corretta prima del merge;
- per il dettaglio operativo della policy, fai sempre riferimento a [VERSIONING.md](./VERSIONING.md).

## 4) Convenzioni leggere ad alto rendimento

- Label minime: `bug`, `enhancement`, `chore`, `docs`, `infra`.
- Milestone solo se hai una release pianificata.
- Usa Issues anche personali come backlog, evitando TODO sparsi nel codice.
- Mantieni `CHANGELOG.md` come changelog ufficiale di release.
- Usa `docs:` solo per documentazione davvero rilasciabile; per housekeeping documentale preferisci `chore:`.

## 5) Integrazioni opzionali (quando servono)

Per non complicare troppo in fase iniziale, abilita solo se c'è beneficio chiaro:

- **CodeQL**: opzionale, solo se vuoi riattivarlo esplicitamente in una finestra di budget.
- **Release Please**: opzionale, solo se vuoi riattivare il flusso GitHub per versioning, changelog e GitHub Releases.
- **Deploy workflow**: utile solo come fallback esplicito; il percorso automatico senza Actions usa webhook VPS e hook locali.

## 6) Checklist rapida di igiene GitHub

- verifiche locali rilevanti eseguite prima del merge
- Dependabot attivo
- Template issue/PR presenti
- Policy sicurezza presente
- Documentazione operativa aggiornata (`docs/`)
- Nessun segreto nel repository
