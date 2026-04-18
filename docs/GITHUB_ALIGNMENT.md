# Allineamento GitHub per DocMolder (solo maintainer)

Questa guida raccoglie setup e pratiche per mantenere il repository il più possibile "GitHub-native", pur restando un progetto gestito da una sola persona.

## 1) Struttura repository consigliata

Elementi già presenti o introdotti:

- `README.md` chiaro su obiettivi e avvio rapido
- `SECURITY.md` per policy vulnerabilità
- `docs/` per runbook, decisioni e roadmap
- `.github/workflows/ci.yml` per test automatici su push/PR
- `.github/dependabot.yml` per aggiornamenti dipendenze
- `.github/ISSUE_TEMPLATE/` per bug/feature standardizzati
- `.github/pull_request_template.md` per PR coerenti

Per un maintainer unico questa struttura riduce il carico cognitivo quando torni sul progetto dopo settimane.

## 2) Impostazioni GitHub repository (consigliate)

Configura da **Settings**:

1. **General → Pull Requests**
   - abilita "Automatically delete head branches".
2. **Branches → Branch protection (main)**
   - richiedi almeno 1 status check (`CI / Python ...`).
   - opzionale ma utile anche da solo: "Require branches to be up to date before merging".
3. **Actions → General**
   - consenti solo actions verificate (GitHub + verified creators) per ridurre rischio supply-chain.
4. **Security → Code security and analysis**
   - abilita secret scanning e Dependabot alerts.

## 3) Flusso operativo consigliato (solo maintainer)

Anche da solo conviene mantenere un mini-flusso PR:

1. branch feature (`feat/...`, `fix/...`)
2. commit piccoli e coesi
3. PR verso `main` con titolo Conventional Commits
4. squash merge solo a CI verde
5. lasciare a `Release Please` la Release PR e il changelog finale

Regola pratica: considera `main` come branch senza push diretti anche se il piano GitHub attuale non permette di imporlo via branch protection sulla repository privata.

Vantaggi principali:

- storico decisioni più chiaro;
- rollback più semplice;
- minor rischio di rompere deploy con commit diretti su `main`;
- versioni e GitHub Releases allineate senza doppia manutenzione manuale.

## 4) Convenzioni leggere ad alto rendimento

- Label minime: `bug`, `enhancement`, `chore`, `docs`, `infra`.
- Milestone solo se hai una release pianificata.
- Usa Issues anche personali come backlog, evitando TODO sparsi nel codice.
- Mantieni `CHANGELOG.md` come changelog ufficiale di release.
- Usa `docs:` solo per documentazione davvero rilasciabile; per housekeeping documentale preferisci `chore:`.
- Mantieni attivo il controllo sul titolo PR per evitare release ambigue.

## 5) Integrazioni opzionali (quando servono)

Per non complicare troppo in fase iniziale, abilita solo se c'è beneficio chiaro:

- **CodeQL**: consigliato se la superficie codice cresce o apri a contributi esterni.
- **Release Please**: consigliato come strada standard per versioning, changelog e GitHub Releases.
- **Deploy workflow**: utile quando il deploy su VPS viene reso completamente idempotente.

## 6) Checklist rapida di igiene GitHub

- CI verde su `main`
- Dependabot attivo
- Template issue/PR presenti
- Policy sicurezza presente
- Documentazione operativa aggiornata (`docs/`)
- Nessun segreto nel repository
