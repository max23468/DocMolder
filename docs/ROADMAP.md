# Roadmap Prodotto

Questa roadmap raccoglie le priorità attuali di `DocMolder`.

Va letta dentro il perimetro definito in [docs/DECISIONS.md](./DECISIONS.md): `DocMolder` resta una utility documentale chat-first, semplice, guidata e affidabile.

## Indice

- [Fase 1: Rifinitura Prodotto](#fase-1-rifinitura-prodotto)
- [Fase 2: Affidabilità Operativa Avanzata](#fase-2-affidabilita-operativa-avanzata)
- [Fase 3: Comprensione Linguaggio Naturale](#fase-3-comprensione-linguaggio-naturale)
- [Fase 4: Estensioni PDF Mirate](#fase-4-estensioni-pdf-mirate)
- [Fase 5: Evoluzione Esperienza Utente](#fase-5-evoluzione-esperienza-utente)
- [Fase 6: Raddrizzamento Foto Documento](#fase-6-raddrizzamento-foto-documento)
- [Fase 7: Robustezza VPS e Performance](#fase-7-robustezza-vps-e-performance)
- [Fase 8: Ottimizzazione del Funzionamento](#fase-8-ottimizzazione-del-funzionamento)

## Fase 1: Rifinitura Prodotto

Completata.

## Fase 2: Affidabilità Operativa Avanzata

Completata.

## Fase 3: Comprensione Linguaggio Naturale

Completata.

## Fase 4: Estensioni PDF Mirate

Completata.

## Fase 5: Evoluzione Esperienza Utente

Completata.

## Fase 6: Raddrizzamento Foto Documento

Completata.

## Fase 7: Robustezza VPS e Performance

Completata.

## Fase 8: Ottimizzazione del Funzionamento

- [ ] introdurre una analisi strutturata della sessione corrente, non limitata a un semplice recap testuale, con conteggi, tipo di contenuti, azioni consigliate ed eventuali warning
- [ ] evitare di ricalcolare più volte nella stessa catena le azioni supportate o esposte, riusando un risultato già inferito quando possibile
- [ ] profilare e ottimizzare meglio il flusso immagini verso PDF per ridurre uso di memoria sui batch più pesanti
- [ ] sostituire il dispatch lineare delle azioni nel processor con una mappa più chiara tra azione e handler
- [ ] distinguere meglio nel codice e nei messaggi le nozioni di azioni supportate, azioni esposte e azioni consigliate
- [ ] consolidare naming output e metadati job per avere convenzioni più coerenti tra file restituiti, storico e riepiloghi utente
- [ ] valutare se una parte minima dello stato upload usato per i limiti operativi debba sopravvivere ai riavvii invece di restare solo in memoria
