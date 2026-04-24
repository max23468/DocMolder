# Task Packet Codex

Usa questo formato quando una chat coordinatore assegna lavoro a un sub-agente o a un'altra istanza Codex.

Il packet deve essere breve, concreto e autosufficiente. Se il lavoro e ambiguo, chiarisci prima lo scope invece di delegare.

## Template

```markdown
## Task
<obiettivo specifico e risultato atteso>

## Contesto
- Repo: /Users/Matteo/Documents/DocMolder
- Branch/worktree: <branch o worktree assegnato>
- Area: <telegram | processing | session_store | deploy | docs | tests | altro>
- Documenti da leggere: <docs rilevanti>

## Ownership
- Puoi modificare: <file/moduli/responsabilita>
- Non toccare: <file/moduli/responsabilita fuori scope>
- Altri agenti attivi: <righe rilevanti da docs/AGENT_COORDINATION.md>

## Vincoli
- Mantieni DocMolder Telegram-first e dentro il perimetro di docs/DECISIONS.md.
- Non introdurre dipendenze senza consenso esplicito.
- Non loggare contenuti dei documenti utente.
- Non revertire modifiche non tue.

## Verifiche richieste
- <test mirati o comandi>
- <eventuale check docs/deploy/release>

## Handoff atteso
- File toccati
- Comportamento cambiato
- Check eseguiti
- Rischi residui
- Prossimo passo consigliato
```

## Checklist coordinatore

- Il task e indipendente dal lavoro gia in corso.
- L'ownership e disgiunta da quella di altri agenti.
- Il sub-agente puo lavorare senza decisioni prodotto aperte.
- Il formato di handoff e chiaro.
- Il coordinatore resta responsabile dell'integrazione finale.
