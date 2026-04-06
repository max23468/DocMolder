# Decisioni Progetto

Questo file raccoglie decisioni architetturali e di prodotto gia prese, in forma breve.

## Indice

- [Polling invece di webhook pubblici](#polling-invece-di-webhook-pubblici)
- [Retention breve dei file temporanei](#retention-breve-dei-file-temporanei)
- [Auto-orientamento PDF invece di rotazione manuale come azione primaria](#auto-orientamento-pdf-invece-di-rotazione-manuale-come-azione-primaria)
- [Fallback conservativi nella pipeline PDF](#fallback-conservativi-nella-pipeline-pdf)
- [SQLite come persistenza locale del progetto](#sqlite-come-persistenza-locale-del-progetto)

## Polling invece di webhook pubblici

Decisione:
- il bot gira in polling

Motivazione:
- riduce complessita operativa
- evita dominio pubblico, reverse proxy e endpoint HTTP esposti
- e coerente con un tool Telegram-first a carico contenuto

Conseguenze:
- il deploy e piu semplice
- il bot non dipende da ingress pubblici
- eventuali evoluzioni API-first richiederebbero una decisione nuova

## Retention breve dei file temporanei

Decisione:
- niente storage permanente dei file utente nel perimetro attuale

Motivazione:
- riduce rischio operativo e responsabilita sui dati
- mantiene il prodotto focalizzato su trasformazioni rapide
- semplifica manutenzione e costi

Conseguenze:
- il recupero storico dei file non e disponibile di default
- la pulizia automatica dei job e parte essenziale del sistema

## Auto-orientamento PDF invece di rotazione manuale come azione primaria

Decisione:
- le elaborazioni PDF compatibili correggono automaticamente l'orientamento quando serve

Motivazione:
- semplifica la UX
- riduce la necessita di una scelta tecnica esplicita da parte dell'utente
- copre meglio il caso pratico di PDF con poche pagine fuori orientamento

Conseguenze:
- la rotazione manuale non e piu esposta come azione principale
- quando l'auto-rotazione interviene, il bot deve permettere di rifare il job senza correzione automatica

## Fallback conservativi nella pipeline PDF

Decisione:
- quando possibile il sistema prova a preservare il PDF nativo prima di ricorrere alla rasterizzazione

Motivazione:
- preservare testo ricercabile, struttura e metadati e preferibile a un output solo visivo
- `Ghostscript` e i fallback nativi offrono risultati migliori nei casi compatibili

Conseguenze:
- la pipeline ha piu rami e va osservata bene
- servono test e metriche per capire quando entra in gioco il fallback piu invasivo

## SQLite come persistenza locale del progetto

Decisione:
- sessioni e job sono persistiti in SQLite

Motivazione:
- soluzione semplice, locale e sufficiente per il perimetro attuale
- facile da gestire in locale e su VPS singola

Conseguenze:
- il progetto e ottimizzato per un singolo nodo applicativo
- una crescita importante del carico richiederebbe valutazioni nuove su persistenza e concorrenza
