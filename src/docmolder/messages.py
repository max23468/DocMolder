from __future__ import annotations

from docmolder.models import CompressionPreset, SupportedAction

WELCOME_MESSAGE = (
    "Ciao, sono DocMolder.\n\n"
    "Posso aiutarti a lavorare su immagini e PDF direttamente qui su Telegram.\n\n"
    "Cosa puoi fare:\n"
    "- creare un PDF da una o più immagini\n"
    "- comprimere un PDF\n"
    "- convertire un PDF in scala di grigi\n"
    "- unire più PDF\n"
    "- estrarre, riordinare, eliminare o ruotare pagine di un PDF\n"
    "- aggiungere un watermark testuale a un PDF\n"
    "- correggere automaticamente l'orientamento dei PDF durante l'elaborazione, quando serve\n"
    "- correggere l'orientamento delle immagini\n\n"
    "Per iniziare, inviami immagini o PDF.\n"
    "Se vuoi, puoi anche usare il menu qui sotto, consultare /history per gli ultimi job "
    "oppure usare template rapidi come `Foto in A4` e `Scansiona e comprimi`."
)

HELP_MESSAGE = (
    "Ecco come usare DocMolder.\n\n"
    "1. Inviami immagini oppure PDF.\n"
    "2. Ti proporrò solo le azioni compatibili con i file ricevuti.\n"
    "3. Se crei un PDF da immagini, ti chiederò anche se vuoi impaginarlo in A4 e con quali bordi.\n"
    "4. Ti restituirò il file finale qui in chat.\n\n"
    "Esempi:\n"
    "- più immagini -> un PDF unico\n"
    "- immagini scannerizzate -> ritaglio bordi e PDF\n"
    "- immagini -> PDF con formato originale oppure A4 con bordi a scelta\n"
    "- un PDF -> comprimi o scala di grigi\n"
    "- un PDF -> estrai pagine, riordinale, eliminale, ruotale o aggiungi un watermark\n"
    "- più PDF -> unisci\n\n"
    "Puoi anche scrivermi richieste semplici come:\n"
    "- fammi un pdf in scala di grigi\n"
    "- ritaglia i bordi e crea un pdf\n"
    "- converti in bianco e nero\n"
    "- unisci questi pdf\n"
    "- comprimi questo pdf\n"
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
    "/reset  (azzera sessione e ultime scelte rapide)"
)

UNAUTHORIZED_MESSAGE = (
    "Questo account non puo usare il bot in questo momento. "
    "Riprova piu tardi oppure contatta l'amministratore di DocMolder."
)

SESSION_EMPTY_MESSAGE = (
    "Non vedo ancora file nella tua sessione. "
    "Inviami immagini o PDF e poi ti proporrò le azioni disponibili."
)

MIXED_SESSION_MESSAGE = (
    "La sessione corrente contiene gia un tipo di file diverso. "
    "Per evitare combinazioni ambigue, usa /reset e riparti con soli PDF oppure sole immagini."
)

FILE_TOO_LARGE_MESSAGE = (
    "Questo file supera il limite consentito per il bot. "
    "Se puoi, prova a inviarne una versione piu leggera oppure dividi il materiale in piu file."
)

UPLOAD_RATE_LIMIT_MESSAGE = (
    "Stai inviando file troppo rapidamente. "
    "Aspetta un attimo e poi riprova con calma."
)

JOB_QUEUE_LIMIT_MESSAGE = (
    "Hai gia troppe operazioni in coda o in lavorazione. "
    "Aspetta che il bot finisca i job gia presi in carico, poi potrai inviarne altri."
)

PROCESSING_MESSAGE = "Sto elaborando i file. Potrebbe volerci qualche secondo."

GENERIC_ERROR_MESSAGE = (
    "Si è verificato un problema durante l'elaborazione. "
    "Riprova tra poco oppure usa /reset per ricominciare."
)

ADMIN_ONLY_MESSAGE = "Questo comando è disponibile solo per l'admin del bot."


def build_pending_action_prompt(action: SupportedAction) -> str:
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
