# Decisioni Aperte

Decisioni non ancora prese che influenzano prossime fasi, roadmap o policy operative.

Questo documento non e una checklist di task: raccoglie scelte da chiarire prima di implementare cambi che aumentano perimetro, rischio o complessita.

## Dati e retention

- decidere se i backup SQLite debbano avere un percorso di export o restore piu guidato per manutenzione

## Prodotto

- decidere se e quando trasformare eventuali esplorazioni OCR non pubbliche in una feature utente dichiarata
- decidere se in futuro introdurre localizzazione inglese o altre lingue oltre all'italiano-first della 1.x iniziale

## Operativita

- decidere se introdurre alert esterni oltre agli alert Telegram admin
- decidere il livello minimo di smoke test post-deploy da considerare bloccante
- decidere eventuali soglie definitive per coda, job stuck, failure rate, runtime dir, disco, load, RAM, job/giorno, utenti attivi e dimensione DB dopo osservazione in produzione
- decidere quando SQLite smette di essere accettabile per volume, concorrenza o retention sulla base delle soglie iniziali della Fase 13

## Sicurezza

- decidere policy formale di rotazione del token Telegram
- decidere se separare ancora di piu backup, runtime e log su filesystem
- decidere se redigere una procedura di incidente con template minimale
- decidere se limitare ulteriormente nomi file o messaggi utente nei log

## GitHub e release

- decidere se rendere obbligatori ulteriori check GitHub oltre alla CI corrente
- decidere se introdurre CodeQL quando la superficie cresce
- decidere se documentare una review periodica mensile per Dependabot, secret scanning e workflow failed
