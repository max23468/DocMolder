# Decisioni Progetto

Questo file raccoglie decisioni architetturali e di prodotto già prese, in forma breve.

## Indice

- [ADR puntuali e basename Markdown](#adr-puntuali-e-basename-markdown)
- [Perimetro prodotto: utility documentale chat-first](#perimetro-prodotto-utility-documentale-chat-first)
- [Soft launch prima, feature dopo](#soft-launch-prima-feature-dopo)
- [Polling invece di webhook pubblici](#polling-invece-di-webhook-pubblici)
- [Webhook privato per deploy e controlli locali](#webhook-privato-per-deploy-e-controlli-locali)
- [Gate Codex sull'HEAD esatto](#gate-codex-sullhead-esatto)
- [Retention breve dei file temporanei](#retention-breve-dei-file-temporanei)
- [Auto-orientamento PDF invece di rotazione manuale come azione primaria](#auto-orientamento-pdf-invece-di-rotazione-manuale-come-azione-primaria)
- [Fallback conservativi nella pipeline PDF](#fallback-conservativi-nella-pipeline-pdf)
- [SQLite come persistenza locale del progetto](#sqlite-come-persistenza-locale-del-progetto)

## ADR puntuali e basename Markdown

Decisione:
- `docs/DECISIONS.md` resta il riepilogo storico delle decisioni stabili già prese
- `docs/DECISIONS_PENDING.md` resta il registro delle decisioni aperte
- `docs/decisions/` ospita nuove decisioni autonome in formato ADR leggero,
  usando `docs/decisions/template.md`
- non si usa `docs/decisions/README.md`, per mantenere un solo `README.md` nella
  repository

Motivazione:
- i basename Markdown univoci rendono ricerca, handoff e riferimenti più chiari
- DocMolder aveva già `docs/DECISIONS.md` come fonte decisionale viva
- mantenere un secondo `README.md` solo per indicizzare gli ADR duplicherebbe
  informazione già collegata da `docs/INDEX.md`

Conseguenze:
- la migrazione delle decisioni storiche da `docs/DECISIONS.md` a ADR puntuali
  va fatta progressivamente, preservando contenuti, motivazioni e conseguenze
  operative
- quando una decisione diventa autonoma, va aggiunta in `docs/decisions/` e
  linkata da `docs/DECISIONS.md` e `docs/INDEX.md`

## Perimetro prodotto: utility documentale chat-first

Decisione:
- `DocMolder` resta una utility documentale chat-first, semplice, guidata e affidabile, focalizzata su trasformazioni pratiche di PDF, foto di documenti e interventi Excel mirati

Motivazione:
- il valore del prodotto oggi e nella rapidità, chiarezza e affidabilità del flusso via Telegram
- allargare troppo il perimetro rischia di trasformarlo in un editor PDF generalista o in un sistema documentale molto più complesso
- mantenere un'operazione chiara per volta aiuta UX, manutenzione e qualità del risultato

Conseguenze:
- le nuove feature vanno accettate solo se rafforzano semplicità, qualità del risultato, chiarezza UX o affidabilità operativa
- gli interventi Excel ammessi restano trasformazioni puntuali su file già apribili, non gestione documentale o recupero password
- vanno invece trattate con molta prudenza feature che aprono mondi nuovi come document management, OCR esteso, workflow troppo complessi o automazioni poco controllabili
- la roadmap deve essere letta dentro questo perimetro: meglio poche evoluzioni coerenti che accumulo di funzioni eterogenee
- salvo decisione esplicita futura, consideriamo `bloat` o `too much` tutte le proposte che spingono il prodotto verso editor PDF generalista, piattaforma documentale ampia o assistente conversazionale troppo aperto

## Soft launch prima, feature dopo

Decisione:
- dalla linea `1.x` il bot resta in soft launch pubblico: è raggiungibile, ma
  non viene spinto con promozione ampia senza evidenza operativa sufficiente;
  questa postura resta valida nella linea `2.x`
- la lingua prodotto resta italiano-first
- le prime feature dopo il consolidamento sono preset e automazioni leggere, non nuove superfici web/API o OCR esteso
- `/admin` resta il centro di diagnosi rapida, mentre shell e runbook restano il percorso per gli interventi operativi veri

Motivazione:
- il bot è già pubblico, quindi la priorità è rendere chiari dati, limiti e cancellazione prima di aumentare esposizione
- preset e automazioni leggere riducono attrito sui flussi esistenti senza allargare troppo il perimetro
- OCR, API pubbliche e web app creerebbero aspettative e complessità non
  coerenti con il perimetro prudente del servizio

Conseguenze:
- Fase 9 ha chiuso retention live, pruning e cancellazione completa self-service; il reset operativo resta separato dalla gestione dati esposta in `/start privacy`
- Fase 10 ha rafforzato onboarding, privacy pubblica e sito statico senza introdurre una web app
- Fase 11 ha introdotto preset automatici leggeri e cancellabili, senza salvare contenuti o nomi file
- Fase 12 ha migliorato scansioni dentro "Raddrizza foto documento", lasciando OCR fuori dal perimetro pubblico
- Fase 13 ha definito soglie prudenziali di crescita e criteri per rivalutare VPS singola e SQLite
- una mini-promozione controllata è possibile solo dopo Fase 10 e con Fase 9 chiusa; una promozione più ampia richiede soglie Fase 13 sotto controllo con dati reali

## Polling invece di webhook pubblici

Decisione:
- il bot gira in polling
- il bot è considerato pubblico e raggiungibile da `https://t.me/docmolder_bot`
- `docmolder.duckdns.org` può essere predisposto con DNS, HTTPS e reverse proxy minimale per operatività e future evoluzioni, senza trasformare automaticamente il bot in un servizio web

Motivazione:
- riduce complessità operativa
- evita dipendenza funzionale da endpoint HTTP esposti
- è coerente con un tool Telegram-first a carico contenuto
- permette di pubblicare il servizio senza introdurre webhook o un runtime web applicativo

Conseguenze:
- il deploy è più semplice
- il bot non dipende da ingress pubblici
- il vhost pubblico resta un sito statico di presentazione e ingresso verso Telegram finché non viene deciso un endpoint DocMolder specifico
- eventuali evoluzioni API-first, webhook Telegram o UI web richiederebbero una decisione nuova

## Webhook privato per deploy e controlli locali

Decisione:
- l'automazione ordinaria usa CI prudente sulle PR non draft verso `main` e webhook privati GitHub -> VPS per il deploy
- il listener webhook gira sulla VPS dietro Nginx e verifica firma HMAC, repository e branch prima di lanciare `deploy/update-vps.sh`
- il listener non include più passaggi extra di rilascio nel flusso standard; il rilascio operativo passa dal percorso di release manuale documentato
- il bump versione, il changelog, i tag e le GitHub Release sono gestiti dalla procedura release manuale documentata
- i controlli di qualità locale restano comandi espliciti, senza hook eseguiti automaticamente dal worktree
- eventuali token GitHub usati per operazioni manuali non sono parte del percorso operativo standard; in caso di necessità si usano secret GitHub e non file env persistenti non più presenti in questo flusso

Motivazione:
- mantiene il consumo Actions controllato: CI PR e workflow operativi solo manuali
- mantiene versioni, changelog, tag e GitHub Releases allineati nel flusso standard GitHub
- mantiene il listener semplice e confinato alla VPS, non al runtime Telegram
- mantiene gate locali espliciti come primo feedback economico prima del push

Conseguenze:
- il deploy automatico dipende da un webhook GitHub configurato esplicitamente sulla repository
- le release ordinarie dipendono dal passaggio con la procedura release manuale documentata dopo merge su `main`
- la release automatica VPS, se riabilitata come fallback, dipende da un token GitHub con permessi di scrittura sui contenuti del repository
- la VPS deve esporre un endpoint HTTPS dedicato al listener, ma non un runtime web applicativo generalista
- se il webhook non è configurato, il percorso resta manuale ma non si rompe il bot
- (deprecato) i commit `chore(main): release docmolder X.Y.Z` non producono una nuova release; oggi la release passa per la procedura release manuale documentata

## Gate Codex sull'HEAD esatto

Decisione:
- il workflow `.github/workflows/codex-review-gate.yml` pubblica lo status richiesto `codex-review` sull'HEAD esatto della PR
- il gate esegue soltanto codice del branch predefinito fidato e accetta segnali esclusivamente da `chatgpt-codex-connector[bot]`
- ogni nuovo SHA o nuovo tentativo invalida review, reazioni, finding ed errori precedenti; i finding P0-P3 correnti prevalgono su qualsiasi approvazione
- il workflow può restare verde mentre lo status `pending`, `failure` o `error` impedisce il merge
- i thread actionable restano letti direttamente sulla PR corrente dal preflight locale; non esiste una inbox globale separata

Motivazione:
- un gate basato sul solo esito del workflow può diventare verde senza provare che Codex abbia approvato l'ultimo commit
- legare segnali, timestamp e `original_commit_id` al tentativo corrente evita riuso di approvazioni o finding obsoleti
- eseguire il codice dalla default branch evita che una PR controlli un workflow privilegiato `pull_request_target`

Conseguenze:
- dopo ogni nuovo commit si richiede `@codex review` e si attende lo status sull'HEAD esatto
- prima del merge si controllano anche i thread della PR corrente con `scripts/check_codex_bot_comments.py --pr <numero> --fail`
- la PR che introduce per la prima volta il workflow richiede bootstrap esplicito: `pull_request_target` legge ancora il branch predefinito precedente

## Retention breve dei file temporanei

Decisione:
- niente storage permanente dei file utente nel perimetro attuale

Motivazione:
- riduce rischio operativo e responsabilità sui dati
- mantiene il prodotto focalizzato su trasformazioni rapide
- semplifica manutenzione e costi

Conseguenze:
- il recupero storico dei file non è disponibile di default
- la pulizia automatica dei job è parte essenziale del sistema

## Auto-orientamento PDF come scelta raccomandata

Decisione:
- le elaborazioni PDF compatibili correggono automaticamente l'orientamento quando serve
- la rotazione manuale resta disponibile come azione esplicita per i casi in cui l'utente vuole controllare direttamente i gradi di rotazione

Motivazione:
- semplifica la UX
- riduce la necessità di una scelta tecnica esplicita da parte dell'utente
- copre meglio il caso pratico di PDF con poche pagine fuori orientamento
- mantiene una via manuale utile per casi particolari che l'auto-orientamento non deve indovinare

Conseguenze:
- l'auto-orientamento è il comportamento raccomandato nei flussi compatibili
- la rotazione manuale può essere esposta come azione avanzata, ma non deve diventare il percorso consigliato di default
- quando l'auto-rotazione interviene, il bot deve permettere di rifare il job senza correzione automatica

## Fallback conservativi nella pipeline PDF

Decisione:
- quando possibile il sistema prova a preservare il PDF nativo prima di ricorrere alla rasterizzazione

Motivazione:
- preservare testo ricercabile, struttura e metadati e preferibile a un output solo visivo
- `Ghostscript` e i fallback nativi offrono risultati migliori nei casi compatibili

Conseguenze:
- la pipeline ha più rami e va osservata bene
- servono test e metriche per capire quando entra in gioco il fallback più invasivo

## Catalogo centrale delle azioni

Decisione:
- etichette utente, ordine di esposizione e azioni compatibili devono derivare da un punto centrale, non da mapping duplicati tra bot, tastiere e messaggi

Motivazione:
- riduce il rischio che una nuova azione venga supportata dalla pipeline ma non compaia in tastiera, o viceversa
- rende più semplice verificare l'allineamento tra modello interno e UI Telegram

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
