# Roadmap Prodotto

Questa roadmap raccoglie le priorita attuali di `DocMolder` dopo la
promozione alla linea stabile `1.x`.

Va letta dentro il perimetro definito in [docs/DECISIONS.md](./DECISIONS.md):
`DocMolder` resta una utility documentale Telegram-first, semplice, guidata e
affidabile. La 1.x consolida l'uso pubblico prudente prima di spingere nuove
funzioni.

## Indice

- [Storico completato](#storico-completato)
- [Stato post-1.5](#stato-post-15)
- [Principi 1.x](#principi-1x)
- [Decisioni confermate per la linea 1.x](#decisioni-confermate-per-la-linea-1x)
- [Fase 9: Privacy, retention e lifecycle dati](#fase-9-privacy-retention-e-lifecycle-dati)
- [Fase 10: UX pubblica e trust](#fase-10-ux-pubblica-e-trust)
- [Fase 11: Preset e automazioni leggere](#fase-11-preset-e-automazioni-leggere)
- [Fase 12: Qualita output e scansioni](#fase-12-qualita-output-e-scansioni)
- [Fase 13: Osservabilita e scala prudente](#fase-13-osservabilita-e-scala-prudente)
- [Fuori perimetro 1.x iniziale](#fuori-perimetro-1x-iniziale)

## Storico completato

Le Fasi 1-8 sono completate:

- rifinitura prodotto
- affidabilita operativa avanzata
- comprensione linguaggio naturale
- estensioni PDF mirate
- evoluzione esperienza utente
- raddrizzamento foto documento
- robustezza VPS e performance
- ottimizzazione del funzionamento

La readiness 1.0 e completata. `DocMolder` e stato promosso a `1.0.0` il
2026-04-28; la linea stabile corrente e documentata nel changelog e nelle
GitHub Releases. Il documento
[ONE_DOT_ZERO_READINESS.md](./ONE_DOT_ZERO_READINESS.md) resta come record della
decisione, dei criteri e degli smoke eseguiti.

## Stato post-1.5

La roadmap operativa 1.x iniziale e completata con `docmolder-v1.5.0`.

Stato corrente:

- nessuna nuova fase di sviluppo e attiva
- lo sviluppo feature resta in pausa finche non emergono bugfix, priorita
  prodotto, segnali operativi o novita esterne rilevanti
- il focus passa a stabilizzazione prudente, osservazione del soft launch e
  manutenzione ordinaria

Priorita operative immediate:

- monitorare `/admin`, healthcheck, log recenti, alert Telegram admin e soglie
  Fase 13
- eseguire smoke Telegram `public-trust` quando serve una verifica funzionale
  reale dopo deploy, correzioni o cambi operativi
- raccogliere eventuali frizioni UX o failure ricorrenti prima di definire una
  nuova fase
- mantenere aggiornate roadmap e decisioni solo quando cambia davvero
  perimetro, comportamento o priorita

Condizioni per riaprire sviluppo:

- bug riproducibile o regressione utente
- soglia operativa superata in modo ricorrente
- feedback utente che indica attrito concreto in un flusso gia supportato
- decisione esplicita di prodotto su una nuova fase, mantenendo il perimetro
  Telegram-first e best-effort

## Principi 1.x

La linea 1.x non cambia il perimetro prodotto: `DocMolder` resta una utility
documentale Telegram-first, pubblica ma best-effort, con retention breve dei
file utente e senza storage documentale permanente.

Priorita di sequenza:

1. chiudere privacy, retention e cancellazione dati prima di nuove feature
   rilevanti
2. rendere piu chiaro l'uso pubblico prudente del bot
3. introdurre solo automazioni leggere che riducono attrito nei flussi gia
   supportati
4. migliorare qualita e diagnosi degli output senza promettere comprensione
   documentale generale
5. rafforzare osservabilita e guardrail prima di una promozione pubblica piu
   ampia

## Decisioni confermate per la linea 1.x

- Postura pubblica: soft launch pubblico. Il bot resta raggiungibile, ma senza
  promozione ampia finche privacy/retention, UX trust e osservabilita minima
  non sono chiuse.
- Lingua prodotto: italiano-first per la 1.x iniziale, senza localizzazione
  inglese nel perimetro corrente.
- Privacy pubblica: rafforzare sia i testi del bot sia il sito statico; il bot
  usa messaggi brevi, il sito contiene il testo piu completo su dati, retention
  e limiti.
- Onboarding: `/start` deve includere una frase breve sul fatto che i file sono
  usati per la lavorazione e non archiviati permanentemente; i dettagli stanno
  in `/help` o nella pagina privacy.
- Cancellazione dati: esporre la cancellazione completa dentro `/reset`, con
  conferma inline obbligatoria. La cancellazione self-service riguarda dati
  live, non backup storici.
- Backup: i backup SQLite non vengono riscritti retroattivamente per cancellare
  il singolo utente; restano coperti da retention breve e la policy va
  dichiarata.
- Preset: automatici ma leggeri, derivati dalle ultime scelte frequenti,
  cancellabili con `/reset` o cancellazione dati, senza salvare contenuti o nomi
  file.
- Retry con stesse impostazioni: solo per job recenti e compatibili. Se i file
  temporanei non sono piu disponibili, il bot chiede di reinviare il file.
- Qualita scansioni: evolvere dentro l'azione "Raddrizza foto documento", con
  opzioni leggere come piu leggibile, mantieni colore e bianco/nero pulito.
- OCR: fuori dalla roadmap 1.x iniziale. Sono ammesse solo esplorazioni
  tecniche non pubbliche, senza promesse utente.
- Osservabilita: `/admin` e il centro di diagnosi rapida; shell e runbook
  restano il percorso per interventi operativi veri.
- Soglie di crescita: definire soglie prudenziali iniziali in Fase 13 su
  job/giorno, utenti attivi, dimensione DB, failure rate e coda, poi rivederle
  con dati reali.
- Promozione pubblica: mini-promozione controllata possibile dopo Fase 10 solo
  se Fase 9 e chiusa; promozione piu ampia solo se le soglie Fase 13 restano
  sotto controllo con dati reali.
- Canali: nessun nuovo canale oltre Telegram e sito statico nella 1.x iniziale.
  Niente web app e niente API pubbliche.
- Release strategy: ogni fase puo uscire come release propria; le feature
  utente vere, in particolare da Fase 11, usano commit/PR rilasciabili coerenti
  con [VERSIONING.md](./VERSIONING.md).

## Fase 9: Privacy, retention e lifecycle dati

Stato: completata.

Obiettivo:

- rendere il bot pubblico piu difendibile prima di aumentare uso e funzioni

Deliverable principali:

- policy formale per retention massima dello storico job live in SQLite
- pruning automatico dei job conclusi vecchi, integrato nel reconcile esistente
- cancellazione completa self-service dei dati utente, esposta dentro `/reset`
- conferma inline esplicita per cancellazione completa
- rimozione coerente di sessione, preferenze rapide, preset, storico personale
  e metadati utente quando l'utente chiede cancellazione completa
- documentazione aggiornata su dati salvati, dati non salvati, retention,
  backup e cancellazione

Criteri soddisfatti:

- l'utente puo cancellare i propri dati live senza intervento admin
- `/reset` resta un reset leggero di sessione e preferenze rapide, senza
  ambiguita con cancellazione completa nello stesso percorso
- reconcile espone pruning eseguito e retention applicata
- log e audit registrano solo eventi sintetici, senza contenuti documentali
- governance, modello dati e operations Telegram sono coerenti con il
  comportamento implementato

Note di perimetro:

- nessun file utente diventa permanente
- lo storico resta metadato operativo leggero, non archivio documentale

## Fase 10: UX pubblica e trust

Stato: completata.

Obiettivo:

- rendere l'esperienza pubblica chiara per nuovi utenti, senza trasformare il
  progetto in una landing o in un servizio commerciale

Deliverable principali:

- messaggi `/start` e `/help` piu chiari su cosa fa il bot e quali limiti ha
- ingresso semplice a privacy, retention e limiti tramite help, status o deep
  link essenziale
- sito statico allineato allo stato 1.x: CTA Telegram, privacy sintetica,
  limiti file e perimetro del servizio
- testo breve gia in `/start` sul fatto che i file non sono archiviati
  permanentemente
- messaggi piu pratici per file troppo grandi, coda piena, manutenzione, job
  fallito e retry
- smoke pubblico minimo post-deploy: start, help, status, upload minimo,
  output e cancellazione dati

Criteri soddisfatti:

- un nuovo utente capisce rapidamente cosa puo fare e cosa non deve aspettarsi
- privacy e limiti sono visibili prima o durante il primo uso reale
- i messaggi di errore indicano un prossimo passo utile
- il sito resta statico e non introduce una superficie applicativa web

Note di perimetro:

- niente dashboard web-first
- niente SLA o promessa di disponibilita continua

## Fase 11: Preset e automazioni leggere

Stato: completata.

Obiettivo:

- velocizzare flussi ripetuti senza trasformare DocMolder in editor o
  gestionale documentale

Deliverable principali:

- preset utente persistenti ma minimali, cancellabili con reset/cancellazione
  dati
- preferenze iniziali per immagini verso PDF, livello compressione e formato
  split
- salvataggio automatico leggero basato sulle ultime scelte frequenti, senza
  contenuti documento o nomi file
- scorciatoie inline contestuali basate sui preset, senza pannelli complessi
- opzione "ripeti con stesse impostazioni" quando il job recente e compatibile
- policy chiara su quali preferenze diventano persistenti e quali restano
  inferenze momentanee

Criteri soddisfatti:

- l'utente ricorrente riduce i passaggi nei flussi piu frequenti
- ogni preset resta opzionale e non impedisce la scelta manuale
- preset e preferenze non salvano contenuti documento o dati sensibili
- `/reset` e cancellazione completa rimuovono preferenze e preset
- i preset vengono promossi solo dopo scelte ripetute e restano limitati a
  compressione, layout immagini verso PDF e formato output split

Note di perimetro:

- i preset riguardano impostazioni operative, non profili documentali o
  archivi di file

## Fase 12: Qualita output e scansioni

Stato: completata.

Obiettivo:

- migliorare i risultati documentali nei flussi gia coerenti con il prodotto

Deliverable principali:

- feedback piu chiaro quando una foto documento e sfocata, buia, senza bordo
  leggibile o con prospettiva incerta
- opzioni leggere dentro "Raddrizza foto documento", come piu leggibile,
  mantieni colore o bianco/nero pulito
- feedback pratico sulla compressione, inclusi casi in cui riduce poco o non
  conviene
- test sintetici piu rappresentativi per foto documento e PDF problematici

Criteri soddisfatti:

- gli output da foto reali diventano piu prevedibili
- fallback ed errori spiegano il limite senza colpevolizzare l'utente
- il bot suggerisce come riprovare quando input o risultato non sono ideali
- i miglioramenti non degradano i percorsi nativi PDF quando disponibili
- le opzioni restano dentro "Raddrizza foto documento" e non introducono OCR o
  comprensione del contenuto

Note di perimetro:

- OCR esteso e comprensione del contenuto restano fuori da questa fase
- eventuali prove OCR devono restare esplorazioni tecniche non promesse agli
  utenti

## Fase 13: Osservabilita e scala prudente

Stato: completata.

Obiettivo:

- preparare un aumento moderato di utenti senza cambiare architettura o
  promettere un servizio con SLA

Deliverable principali:

- dashboard admin piu utile per uso pubblico: utenti attivi recenti, failure
  rate per azione, job lenti, pruning e cancellazioni dati
- soglie health riviste dopo osservazione reale su coda, RAM, runtime dir,
  backup, failure rate e job running stale
- alert Telegram admin piu orientati all'azione, con indicazione del runbook o
  comando utile
- soglie prudenziali iniziali su job/giorno, utenti attivi, dimensione DB,
  failure rate e coda
- criterio scritto per capire quando SQLite o VPS singola non bastano piu
- runbook di emergenza per manutenzione, allow-list temporanea, pruning manuale
  e rollback

Criteri soddisfatti:

- i problemi operativi comuni sono diagnosticabili da `/admin`, healthcheck e
  runbook senza interrogare manualmente SQLite
- esiste un criterio chiaro per fermare crescita, restringere accesso o
  rivalutare architettura
- il servizio resta coerente con VPS singola e bot Telegram in polling finche i
  limiti sono rispettati
- gli alert admin indicano un controllo successivo utile invece di limitarsi al
  sintomo

Note di perimetro:

- nessuna migrazione architetturale automatica
- eventuale cambio database, coda esterna o alerting esterno richiede decisione
  dedicata

## Fuori perimetro 1.x iniziale

Restano fuori dalla roadmap iniziale 1.x, salvo decisione esplicita:

- dashboard web-first
- archivio documentale permanente
- SLA pubblico o supporto commerciale strutturato
- API pubbliche o integrazioni esterne stabili
- OCR esteso o comprensione documento generalista

Questi temi possono essere rivalutati solo dopo aver chiuso privacy/retention,
uso pubblico prudente e osservabilita minima della linea 1.x.
