WELCOME_MESSAGE = (
    "Ciao, sono DocMolder.\n\n"
    "Posso aiutarti a lavorare su immagini e PDF direttamente qui su Telegram.\n\n"
    "Cosa puoi fare:\n"
    "- creare un PDF da una o più immagini\n"
    "- comprimere un PDF\n"
    "- convertire un PDF in scala di grigi\n"
    "- unire più PDF\n"
    "- ruotare un PDF\n"
    "- correggere l'orientamento delle immagini\n\n"
    "Per iniziare, inviami immagini o PDF.\n"
    "Se vuoi, puoi anche usare il menu qui sotto."
)

HELP_MESSAGE = (
    "Ecco come usare DocMolder.\n\n"
    "1. Inviami immagini oppure PDF.\n"
    "2. Ti proporrò solo le azioni compatibili con i file ricevuti.\n"
    "3. Scegli l'azione con i pulsanti.\n"
    "4. Ti restituirò il file finale qui in chat.\n\n"
    "Esempi:\n"
    "- più immagini -> un PDF unico\n"
    "- un PDF -> comprimi, scala di grigi o ruota\n"
    "- più PDF -> unisci\n\n"
    "Puoi anche scrivermi richieste semplici come:\n"
    "- fammi un pdf in scala di grigi\n"
    "- converti in bianco e nero\n"
    "- unisci questi pdf\n"
    "- comprimi questo pdf\n\n"
    "Comandi utili:\n"
    "/start\n"
    "/help\n"
    "/status\n"
    "/reset"
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
