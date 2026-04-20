# AGENTS.md — Istruzioni operative per Codex (DocMolder)

Questo file definisce linee guida persistenti per gli agenti che lavorano in questa repository.
Scope: intera repository (salvo override in AGENTS.md più specifici in sottocartelle).

## 1) Obiettivo
- Mantenere modifiche piccole, chiare e verificabili.
- Preferire robustezza, leggibilità e semplicità operativa.
- Evitare side-effect non richiesti rispetto alla task dell’utente.

## 2) Principi di lavoro
- Cambia solo ciò che è necessario per la richiesta corrente.
- Prima di modificare: comprendi il contesto e i vincoli esistenti.
- Non introdurre dipendenze nuove senza una motivazione esplicita.

## 3) Stile e qualità del codice
- Segui le convenzioni già presenti nel progetto.
- Usa nomi espliciti e coerenti con il dominio del progetto.
- Evita blocchi troppo grandi: favorisci funzioni piccole e testabili.
- Non aggiungere commenti ridondanti; commenta solo decisioni non ovvie.
- Non inserire `try/catch` attorno agli import.

## 4) Logging, errori e UX operativa
- Gestisci errori in modo esplicito e con messaggi utili.
- Evita leak di dati sensibili in log ed error message.
- Se il fallback è possibile, preferiscilo al crash.
- Mantieni output e messaggi consistenti con il tono del progetto.

## 5) Sicurezza e dati
- Minimizza la persistenza dei file utente e dei temporanei.
- Non committare segreti, token, credenziali o file `.env` reali.
- Rispetta i limiti operativi già presenti (dimensioni, concorrenza, retention).

## 6) Testing e verifica minima
Prima del commit, esegui (quando disponibili):
- test/unit/integration rilevanti alla modifica;
- eventuali linters/formatters del progetto;
- verifica manuale del percorso utente toccato dalla modifica.

Se un check non è eseguibile nell’ambiente corrente, dichiaralo esplicitamente.

## 7) Commit e PR
- Un commit deve essere coeso (una modifica logica principale).
- Messaggi commit chiari, in forma imperativa, con scope quando utile.
- PR con:
  - contesto/problema,
  - soluzione adottata,
  - impatti/rischi,
  - test effettuati.
- Per il versioning, la repository e `release-please`-first:
  - non aggiornare manualmente `CHANGELOG.md`, `.release-please-manifest.json`, `pyproject.toml` o `src/docmolder/__init__.py` nelle PR normali;
  - il bump versione e il changelog di release spettano solo alla Release PR generata dal workflow automatico;
  - se una modifica ordinaria tocca quei file, fermati e riallinea la PR al flusso ufficiale prima del merge.

## 8) Definizione di Done
Una modifica è “done” se:
- risolve la richiesta senza regressioni evidenti;
- mantiene coerenza con architettura e convenzioni esistenti;
- include verifiche eseguite e limiti noti;
- è documentata quanto basta per manutenzione futura.

## 9) Regole pratiche per l’agente
- Non fare refactor estesi non richiesti.
- Non cambiare naming/API pubbliche senza necessità.
- Non modificare file non correlati “già che ci sei”.
- In caso di ambiguità, preferisci la soluzione più semplice e reversibile.
- Nella roadmap, gli item completati vanno rimossi dalla checklist; non usare checkbox segnate come completate per elementi già fatti.
