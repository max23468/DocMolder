# Prompt Operativi Codex

Prompt riutilizzabili per lavorare con Codex e sub-agenti su DocMolder.

Sostituisci i placeholder tra `<...>` prima di usarli.

## Esplorazione codice

```text
Repo: /Users/Matteo/Documents/DocMolder.
Leggi AGENTS.md e docs/AGENT_COORDINATION.md. Esplora solo <area/moduli>.
Obiettivo: rispondere a <domanda concreta>.
Non modificare file. Riporta evidenze con path e funzioni rilevanti, rischi e test suggeriti.
```

## Implementazione circoscritta

```text
Repo: /Users/Matteo/Documents/DocMolder.
Leggi AGENTS.md, docs/CONTEXT.md, docs/DECISIONS.md e docs/AGENT_COORDINATION.md.
Task: <obiettivo>.
Ownership: puoi modificare solo <file/moduli>. Non toccare <file/moduli esclusi>.
Implementa direttamente, segui le convenzioni esistenti, non introdurre dipendenze.
Esegui <test/check richiesti>. Handoff finale: file toccati, comportamento cambiato, check, rischi residui.
```

## Test mirati

```text
Repo: /Users/Matteo/Documents/DocMolder.
Verifica <comportamento/flusso> senza refactor non richiesti.
Puoi modificare solo <test file> e, se indispensabile, <file sorgente assegnati>.
Esegui i test mirati e riporta output essenziale, failure e rischio residuo.
```

## Review del diff

```text
Repo: /Users/Matteo/Documents/DocMolder.
Fai review del diff corrente con stance da code review: bug, regressioni, rischi dati utente, test mancanti.
Non modificare file.
Ordina i findings per severità e cita file/linea. Se non trovi problemi, dichiaralo e indica eventuali test gap.
```

## Deploy impact

```text
Repo: /Users/Matteo/Documents/DocMolder.
Valuta solo impatto deploy/release del diff corrente.
Leggi docs/VERSIONING.md, docs/RELEASE_PROCESS.md e docs/VPS_RUNBOOK.md.
Riporta: deploy relevant sì/no, release type consigliato, check pre-merge, check post-deploy, rischi residui.
Non modificare file.
```

## GitHub manutenzione e release

```text
Repo: /Users/Matteo/Documents/DocMolder.
Esegui make github-maintenance e interpreta il report.
Concentrati solo su PR aperte, Release PR, PR Dependabot, alert Dependabot leggibili e run Actions fallite recenti.
Non modificare file senza un task separato; riporta priorità, rischio e prossimo passo.
```

## Observability operations

```text
Repo: /Users/Matteo/Documents/DocMolder.
Esegui make ops-report o, su VPS, python /opt/docmolder/app/scripts/ops_report.py --check-service.
Interpreta health, systemd, backup, runtime, job e prossime azioni.
Non eseguire deploy, restart, restore o comandi sudo distruttivi senza consenso esplicito.
```

## Handoff finale

```text
Genera handoff usando:
python3 scripts/agent_handoff.py --owner "<owner>" --summary "<cosa fatta>" --check "<check>" --risk "<rischio>" --next-step "<prossimo passo>"
Integra nella risposta finale solo le informazioni essenziali.
```
