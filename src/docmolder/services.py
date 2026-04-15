from __future__ import annotations

from pathlib import Path

from docmolder.models import FileKind, SessionFile, SupportedAction, UserSession


ACTION_LABELS: dict[SupportedAction, str] = {
    SupportedAction.IMAGES_TO_PDF: "PDF da immagini",
    SupportedAction.IMAGES_TO_PDF_CROP: "PDF con ritaglio bordi",
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE: "PDF grigio da immagini",
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: "PDF grigio con ritaglio bordi",
    SupportedAction.PDF_COMPRESS: "Comprimi PDF",
    SupportedAction.PDF_GRAYSCALE: "Scala di grigi",
    SupportedAction.PDF_MERGE: "Unisci PDF",
    SupportedAction.PDF_EXTRACT_PAGES: "Estrai pagine",
    SupportedAction.PDF_REORDER_PAGES: "Riordina pagine",
    SupportedAction.PDF_DELETE_PAGES: "Elimina pagine",
    SupportedAction.PDF_ROTATE: "Ruota pagine",
    SupportedAction.PDF_WATERMARK: "Watermark testuale",
    SupportedAction.AUTO_ORIENT: "Correggi orientamento",
}

OUTPUT_SUFFIX_BY_ACTION: dict[SupportedAction, str] = {
    SupportedAction.IMAGES_TO_PDF: "pdf",
    SupportedAction.IMAGES_TO_PDF_CROP: "cropped_pdf",
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE: "grayscale",
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: "cropped_grayscale",
    SupportedAction.PDF_GRAYSCALE: "grayscale",
    SupportedAction.PDF_COMPRESS: "compressed",
    SupportedAction.PDF_MERGE: "merged",
    SupportedAction.PDF_EXTRACT_PAGES: "extracted_pages",
    SupportedAction.PDF_REORDER_PAGES: "reordered_pages",
    SupportedAction.PDF_DELETE_PAGES: "deleted_pages",
    SupportedAction.PDF_ROTATE: "rotated",
    SupportedAction.PDF_WATERMARK: "watermarked",
    SupportedAction.AUTO_ORIENT: "oriented",
}

IMAGE_ONLY_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.IMAGES_TO_PDF,
    SupportedAction.IMAGES_TO_PDF_CROP,
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    SupportedAction.AUTO_ORIENT,
)

SINGLE_PDF_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.PDF_GRAYSCALE,
    SupportedAction.PDF_COMPRESS,
    SupportedAction.PDF_EXTRACT_PAGES,
    SupportedAction.PDF_REORDER_PAGES,
    SupportedAction.PDF_DELETE_PAGES,
    SupportedAction.PDF_ROTATE,
    SupportedAction.PDF_WATERMARK,
)

EXPOSED_ACTION_ORDER: tuple[SupportedAction, ...] = (
    SupportedAction.IMAGES_TO_PDF,
    SupportedAction.IMAGES_TO_PDF_CROP,
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
    SupportedAction.PDF_GRAYSCALE,
    SupportedAction.PDF_COMPRESS,
    SupportedAction.PDF_MERGE,
    SupportedAction.PDF_EXTRACT_PAGES,
    SupportedAction.PDF_REORDER_PAGES,
    SupportedAction.PDF_DELETE_PAGES,
    SupportedAction.PDF_ROTATE,
    SupportedAction.PDF_WATERMARK,
    SupportedAction.AUTO_ORIENT,
)


def infer_supported_actions(session: UserSession) -> list[SupportedAction]:
    if not session.files:
        return []

    kinds = {item.kind for item in session.files}
    actions: list[SupportedAction] = []

    if kinds == {FileKind.IMAGE}:
        actions.extend(IMAGE_ONLY_ACTIONS)

    if kinds == {FileKind.PDF}:
        if len(session.files) > 1:
            actions.append(SupportedAction.PDF_MERGE)
        if len(session.files) == 1:
            actions.extend(SINGLE_PDF_ACTIONS)

    return actions


def infer_exposed_actions(session: UserSession) -> list[SupportedAction]:
    supported = set(infer_supported_actions(session))
    return [action for action in EXPOSED_ACTION_ORDER if action in supported]


def get_action_label(action: SupportedAction | str) -> str:
    try:
        resolved = SupportedAction(action)
    except ValueError:
        return str(action)
    return ACTION_LABELS.get(resolved, resolved.value)


def describe_session(session: UserSession) -> str:
    images = sum(1 for item in session.files if item.kind == FileKind.IMAGE)
    pdfs = sum(1 for item in session.files if item.kind == FileKind.PDF)

    parts: list[str] = []
    if images:
        parts.append(f"{images} immagini")
    if pdfs:
        parts.append(f"{pdfs} PDF")

    summary = ", ".join(parts) if parts else "nessun file"
    return f"Sessione corrente: {summary}."


def build_session_file(file_id: str, file_name: str | None, kind: FileKind) -> SessionFile:
    normalized_name = file_name or f"{kind.value}_{file_id[:8]}"
    return SessionFile(
        telegram_file_id=file_id,
        file_name=normalized_name,
        kind=kind,
    )


def build_output_stem(action: SupportedAction, files: list[SessionFile]) -> str:
    base_name = _build_output_base_name(files)
    return f"{base_name}_{OUTPUT_SUFFIX_BY_ACTION[action]}"


def _build_output_base_name(files: list[SessionFile]) -> str:
    if not files:
        return "docmolder"

    primary_name = sanitize_filename(files[0].file_name)
    primary_stem = Path(primary_name).stem or "file"
    if len(files) == 1:
        return primary_stem[:80]
    return f"{primary_stem[:60]}_{len(files)}_files"


def sanitize_filename(file_name: str) -> str:
    path = Path(file_name)
    stem = path.stem or "file"
    suffix = path.suffix
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return f"{safe_stem[:80] or 'file'}{suffix.lower()}"
