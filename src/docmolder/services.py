from __future__ import annotations

from pathlib import Path

from docmolder.models import FileKind, SessionFile, SupportedAction, UserSession


def infer_supported_actions(session: UserSession) -> list[SupportedAction]:
    if not session.files:
        return []

    kinds = {item.kind for item in session.files}
    actions: list[SupportedAction] = []

    if kinds == {FileKind.IMAGE}:
        actions.extend(
            [
                SupportedAction.IMAGES_TO_PDF,
                SupportedAction.IMAGES_TO_PDF_CROP,
                SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
                SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
                SupportedAction.AUTO_ORIENT,
            ]
        )

    if kinds == {FileKind.PDF}:
        if len(session.files) > 1:
            actions.append(SupportedAction.PDF_MERGE)
        if len(session.files) == 1:
            actions.extend(
                [
                    SupportedAction.PDF_GRAYSCALE,
                    SupportedAction.PDF_COMPRESS,
                    SupportedAction.PDF_ROTATE,
                ]
            )

    return actions


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


def build_output_stem(action: SupportedAction) -> str:
    labels = {
        SupportedAction.IMAGES_TO_PDF: "docmolder_pdf",
        SupportedAction.IMAGES_TO_PDF_CROP: "docmolder_cropped_pdf",
        SupportedAction.IMAGES_TO_PDF_GRAYSCALE: "docmolder_grayscale",
        SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: "docmolder_cropped_grayscale",
        SupportedAction.PDF_GRAYSCALE: "docmolder_grayscale",
        SupportedAction.PDF_COMPRESS: "docmolder_compressed",
        SupportedAction.PDF_MERGE: "docmolder_merged",
        SupportedAction.PDF_ROTATE: "docmolder_rotated",
        SupportedAction.AUTO_ORIENT: "docmolder_oriented",
    }
    return labels[action]


def sanitize_filename(file_name: str) -> str:
    path = Path(file_name)
    stem = path.stem or "file"
    suffix = path.suffix
    safe_stem = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in stem)
    return f"{safe_stem[:80] or 'file'}{suffix.lower()}"
