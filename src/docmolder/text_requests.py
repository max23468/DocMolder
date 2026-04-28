from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

from docmolder.messages import build_pending_action_prompt as _build_pending_action_prompt
from docmolder.models import CompressionPreset, FileKind, SupportedAction, UserSession
from docmolder.processing import (
    A4_MARGIN_NARROW_PX,
    A4_MARGIN_NONE_PX,
    A4_MARGIN_WIDE_PX,
    ProcessingUserError,
)
from docmolder.action_catalog import infer_supported_actions


@dataclass(slots=True)
class TextRequestResolution:
    kind: Literal["enqueue", "pending", "clarify"]
    action: SupportedAction | None = None
    compression_preset: CompressionPreset | None = None
    rotate_degrees: int | None = None
    page_selection: str | None = None
    watermark_text: str | None = None
    split_output_zip: bool | None = None
    message: str | None = None


def _normalize_free_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def _parse_image_pdf_layout_choice(text: str) -> bool | None:
    normalized = _normalize_free_text(text)
    wants_a4 = "a4" in normalized and _contains_any(normalized, ("si", "sì", "impagina", "usa"))
    wants_original = _contains_any(
        normalized,
        ("mantieni formato originale", "formato originale", "originale", "non impaginare", "no a4"),
    ) or ("no" in normalized and "a4" in normalized)
    if wants_a4:
        return True
    if wants_original:
        return False
    return None


def _parse_image_pdf_margin_choice(text: str) -> int | None:
    normalized = _normalize_free_text(text)
    if _contains_any(normalized, ("senza bordi", "nessun bordo", "nessuno", "no bordi")):
        return A4_MARGIN_NONE_PX
    if _contains_any(normalized, ("bordi larghi", "bordi ampi", "larghi", "ampi")):
        return A4_MARGIN_WIDE_PX
    if _contains_any(normalized, ("bordi stretti", "stretto", "stretti", "narrow")):
        return A4_MARGIN_NARROW_PX
    return None


def _validate_page_input_text(text: str) -> None:
    value = text.strip()
    if not value:
        raise ProcessingUserError("Non ho ricevuto nessuna selezione pagine. Usa un formato come 1,3,5-7.")
    allowed_chars = set("0123456789,- ")
    if any(char not in allowed_chars for char in value):
        raise ProcessingUserError("Usa solo numeri, virgole e intervalli, ad esempio 1,3,5-7.")


def _normalize_page_selection_text(text: str) -> str:
    value = re.sub(r"(?<=\d)\s+(?=\d)", ",", text.strip())
    return re.sub(r"\s*,\s*", ",", value)


def _contains_any(text: str, fragments: tuple[str, ...]) -> bool:
    return any(fragment in text for fragment in fragments)


def _normalize_keyword_text(text: str) -> str:
    normalized = _normalize_free_text(text)
    collapsed = re.sub(r"[^a-z0-9]+", " ", normalized)
    return re.sub(r"\s+", " ", collapsed).strip()


def _tokenize_keyword_text(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text)


def _edit_distance_with_limit(left: str, right: str, limit: int) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    previous_row = list(range(len(right) + 1))
    for index, left_char in enumerate(left, start=1):
        current_row = [index]
        row_min = current_row[0]
        for right_index, right_char in enumerate(right, start=1):
            substitution_cost = 0 if left_char == right_char else 1
            value = min(
                previous_row[right_index] + 1,
                current_row[right_index - 1] + 1,
                previous_row[right_index - 1] + substitution_cost,
            )
            current_row.append(value)
            row_min = min(row_min, value)
        if row_min > limit:
            return limit + 1
        previous_row = current_row
    return previous_row[-1]


def _matches_token_with_typo(token: str, variant: str) -> bool:
    if token == variant:
        return True
    if min(len(token), len(variant)) < 4:
        return False
    limit = 1 if max(len(token), len(variant)) <= 7 else 2
    return _edit_distance_with_limit(token, variant, limit) <= limit


def _matches_keyword_group(text: str, tokens: list[str], variants: tuple[str, ...]) -> bool:
    padded_text = f" {text} "
    for variant in variants:
        normalized_variant = _normalize_keyword_text(variant)
        if not normalized_variant:
            continue
        if " " in normalized_variant:
            if f" {normalized_variant} " in padded_text:
                return True
            continue
        if any(_matches_token_with_typo(token, normalized_variant) for token in tokens):
            return True
    return False


def _extract_compression_preset(text: str, tokens: list[str]) -> CompressionPreset | None:
    if _matches_keyword_group(text, tokens, ("forte", "fortissima", "massima", "spinta", "strong")):
        return CompressionPreset.STRONG
    if _matches_keyword_group(text, tokens, ("leggera", "leggera", "light", "soft", "minima")):
        return CompressionPreset.LIGHT
    if _matches_keyword_group(text, tokens, ("media", "medio", "normale", "standard", "moderata", "medium")):
        return CompressionPreset.MEDIUM
    return None


def _infer_split_output_zip(text: str, tokens: list[str]) -> bool | None:
    padded_text = f" {text} "
    negated_zip_patterns = (
        r"\bsenza\s+(?:lo\s+|il\s+|uno\s+|un\s+)?zip\b",
        r"\bno\s+(?:allo\s+|al\s+|lo\s+|il\s+)?zip\b",
        r"\bnon\s+(?:in\s+|come\s+|lo\s+|il\s+)?zip\b",
    )
    if any(re.search(pattern, text) for pattern in negated_zip_patterns):
        return False
    if any(
        fragment in padded_text
        for fragment in (" pdf separati ", " file separati ", " singoli file ", " pagine separate ", " uno per pagina ")
    ):
        return False
    if "zip" in tokens or "archivio" in tokens:
        return True
    if any(token in {"separati", "separate", "singoli"} for token in tokens):
        return False
    return None


def _build_page_action_clarification(page_selection: str | None) -> str:
    selection_suffix = f" ({page_selection})" if page_selection else ""
    return (
        "Ho capito che stai parlando di pagine, ma non mi e ancora chiaro cosa vuoi fare"
        f"{selection_suffix}.\n"
        "Posso fare una cosa per volta: `estrai pagine`, `elimina pagine` oppure `riordina pagine`."
    )


def _build_multi_action_clarification(actions: tuple[str, str]) -> str:
    return (
        "In questa frase vedo piu operazioni insieme.\n"
        f"Posso eseguire una cosa per volta: `{actions[0]}` oppure `{actions[1]}`.\n"
        "Dimmi quale vuoi fare adesso e la prendo subito in carico."
    )


def _resolve_text_request(session: UserSession, text: str) -> TextRequestResolution | None:
    normalized_text = _normalize_free_text(text)
    keyword_text = _normalize_keyword_text(text)
    tokens = _tokenize_keyword_text(keyword_text)
    supported = set(infer_supported_actions(session))
    session_kinds = {item.kind for item in session.files}

    mentions_grayscale = _matches_keyword_group(
        keyword_text,
        tokens,
        ("scala di grigi", "bianco e nero", "bianco nero", "grayscale", "grigio", "monocromatico"),
    )
    mentions_pdf = _matches_keyword_group(
        keyword_text,
        tokens,
        ("pdf", "documento", "file"),
    )
    mentions_crop = _matches_keyword_group(
        keyword_text,
        tokens,
        (
            "ritaglia",
            "ritaglio",
            "bordi",
            "margini",
            "scannerizza",
            "scansiona",
            "scannerizzato",
            "scansionato",
            "scansione",
            "foglio",
        ),
    )
    mentions_merge = _matches_keyword_group(
        keyword_text,
        tokens,
        ("unisci", "accorpa", "merge", "combina", "raggruppa"),
    )
    mentions_split = _matches_keyword_group(
        keyword_text,
        tokens,
        ("dividi", "dividilo", "dividere", "separa", "separalo", "separare", "split", "splitta", "spezza", "spezzalo"),
    )
    mentions_compress = _matches_keyword_group(
        keyword_text,
        tokens,
        (
            "comprimi",
            "comprimilo",
            "compressione",
            "alleggerisci",
            "alleggeriscilo",
            "riduci",
            "riducilo",
            "ottimizza",
            "ottimizzalo",
            "peso",
            "piu leggero",
        ),
    )
    mentions_auto_orient = _matches_keyword_group(
        keyword_text,
        tokens,
        ("orientamento", "raddrizza", "raddrizzare", "addrizza", "dritto"),
    )
    mentions_document_photo_fix = _matches_keyword_group(
        keyword_text,
        tokens,
        (
            "raddrizza foto documento",
            "sistema foto documento",
            "migliora foto documento",
            "foto documento",
            "foto del documento",
            "foglio storto",
            "raddrizza foglio",
            "sistema foglio",
            "correggi prospettiva",
            "prospettiva",
            "foto storta",
            "scansiona documento",
            "scansiona questo foglio",
        ),
    )
    mentions_rotate = _matches_keyword_group(
        keyword_text,
        tokens,
        ("ruota", "ruotalo", "rotazione", "gira", "giralo", "girare", "capovolgi", "capovolgilo"),
    )
    mentions_extract = _matches_keyword_group(
        keyword_text,
        tokens,
        ("estrai", "estrazione", "prendi", "tieni", "mantieni", "conserva"),
    )
    mentions_delete = _matches_keyword_group(
        keyword_text,
        tokens,
        ("elimina", "rimuovi", "cancella", "togli", "scarta"),
    )
    mentions_reorder = _matches_keyword_group(
        keyword_text,
        tokens,
        ("riordina", "riordinare", "ordina", "sequenza", "ordine"),
    )
    mentions_watermark = _matches_keyword_group(
        keyword_text,
        tokens,
        ("watermark", "filigrana", "timbro"),
    )
    mentions_pdf_creation = _matches_keyword_group(
        keyword_text,
        tokens,
        (
            "crea pdf",
            "fai pdf",
            "fallo pdf",
            "fanne pdf",
            "genera pdf",
            "converti in pdf",
            "trasforma in pdf",
            "trasformale in pdf",
            "mettile in pdf",
            "in pdf",
        ),
    )
    page_selection = _extract_page_selection_from_text(normalized_text, allow_keywordless_sequence=True)
    rotate_degrees = _extract_rotation_degrees(keyword_text)
    watermark_text = _extract_watermark_text(text)
    compression_preset = _extract_compression_preset(keyword_text, tokens)
    split_output_zip = _infer_split_output_zip(keyword_text, tokens)

    if SupportedAction.PDF_ROTATE in supported and mentions_rotate:
        if rotate_degrees is not None:
            return TextRequestResolution(
                kind="enqueue",
                action=SupportedAction.PDF_ROTATE,
                rotate_degrees=rotate_degrees,
            )
        return TextRequestResolution(
            kind="pending",
            action=SupportedAction.PDF_ROTATE,
            message=_build_pending_action_prompt(SupportedAction.PDF_ROTATE),
        )

    if SupportedAction.PDF_WATERMARK in supported and mentions_watermark:
        if watermark_text:
            return TextRequestResolution(
                kind="enqueue",
                action=SupportedAction.PDF_WATERMARK,
                watermark_text=watermark_text,
            )
        return TextRequestResolution(
            kind="pending",
            action=SupportedAction.PDF_WATERMARK,
            message=_build_pending_action_prompt(SupportedAction.PDF_WATERMARK),
        )

    page_action_matches: list[SupportedAction] = []
    if SupportedAction.PDF_EXTRACT_PAGES in supported and mentions_extract:
        page_action_matches.append(SupportedAction.PDF_EXTRACT_PAGES)
    if SupportedAction.PDF_DELETE_PAGES in supported and mentions_delete:
        page_action_matches.append(SupportedAction.PDF_DELETE_PAGES)
    if SupportedAction.PDF_REORDER_PAGES in supported and mentions_reorder:
        page_action_matches.append(SupportedAction.PDF_REORDER_PAGES)

    if len(page_action_matches) > 1:
        return TextRequestResolution(kind="clarify", message=_build_page_action_clarification(page_selection))

    if len(page_action_matches) == 1:
        selected_page_action = page_action_matches[0]
        if page_selection:
            return TextRequestResolution(
                kind="enqueue",
                action=selected_page_action,
                page_selection=page_selection,
            )
        return TextRequestResolution(
            kind="pending",
            action=selected_page_action,
            message=_build_pending_action_prompt(selected_page_action),
        )

    if page_selection and session_kinds == {FileKind.PDF}:
        return TextRequestResolution(kind="clarify", message=_build_page_action_clarification(page_selection))

    if SupportedAction.PDF_MERGE in supported and mentions_merge:
        return TextRequestResolution(kind="enqueue", action=SupportedAction.PDF_MERGE)

    if SupportedAction.PDF_SPLIT in supported and mentions_split:
        if split_output_zip is None:
            return TextRequestResolution(
                kind="pending",
                action=SupportedAction.PDF_SPLIT,
                message=_build_pending_action_prompt(SupportedAction.PDF_SPLIT),
            )
        return TextRequestResolution(
            kind="enqueue",
            action=SupportedAction.PDF_SPLIT,
            split_output_zip=split_output_zip,
        )

    if SupportedAction.PDF_COMPRESS in supported and SupportedAction.PDF_GRAYSCALE in supported:
        if mentions_compress and mentions_grayscale:
            return TextRequestResolution(
                kind="clarify",
                message=_build_multi_action_clarification(("comprimi il PDF", "converti il PDF in scala di grigi")),
            )

    if SupportedAction.PDF_COMPRESS in supported and mentions_compress:
        return TextRequestResolution(
            kind="enqueue",
            action=SupportedAction.PDF_COMPRESS,
            compression_preset=compression_preset,
        )

    if SupportedAction.PDF_GRAYSCALE in supported and mentions_grayscale:
        return TextRequestResolution(kind="enqueue", action=SupportedAction.PDF_GRAYSCALE)

    if session_kinds == {FileKind.IMAGE}:
        if SupportedAction.DOCUMENT_PHOTO_FIX in supported and (
            mentions_document_photo_fix or (mentions_crop and "foglio" in tokens and mentions_auto_orient)
        ):
            return TextRequestResolution(kind="enqueue", action=SupportedAction.DOCUMENT_PHOTO_FIX)
        if SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE in supported and mentions_crop and mentions_grayscale:
            return TextRequestResolution(kind="enqueue", action=SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE)
        if SupportedAction.IMAGES_TO_PDF_CROP in supported and mentions_crop and (mentions_pdf or mentions_grayscale or mentions_pdf_creation):
            return TextRequestResolution(kind="enqueue", action=SupportedAction.IMAGES_TO_PDF_CROP)
        if SupportedAction.IMAGES_TO_PDF_GRAYSCALE in supported and mentions_grayscale:
            return TextRequestResolution(kind="enqueue", action=SupportedAction.IMAGES_TO_PDF_GRAYSCALE)
        if SupportedAction.IMAGES_TO_PDF in supported and (mentions_pdf or mentions_pdf_creation):
            return TextRequestResolution(kind="enqueue", action=SupportedAction.IMAGES_TO_PDF)

    if SupportedAction.AUTO_ORIENT in supported and mentions_auto_orient and not mentions_rotate:
        return TextRequestResolution(kind="enqueue", action=SupportedAction.AUTO_ORIENT)

    return None


def _extract_rotation_degrees(text: str) -> int | None:
    for pattern, degrees in (
        (r"\b90\b", 90),
        (r"\b180\b", 180),
        (r"\b270\b", 270),
        (r"\bnovanta\b", 90),
        (r"\bcentottanta\b", 180),
        (r"\bduecentosettanta\b", 270),
        (r"\bmezzo giro\b", 180),
    ):
        if re.search(pattern, text):
            return degrees
    if "destra" in text:
        return 90
    if "sinistra" in text:
        return 270
    return None


def _extract_page_selection_from_text(text: str, *, allow_keywordless_sequence: bool = False) -> str | None:
    cleaned_text = re.sub(r"\b(?:e|ed|poi)\b", ",", text)
    match = re.search(r"(?:pagina|pagine)\s+([0-9,\-\s,]+)", cleaned_text)
    if match:
        return _normalize_page_selection_text(match.group(1))
    match = re.search(
        r"(?:estrai|estrazione|prendi|tieni|mantieni|conserva|elimina|rimuovi|cancella|togli|riordina|ordina)\s+([0-9,\-\s,]+)",
        cleaned_text,
    )
    if match:
        return _normalize_page_selection_text(match.group(1))
    if allow_keywordless_sequence:
        match = re.search(r"([0-9][0-9,\-\s,]+)$", cleaned_text.strip())
        if match:
            return _normalize_page_selection_text(match.group(1))
    return None


def _extract_watermark_text(text: str) -> str | None:
    quoted_match = re.search(r"[\"'“”](.+?)[\"'“”]", text)
    if quoted_match is not None:
        watermark_text = quoted_match.group(1).strip()
        if watermark_text:
            return watermark_text
    match = re.search(
        r"(?:watermark|filigrana|timbro)(?:\s+testuale)?(?:\s+(?:con|testo|scritta))?[:\s]+(.+)$",
        text,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    watermark_text = match.group(1).strip().strip("\"'“”")
    watermark_text = re.sub(r"^(?:testo|scritta)\s+", "", watermark_text, flags=re.IGNORECASE)
    return watermark_text or None


def _build_quick_action_guidance(session: UserSession | None, text: str) -> str | None:
    normalized = _normalize_free_text(text)

    if text in {"Crea PDF", "Crea PDF da immagini"}:
        if session is None or not session.files:
            return "Inviami una o piu immagini e creerò un PDF unico. Se vuoi, puoi mandarne diverse nella stessa sessione."
        if {item.kind for item in session.files} == {FileKind.PDF}:
            return "Per creare un PDF da immagini devo partire da foto o scansioni. Usa /reset e inviami una o piu immagini."

    if text == "Comprimi PDF":
        if session is None or not session.files:
            return "Inviami un PDF e potrò comprimerlo subito. Se ne mandi uno solo, ti proporrò anche i livelli di compressione."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Per comprimere serve un PDF. Se vuoi, posso prima trasformare le immagini in un PDF."
        if len(session.files) > 1:
            return "Per comprimere serve un solo PDF nella sessione corrente. Inviamene uno solo oppure unisci prima i file."

    if text == "Unisci PDF":
        if session is None or not session.files:
            return "Inviami due o piu PDF nella stessa sessione e li unirò in un file unico."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Per unire servono PDF, non immagini. Se vuoi, posso prima creare un PDF dalle immagini che hai inviato."
        if len(session.files) == 1:
            return "Per unire i PDF me ne servono almeno due nella stessa sessione."

    if "foto in a4" in normalized or "immagini in a4" in normalized:
        if session is None or not session.files:
            return "Inviami una o piu immagini e ti guidero subito verso un PDF impaginato in A4."
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return "Perfetto: scegli 'PDF da immagini' e poi conferma l'impaginazione A4. Se vuoi, puoi anche aggiungere altre foto prima."
        return "Per il template 'foto in A4' devo partire da immagini o foto, non da PDF."

    if "scansiona e comprimi" in normalized or ("scansiona" in normalized and "comprimi" in normalized):
        if session is None or not session.files:
            return (
                "Inviami una o piu foto del documento. Ti conviene partire con un PDF da immagini, meglio ancora con ritaglio bordi, "
                "e poi comprimere il risultato finale con un secondo passaggio guidato."
            )
        if {item.kind for item in session.files} == {FileKind.IMAGE}:
            return (
                "Per questo flusso ti conviene: 1) creare un PDF da immagini, meglio con ritaglio bordi se serve; "
                "2) comprimere il PDF finale dal messaggio risultato, senza ricaricarlo."
            )
        if {item.kind for item in session.files} == {FileKind.PDF}:
            return "Se hai gia un PDF, puoi saltare la parte scansione e comprimere direttamente il file corrente."

    return None
