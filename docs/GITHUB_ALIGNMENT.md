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
- `.github/workflows/codex-review-gate.yml` per lo status `codex-review` sull'HEAD esatto
- controllo release manuale supportato dal flusso release corrente (documentato in `docs/VERSIONING.md`)
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
   - richiedi PR prima del merge, linear history e gli status check `CI result` e `codex-review`.
   - per contesto maintainer singolo mantieni la revisione PR come self-review: non richiedere approvazioni esterne.
   - non rendere obbligatori i singoli job condizionali della CI: usa l'aggregato `CI result` insieme a `codex-review`.
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
4. squash merge dopo verifiche locali rilevanti, `CI result` verde e `codex-review` riuscito sull'HEAD esatto
5. lasciare release, changelog e tag al passaggio manuale con la procedura release manuale documentata
6. usare i workflow deploy solo come fallback manuali espliciti

Regola pratica: `main` non si usa per push diretti. Anche da solo, lavora sempre
con branch dedicato + PR + squash merge; `make publish-docs` applica lo stesso
flusso anche alle modifiche documentali minime.

Vantaggi principali:

- storico decisioni più chiaro;
- rollback più semplice;
- minor rischio di rompere deploy con commit diretti su `main`;
- versioni e GitHub Releases allineate senza doppia manutenzione manuale.

Questa non è una preferenza soft: per DocMolder il flusso ufficiale resta PR squashate verso `main`, salvo la scorciatoia documentale esplicita descritta sopra. `CI result` e `codex-review` sono i guardrail remoti da richiedere sulle PR non draft.

Regola aggiuntiva fondamentale:

- le PR ordinarie non devono toccare `CHANGELOG.md`, `pyproject.toml` (campo `version`) o `src/docmolder/__init__.py`;
- quei file vengono aggiornati dal flusso della procedura release manuale documentata o da manutenzione esplicita del flusso;
- se compaiono in una PR normale, la PR va corretta prima del merge;
- per il dettaglio operativo della policy, fai sempre riferimento a [VERSIONING.md](./VERSIONING.md).

Regola review Codex:

- al primo giro usa la review automatica senza pubblicare richieste;
- dopo ogni nuovo SHA o per un retry pubblica una sola riga `@codex review` e attendi lo status `codex-review` sullo stesso HEAD;
- il workflow osserva solo `chatgpt-codex-connector[bot]` ed esegue codice della default branch fidata;
- prima di ready/merge verifica lo status `codex-review` sull'HEAD corrente;
- quando restano P0/P1 aperti, indicare in chat il fix nella PR corrente; P2/P3 restano advisory.

## 4) Convenzioni leggere ad alto rendimento

- Label minime: `bug`, `enhancement`, `chore`, `docs`, `infra`.
- Milestone solo se hai una release pianificata.
- Usa Issues anche personali come backlog, evitando TODO sparsi nel codice.
- Mantieni `CHANGELOG.md` come changelog ufficiale di release.
- Usa `docs:` solo per documentazione davvero rilasciabile; per housekeeping documentale preferisci `chore:`.

## 5) Integrazioni opzionali (quando servono)

Per non complicare troppo in fase iniziale, abilita solo se c'è beneficio chiaro:

- **CodeQL**: opzionale, attivabile solo in finestre operative dedicate.
- **Release manuale**: procedura release manuale documentata su checkout pulita per versioning, changelog e GitHub Releases.
- **Dependabot auto-merge**: attivo solo per aggiornamenti Dependabot conservativi e dopo `CI` riuscita.
- **Deploy workflow**: utile solo come fallback esplicito; il percorso automatico di deploy usa webhook VPS e hook locali.

## 6) Checklist rapida di igiene GitHub

- verifiche locali rilevanti eseguite prima del merge
- Dependabot attivo
- Template issue/PR presenti
- Policy sicurezza presente
- Documentazione operativa aggiornata (`docs/`)
- Nessun segreto nel repository
