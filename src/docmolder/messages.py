from __future__ import annotations

from docmolder.branding import BRAND_NAME, BRAND_TAGLINE
from docmolder.models import CompressionPreset, SupportedAction

PUBLIC_PRIVACY_URL = "https://docmolder.duckdns.org/privacy.html"

WELCOME_MESSAGE = (
    f"Ciao, sono {BRAND_NAME}.\n\n"
    f"{BRAND_TAGLINE}\n\n"
    "Lavoro bene quando mi mandi PDF, foto o scansioni direttamente qui su Telegram. "
    "Uso i file per creare il risultato richiesto e non li archivio permanentemente.\n\n"
    "Ti aiuto a:\n"
    "- creare PDF ordinati da immagini\n"
    "- raddrizzare foto di documenti senza aprire un editor\n"
    "- comprimere, unire, dividere e convertire PDF\n"
    "- estrarre, riordinare, eliminare o ruotare pagine\n"
    "- aggiungere watermark testuali\n"
    "- correggere l'orientamento di PDF e immagini quando serve\n\n"
    "Per partire, inviami immagini o PDF.\n"
    "Per limiti, dati e cancellazione usa /help o leggi la pagina privacy:\n"
    f"{PUBLIC_PRIVACY_URL}"
)

HELP_MESSAGE = (
    f"Ecco come usare {BRAND_NAME}.\n\n"
    "1. Inviami immagini oppure PDF.\n"
    "2. Ti proporrò solo le azioni compatibili con i file ricevuti.\n"
    "3. Se crei un PDF da immagini, ti chiederò anche se vuoi impaginarlo in A4 e con quali bordi.\n"
    "4. Ti restituirò il file finale qui in chat.\n\n"
    "DocMolder è pensato per essere semplice: una richiesta chiara per volta, pochi tocchi e un risultato pronto. "
    "Il servizio è pubblico ma best-effort: non è un archivio documentale, non offre SLA e può limitare lavorazioni troppo pesanti.\n\n"
    "Dati e limiti:\n"
    "- i file servono alla lavorazione e non sono archiviati permanentemente\n"
    "- lo storico job live conserva metadati tecnici per /history e retry, poi viene potato\n"
    "- /reset azzera sessione e preferenze; da lì puoi cancellare anche tutti i tuoi dati live\n"
    f"- dettagli completi: {PUBLIC_PRIVACY_URL}\n\n"
    "Esempi:\n"
    "- più immagini -> un PDF unico\n"
    "- immagini scannerizzate -> ritaglio bordi e PDF\n"
    "- foto storta di un foglio -> raddrizza foto documento\n"
    "- immagini -> PDF con formato originale oppure A4 con bordi a scelta\n"
    "- un PDF -> comprimi o scala di grigi\n"
    "- un PDF -> dividi in un file per pagina\n"
    "- un PDF -> estrai pagine, riordinale, eliminale, ruotale o aggiungi un watermark\n"
    "- più PDF -> unisci\n\n"
    "Puoi anche scrivermi richieste semplici come:\n"
    "- fammi un pdf in scala di grigi\n"
    "- ritaglia i bordi e crea un pdf\n"
    "- raddrizza foto documento\n"
    "- converti in bianco e nero\n"
    "- unisci questi pdf\n"
    "- comprimi questo pdf\n"
    "- dividi questo pdf\n"
    "- estrai pagine 2-4\n"
    "- ruota questo pdf di 90 gradi\n"
    "- aggiungi watermark BOZZA\n"
    "- foto in A4\n"
    "- scansiona e comprimi\n\n"
    "Comandi utili:\n"
    "/start\n"
    "/help\n"
    "/history\n"
    "/status\n"
    "/reset  (azzera sessione e ultime scelte rapide, con opzione di cancellazione dati live)"
)

UNAUTHORIZED_MESSAGE = (
    "Questo account non può usare il bot in questo momento. "
    f"Contatta l'amministratore di {BRAND_NAME} per l'abilitazione."
)

SESSION_EMPTY_MESSAGE = (
    "Non vedo ancora file nella tua sessione. "
    "Inviami immagini o PDF e poi ti proporrò le azioni disponibili."
)

MIXED_SESSION_MESSAGE = (
    "La sessione corrente contiene già un tipo di file diverso. "
    "Per evitare combinazioni ambigue, usa /reset e riparti con soli PDF oppure sole immagini."
)

FILE_TOO_LARGE_MESSAGE = (
    "Questo file supera il limite consentito per il bot. "
    "Prova a inviarne una versione più leggera, riduci risoluzione/compressione oppure dividi il materiale in più file."
)

UPLOAD_RATE_LIMIT_MESSAGE = (
    "Stai inviando file troppo rapidamente. "
    "Aspetta qualche secondo e poi riprova con meno file per volta."
)

JOB_QUEUE_LIMIT_MESSAGE = (
    "Hai già troppe operazioni in coda o in lavorazione. "
    "Aspetta che il bot finisca i job già presi in carico, controlla /status e poi inviane altri."
)

PROCESSING_MESSAGE = "Sto elaborando i file. Potrebbe volerci qualche secondo."

GENERIC_ERROR_MESSAGE = (
    "Si è verificato un problema durante l'elaborazione. "
    "Riprova tra poco; se il problema continua, usa /reset e reinvia il file."
)

ADMIN_ONLY_MESSAGE = "Questo comando è disponibile solo per l'admin del bot."

SERVICE_UNAVAILABLE_MESSAGE = (
    "DocMolder è in modalità manutenzione in questo momento. "
    "Riprova tra poco o controlla /status. Gli admin possono continuare a usare i comandi di controllo."
)


def build_pending_action_prompt(action: SupportedAction) -> str:
    if action == SupportedAction.PDF_SPLIT:
        return (
            "Come vuoi ricevere le pagine divise?\n"
            "Puoi scegliere uno `ZIP` unico oppure `PDF separati`. Per documenti con tante pagine lo ZIP è più ordinato."
        )
    if action == SupportedAction.PDF_ROTATE:
        return (
            "Scrivimi di quanto vuoi ruotare il PDF: `90`, `180` oppure `270` gradi.\n"
            "Vanno bene anche frasi naturali come `ruotalo di 90 gradi`, `giralo a destra` o `mezzo giro`."
        )
    if action == SupportedAction.PDF_EXTRACT_PAGES:
        return (
            "Scrivimi quali pagine vuoi estrarre, ad esempio `1,3,5-7`.\n"
            "Puoi combinare pagine singole e intervalli. Se preferisci, vanno bene anche spazi semplici come `1 3 5-7`.\n"
            "Se sbagli formato, ti dico subito come correggerlo."
        )
    if action == SupportedAction.PDF_REORDER_PAGES:
        return (
            "Scrivimi il nuovo ordine completo delle pagine, ad esempio `3,1,2`.\n"
            "Devi indicare tutte le pagine del PDF una sola volta. Accetto anche sequenze con spazi, ad esempio `3 1 2`.\n"
            "Se il PDF ha 5 pagine, devo ricevere tutte e 5 le posizioni."
        )
    if action == SupportedAction.PDF_DELETE_PAGES:
        return (
            "Scrivimi quali pagine vuoi eliminare, ad esempio `2,4-5`.\n"
            "Il bot manterra tutte le altre. Se preferisci, vanno bene anche spazi semplici come `2 4-5`.\n"
            "Attenzione: deve restare almeno una pagina nel PDF finale."
        )
    if action == SupportedAction.PDF_WATERMARK:
        return (
            "Scrivimi il testo semplice che vuoi usare come watermark su tutte le pagine del PDF.\n"
            "Esempio: `BOZZA`, `COPIA` oppure il nome del destinatario."
        )
    return "Scrivimi i dettagli necessari per continuare."


def build_pending_action_queued_message(action: SupportedAction, job_id: int, raw_value: str) -> str:
    cleaned_value = raw_value.strip()
    if action == SupportedAction.PDF_SPLIT:
        if cleaned_value.lower() in {"zip", "archivio", "zip unico"}:
            return (
                f"Divisione PDF presa in carico con ZIP unico. Job #{job_id} in coda.\n"
                "Ti invio lo ZIP appena è pronto."
            )
        return (
            f"Divisione PDF presa in carico con PDF separati. Job #{job_id} in coda.\n"
            "Ti invio i file appena sono pronti."
        )
    if action == SupportedAction.PDF_EXTRACT_PAGES:
        return f"Estrazione pagine presa in carico ({cleaned_value}). Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_REORDER_PAGES:
        return f"Riordino pagine preso in carico ({cleaned_value}). Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_DELETE_PAGES:
        return f"Eliminazione pagine presa in carico ({cleaned_value}). Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_WATERMARK:
        return f'Watermark testuale preso in carico ("{cleaned_value}"). Job #{job_id} in coda.\nTi invio il PDF appena è pronto.'
    return f"Operazione presa in carico. Job #{job_id} in coda."


def build_text_request_queued_message(
    action: SupportedAction,
    job_id: int,
    compression_preset: CompressionPreset | None,
) -> str:
    if action == SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE:
        return (
            f"Ritaglio automatico e PDF in scala di grigi presi in carico. "
            f"Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
        )
    if action == SupportedAction.IMAGES_TO_PDF_CROP:
        return f"Ritaglio automatico e creazione PDF presi in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.DOCUMENT_PHOTO_FIX:
        return f"Raddrizzamento foto documento preso in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.IMAGES_TO_PDF_GRAYSCALE:
        return f"PDF in scala di grigi preso in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.IMAGES_TO_PDF:
        return f"Creazione PDF presa in carico. Job #{job_id} in coda.\nTi scrivo qui appena è pronto."
    if action == SupportedAction.PDF_GRAYSCALE:
        return (
            f"Conversione in scala di grigi presa in carico. Job #{job_id} in coda.\n"
            "Se il PDF è complesso potrei impiegare un po' di più o usare un fallback per garantirti comunque un risultato."
        )
    if action == SupportedAction.PDF_MERGE:
        return f"Unione PDF presa in carico. Job #{job_id} in coda.\nTi invio il file appena è pronto."
    if action == SupportedAction.PDF_SPLIT:
        return (
            f"Divisione PDF presa in carico. Job #{job_id} in coda.\n"
            "Ti invio uno ZIP con un PDF per ogni pagina appena è pronto."
        )
    if action == SupportedAction.PDF_EXTRACT_PAGES:
        return f"Estrazione pagine presa in carico. Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_REORDER_PAGES:
        return f"Riordino pagine preso in carico. Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_DELETE_PAGES:
        return f"Eliminazione pagine presa in carico. Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_COMPRESS:
        preset_label = (compression_preset or CompressionPreset.MEDIUM).value
        extra_note = (
            "\nSe il PDF è difficile da comprimere potrei impiegare più tempo o usare un fallback compatibile."
            if preset_label in {CompressionPreset.MEDIUM.value, CompressionPreset.STRONG.value}
            else ""
        )
        return (
            f"Compressione PDF presa in carico con livello {preset_label}. "
            f"Job #{job_id} in coda.\nTi invio il file appena è pronto.{extra_note}"
        )
    if action == SupportedAction.AUTO_ORIENT:
        return f"Correzione orientamento presa in carico. Job #{job_id} in coda.\nTi invio il risultato appena è pronto."
    if action == SupportedAction.PDF_ROTATE:
        return f"Rotazione manuale presa in carico. Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    if action == SupportedAction.PDF_WATERMARK:
        return f"Watermark testuale preso in carico. Job #{job_id} in coda.\nTi invio il PDF appena è pronto."
    return f"Operazione presa in carico. Job #{job_id} in coda."


def build_processing_started_message(action: SupportedAction, job_id: int) -> str:
    if action == SupportedAction.PDF_GRAYSCALE:
        return (
            f"Sto elaborando i file. Potrebbe volerci qualche secondo.\n"
            f"Job #{job_id} in elaborazione.\n"
            "Se il PDF non si lascia convertire bene in modo nativo, proverò una soluzione di ripiego compatibile."
        )
    if action == SupportedAction.PDF_COMPRESS:
        return (
            f"Sto elaborando i file. Potrebbe volerci qualche secondo.\n"
            f"Job #{job_id} in elaborazione.\n"
            "Nei casi più difficili la compressione può richiedere un po' di più per trovare il fallback più adatto."
        )
    return f"{PROCESSING_MESSAGE}\nJob #{job_id} in elaborazione."
