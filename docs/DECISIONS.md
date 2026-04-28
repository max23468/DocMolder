# Decisioni Progetto

Questo file raccoglie decisioni architetturali e di prodotto gia prese, in forma breve.

## Indice

- [Perimetro prodotto: utility documentale chat-first](#perimetro-prodotto-utility-documentale-chat-first)
- [Roadmap 1.x: soft launch prima, feature dopo](#roadmap-1x-soft-launch-prima-feature-dopo)
- [Polling invece di webhook pubblici](#polling-invece-di-webhook-pubblici)
- [Webhook privato per deploy e hook locali](#webhook-privato-per-deploy-e-hook-locali)
- [Retention breve dei file temporanei](#retention-breve-dei-file-temporanei)
- [Auto-orientamento PDF invece di rotazione manuale come azione primaria](#auto-orientamento-pdf-invece-di-rotazione-manuale-come-azione-primaria)
- [Fallback conservativi nella pipeline PDF](#fallback-conservativi-nella-pipeline-pdf)
- [SQLite come persistenza locale del progetto](#sqlite-come-persistenza-locale-del-progetto)

## Perimetro prodotto: utility documentale chat-first

Decisione:
- `DocMolder` resta una utility documentale chat-first, semplice, guidata e affidabile, focalizzata su trasformazioni pratiche di PDF e foto di documenti

Motivazione:
- il valore del prodotto oggi e nella rapidita, chiarezza e affidabilita del flusso via Telegram
- allargare troppo il perimetro rischia di trasformarlo in un editor PDF generalista o in un sistema documentale molto piu complesso
- mantenere un'operazione chiara per volta aiuta UX, manutenzione e qualita del risultato

Conseguenze:
- le nuove feature vanno accettate solo se rafforzano semplicita, qualita del risultato, chiarezza UX o affidabilita operativa
- vanno invece trattate con molta prudenza feature che aprono mondi nuovi come document management, OCR esteso, workflow troppo complessi o automazioni poco controllabili
- la roadmap deve essere letta dentro questo perimetro: meglio poche evoluzioni coerenti che accumulo di funzioni eterogenee
- salvo decisione esplicita futura, consideriamo `bloat` o `too much` tutte le proposte che spingono il prodotto verso editor PDF generalista, piattaforma documentale ampia o assistente conversazionale troppo aperto

## Roadmap 1.x: soft launch prima, feature dopo

Decisione:
- la linea `1.x` resta in soft launch pubblico: il bot e raggiungibile, ma non viene spinto con promozione ampia prima di privacy/retention, UX trust e osservabilita minima
- la lingua prodotto resta italiano-first nella 1.x iniziale
- le prime feature dopo il consolidamento sono preset e automazioni leggere, non nuove superfici web/API o OCR esteso
- `/admin` resta il centro di diagnosi rapida, mentre shell e runbook restano il percorso per gli interventi operativi veri

Motivazione:
- il bot e gia pubblico, quindi la priorita e rendere chiari dati, limiti e cancellazione prima di aumentare esposizione
- preset e automazioni leggere riducono attrito sui flussi esistenti senza allargare troppo il perimetro
- OCR, API pubbliche e web app creerebbero aspettative e complessita non coerenti con la fase iniziale della 1.x

Conseguenze:
- Fase 9 ha chiuso retention live, pruning e cancellazione completa self-service dentro `/reset`
- Fase 10 ha rafforzato onboarding, privacy pubblica e sito statico senza introdurre una web app
- Fase 11 ha introdotto preset automatici leggeri e cancellabili, senza salvare contenuti o nomi file
- Fase 12 ha migliorato scansioni dentro "Raddrizza foto documento", lasciando OCR fuori dal perimetro pubblico
- Fase 13 ha definito soglie prudenziali di crescita e criteri per rivalutare VPS singola e SQLite
- una mini-promozione controllata e possibile solo dopo Fase 10 e con Fase 9 chiusa; una promozione piu ampia richiede soglie Fase 13 sotto controllo con dati reali

## Polling invece di webhook pubblici

Decisione:
- il bot gira in polling
- il bot e considerato pubblico e raggiungibile da `https://t.me/docmolder_bot`
- `docmolder.duckdns.org` puo essere predisposto con DNS, HTTPS e reverse proxy minimale per operativita e future evoluzioni, senza trasformare automaticamente il bot in un servizio web

Motivazione:
- riduce complessita operativa
- evita dipendenza funzionale da endpoint HTTP esposti
- e coerente con un tool Telegram-first a carico contenuto
- permette di pubblicare il servizio senza introdurre webhook o un runtime web applicativo

Conseguenze:
- il deploy e piu semplice
- il bot non dipende da ingress pubblici
- il vhost pubblico resta un sito statico di presentazione e ingresso verso Telegram finche non viene deciso un endpoint DocMolder specifico
- eventuali evoluzioni API-first, webhook Telegram o UI web richiederebbero una decisione nuova

## Webhook privato per deploy, release e hook locali

Decisione:
- l'automazione senza GitHub Actions usa webhook privati GitHub -> VPS per il deploy su `main` e, se abilitato, per la release automatica successiva
- il listener webhook gira sulla VPS dietro Nginx e verifica firma HMAC, repository e branch prima di lanciare `deploy/update-vps.sh`
- dopo un deploy riuscito, il listener puo lanciare `deploy/auto-release.sh`, che crea bump, changelog, commit di release, tag e GitHub Release quando trova commit rilasciabili dal tag precedente
- i controlli di qualità locale vivono in hook `git` installabili con `make install-hooks`
- il token GitHub usato per scrivere release vive solo sulla VPS in `/etc/docmolder/release.env`, con permessi root-only

Motivazione:
- permette di mantenere il deploy automatico senza dipendere da Actions
- permette di mantenere versioni, changelog, tag e GitHub Releases allineati anche senza Actions
- mantiene il listener semplice e confinato alla VPS, non al runtime Telegram
- sposta i gate quotidiani vicino alla macchina di sviluppo, dove il costo di verifica e nullo

Conseguenze:
- il deploy automatico dipende da un webhook GitHub configurato esplicitamente sulla repository
- la release automatica dipende da un token GitHub con permessi di scrittura sui contenuti del repository
- la VPS deve esporre un endpoint HTTPS dedicato al listener, ma non un runtime web applicativo generalista
- gli hook locali possono bloccare push non pronti prima che arrivino su GitHub
- se il webhook o gli hook non sono configurati, il percorso resta manuale ma non si rompe il bot
- i commit `chore(main): release docmolder X.Y.Z` non producono una nuova release, evitando loop di release/deploy

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

## Auto-orientamento PDF come scelta raccomandata

Decisione:
- le elaborazioni PDF compatibili correggono automaticamente l'orientamento quando serve
- la rotazione manuale resta disponibile come azione esplicita per i casi in cui l'utente vuole controllare direttamente i gradi di rotazione

Motivazione:
- semplifica la UX
- riduce la necessita di una scelta tecnica esplicita da parte dell'utente
- copre meglio il caso pratico di PDF con poche pagine fuori orientamento
- mantiene una via manuale utile per casi particolari che l'auto-orientamento non deve indovinare

Conseguenze:
- l'auto-orientamento e il comportamento raccomandato nei flussi compatibili
- la rotazione manuale puo essere esposta come azione avanzata, ma non deve diventare il percorso consigliato di default
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

## Catalogo centrale delle azioni

Decisione:
- etichette utente, ordine di esposizione e azioni compatibili devono derivare da un punto centrale, non da mapping duplicati tra bot, tastiere e messaggi

Motivazione:
- riduce il rischio che una nuova azione venga supportata dalla pipeline ma non compaia in tastiera, o viceversa
- rende piu semplice verificare l'allineamento tra modello interno e UI Telegram

Conseguenze:
- l'introduzione di una nuova azione passa prima dal catalogo in `action_catalog.py`
- tastiere e report si appoggiano a etichette condivise invece di duplicare stringhe locali

## SQLite come persistenza locale del progetto

Decisione:
- sessioni e job sono persistiti in SQLite

Motivazione:
- soluzione semplice, locale e sufficiente per il perimetro attuale
- facile da gestire in locale e su VPS singola

Conseguenze:
- il progetto e ottimizzato per un singolo nodo applicativo
- una crescita importante del carico richiederebbe valutazioni nuove su persistenza e concorrenza
