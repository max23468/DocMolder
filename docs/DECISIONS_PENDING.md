# Decisioni Aperte

Decisioni non ancora prese che influenzano prossime fasi, roadmap o policy operative.

Questo documento non e una checklist di task: raccoglie scelte da chiarire prima di implementare cambi che aumentano perimetro, rischio o complessita.

## Dati e retention

- decidere retention massima dello storico job in SQLite
- decidere se introdurre pruning automatico per job riusciti, falliti e molto vecchi
- decidere se offrire una cancellazione self-service completa dei dati utente oltre a `/reset`
- decidere quanto rendere visibile all'utente lo storico dei file, restando nel vincolo di non conservare i documenti
- decidere se i backup SQLite debbano avere un percorso di export o restore piu guidato per manutenzione

## Prodotto

- decidere quanto spingere OCR e comprensione documento senza trasformare il bot in suite documentale generalista
- decidere se introdurre preset utente persistenti oltre alle preferenze rapide attuali
- decidere quali scorciatoie conversazionali meritino stato persistente e quali debbano restare inferenze momentanee

## Operativita

- decidere eventuali soglie piu restrittive per coda troppo lunga, job stuck, failure rate, runtime dir, disco, load e RAM dopo osservazione in produzione
- decidere se introdurre alert esterni oltre agli alert Telegram admin
- decidere il livello minimo di smoke test post-deploy da considerare bloccante
- decidere quando SQLite smette di essere accettabile per volume, concorrenza o retention

## Sicurezza

- decidere policy formale di rotazione del token Telegram
- decidere se separare ancora di piu backup, runtime e log su filesystem
- decidere se redigere una procedura di incidente con template minimale
- decidere se limitare ulteriormente nomi file o messaggi utente nei log

## GitHub e release

- decidere se rendere obbligatori ulteriori check GitHub oltre alla CI corrente
- decidere se introdurre CodeQL quando la superficie cresce
- decidere se documentare una review periodica mensile per Dependabot, secret scanning e workflow failed
