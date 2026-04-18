# Security Policy

## Supported Versions

`DocMolder` non ha attualmente una matrice di versioni rilasciate e supportate a lungo termine.

Per ora consideriamo supportata solo:

| Versione | Supporto security |
| --- | --- |
| `main` su GitHub | Si |
| deploy di produzione corrente derivato da `main` | Si |
| branch, fork o snapshot storici | No |

Se in futuro introdurremo release versionate, aggiorneremo questa sezione con una policy di supporto esplicita.

## Reporting a Vulnerability

Se trovi una vulnerabilita, non aprire una issue pubblica con dettagli sensibili.

Usa invece uno di questi canali:

- GitHub Security Advisories / private vulnerability reporting, se abilitato sul repository
- email diretta al maintainer del progetto

Nel report includi, se possibile:

- descrizione del problema
- impatto atteso
- passaggi per riprodurlo
- eventuale proof of concept
- versione, commit o contesto del deploy coinvolto

## Response Expectations

Obiettivo operativo, senza SLA formale:

- presa in carico iniziale appena ragionevolmente possibile
- conferma di riproduzione o triage iniziale quando il problema e verificabile
- fix o mitigazione coordinata prima della divulgazione pubblica, quando appropriato

## Scope Notes

Per questo progetto sono particolarmente sensibili:

- token Telegram
- segreti e variabili ambiente di deploy
- file utente temporanei
- pipeline PDF e dipendenze native collegate
- configurazione VPS e workflow di aggiornamento
