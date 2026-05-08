from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from docmolder.models import FileKind, SessionFile, SupportedAction, UserSession


ACTION_LABELS: dict[SupportedAction, str] = {
    SupportedAction.IMAGES_TO_PDF: "PDF da immagini",
    SupportedAction.IMAGES_TO_PDF_CROP: "PDF da immagini con ritaglio",
    SupportedAction.DOCUMENT_PHOTO_FIX: "Raddrizza foto documento",
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE: "PDF grigio da immagini",
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: "PDF grigio da immagini con ritaglio",
    SupportedAction.PDF_COMPRESS: "Comprimi PDF",
    SupportedAction.PDF_GRAYSCALE: "Scala di grigi",
    SupportedAction.PDF_CROP: "Taglia bordi PDF",
    SupportedAction.PDF_MERGE: "Unisci PDF",
    SupportedAction.PDF_SPLIT: "Dividi PDF",
    SupportedAction.PDF_EXTRACT_PAGES: "Estrai pagine",
    SupportedAction.PDF_REORDER_PAGES: "Riordina pagine",
    SupportedAction.PDF_DELETE_PAGES: "Elimina pagine",
    SupportedAction.PDF_ROTATE: "Ruota pagine",
    SupportedAction.PDF_WATERMARK: "Watermark testuale",
    SupportedAction.EXCEL_UNLOCK_EDITING: "Sblocca modifica Excel",
    SupportedAction.AUTO_ORIENT: "Correggi orientamento",
}

OUTPUT_SUFFIX_BY_ACTION: dict[SupportedAction, str] = {
    SupportedAction.IMAGES_TO_PDF: "pdf",
    SupportedAction.IMAGES_TO_PDF_CROP: "cropped_pdf",
    SupportedAction.DOCUMENT_PHOTO_FIX: "document_photo",
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE: "grayscale",
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE: "cropped_grayscale",
    SupportedAction.PDF_GRAYSCALE: "grayscale",
    SupportedAction.PDF_CROP: "cropped",
    SupportedAction.PDF_COMPRESS: "compressed",
    SupportedAction.PDF_MERGE: "merged",
    SupportedAction.PDF_SPLIT: "split_pages",
    SupportedAction.PDF_EXTRACT_PAGES: "extracted_pages",
    SupportedAction.PDF_REORDER_PAGES: "reordered_pages",
    SupportedAction.PDF_DELETE_PAGES: "deleted_pages",
    SupportedAction.PDF_ROTATE: "rotated",
    SupportedAction.PDF_WATERMARK: "watermarked",
    SupportedAction.EXCEL_UNLOCK_EDITING: "unlocked",
    SupportedAction.AUTO_ORIENT: "oriented",
}

IMAGE_ONLY_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.IMAGES_TO_PDF,
    SupportedAction.IMAGES_TO_PDF_CROP,
    SupportedAction.DOCUMENT_PHOTO_FIX,
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
    SupportedAction.IMAGES_TO_PDF_CROP_GRAYSCALE,
    SupportedAction.AUTO_ORIENT,
)

SINGLE_PDF_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.PDF_GRAYSCALE,
    SupportedAction.PDF_CROP,
    SupportedAction.PDF_COMPRESS,
    SupportedAction.PDF_SPLIT,
    SupportedAction.PDF_EXTRACT_PAGES,
    SupportedAction.PDF_REORDER_PAGES,
    SupportedAction.PDF_DELETE_PAGES,
    SupportedAction.PDF_ROTATE,
    SupportedAction.PDF_WATERMARK,
)

SINGLE_EXCEL_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.EXCEL_UNLOCK_EDITING,
)

RESULT_FOLLOWUP_ACTIONS: tuple[SupportedAction, ...] = (
    SupportedAction.PDF_COMPRESS,
    SupportedAction.PDF_CROP,
    SupportedAction.PDF_GRAYSCALE,
    SupportedAction.PDF_SPLIT,
    SupportedAction.PDF_EXTRACT_PAGES,
    SupportedAction.PDF_REORDER_PAGES,
    SupportedAction.PDF_DELETE_PAGES,
    SupportedAction.PDF_ROTATE,
    SupportedAction.PDF_WATERMARK,
)

PENDING_ACTION_LABELS: dict[str, str] = {
    "images_pdf_layout": "impaginazione PDF da immagini",
    "images_pdf_margin": "bordi impaginazione A4",
}

EXPOSED_ACTION_ORDER: tuple[SupportedAction, ...] = (
    SupportedAction.IMAGES_TO_PDF,
    SupportedAction.IMAGES_TO_PDF_CROP,
    SupportedAction.DOCUMENT_PHOTO_FIX,
    SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
    SupportedAction.PDF_GRAYSCALE,
    SupportedAction.PDF_CROP,
    SupportedAction.PDF_COMPRESS,
    SupportedAction.PDF_MERGE,
    SupportedAction.PDF_SPLIT,
    SupportedAction.PDF_EXTRACT_PAGES,
    SupportedAction.PDF_REORDER_PAGES,
    SupportedAction.PDF_DELETE_PAGES,
    SupportedAction.PDF_ROTATE,
    SupportedAction.PDF_WATERMARK,
    SupportedAction.AUTO_ORIENT,
    SupportedAction.EXCEL_UNLOCK_EDITING,
)


@dataclass(frozen=True, slots=True)
class SessionInventory:
    total_files: int
    image_count: int
    pdf_count: int
    excel_count: int
    file_preview: str

    @property
    def kinds(self) -> frozenset[FileKind]:
        kinds: set[FileKind] = set()
        if self.image_count:
            kinds.add(FileKind.IMAGE)
        if self.pdf_count:
            kinds.add(FileKind.PDF)
        if self.excel_count:
            kinds.add(FileKind.EXCEL)
        return frozenset(kinds)

    @property
    def short_label(self) -> str:
        parts: list[str] = []
        if self.image_count:
            parts.append(f"{self.image_count} immagini")
        if self.pdf_count:
            parts.append(f"{self.pdf_count} PDF")
        if self.excel_count:
            parts.append(f"{self.excel_count} Excel")
        return ", ".join(parts) if parts else "nessun file"


@dataclass(frozen=True, slots=True)
class SessionAnalysis:
    inventory: SessionInventory
    supported_actions: tuple[SupportedAction, ...]
    exposed_actions: tuple[SupportedAction, ...]
    recommended_actions: tuple[SupportedAction, ...]
    advanced_actions: tuple[SupportedAction, ...]
    warnings: tuple[str, ...]
    next_step: str


def infer_session_analysis(session: UserSession) -> SessionAnalysis:
    inventory = _build_session_inventory(session.files)
    supported_actions = _infer_supported_actions(inventory)
    exposed_actions = tuple(action for action in EXPOSED_ACTION_ORDER if action in supported_actions)
    recommended_actions = _infer_recommended_actions(inventory, supported_actions)
    advanced_actions = tuple(action for action in exposed_actions if action not in recommended_actions)
    warnings = _infer_session_warnings(session, inventory, supported_actions)
    next_step = _build_next_step_hint(session, inventory)
    return SessionAnalysis(
        inventory=inventory,
        supported_actions=supported_actions,
        exposed_actions=exposed_actions,
        recommended_actions=recommended_actions,
        advanced_actions=advanced_actions,
        warnings=warnings,
        next_step=next_step,
    )


def infer_supported_actions(session: UserSession) -> list[SupportedAction]:
    return list(infer_session_analysis(session).supported_actions)


def infer_exposed_actions(session: UserSession) -> list[SupportedAction]:
    return list(infer_session_analysis(session).exposed_actions)


def get_action_label(action: SupportedAction | str) -> str:
    try:
        resolved = SupportedAction(action)
    except ValueError:
        raw_action = str(action)
        pending_label = PENDING_ACTION_LABELS.get(raw_action.split(":", 1)[0])
        return pending_label or raw_action
    return ACTION_LABELS.get(resolved, resolved.value)


def build_session_recap(session: UserSession, *, analysis: SessionAnalysis | None = None) -> str:
    analysis = analysis or infer_session_analysis(session)
    lines = [
        "Sessione corrente:",
        f"- File: {analysis.inventory.short_label}",
    ]

    if analysis.inventory.file_preview:
        lines.append(f"- Contenuto: {analysis.inventory.file_preview}")

    if analysis.recommended_actions:
        lines.append(f"- Azioni consigliate: {_format_action_list(analysis.recommended_actions)}")

    if analysis.advanced_actions:
        lines.append(f"- Altre azioni disponibili: {_format_action_list(analysis.advanced_actions, max_items=4)}")

    if analysis.warnings:
        lines.append(f"- Avvisi: {' '.join(analysis.warnings)}")

    lines.append(f"- Prossimo passo: {analysis.next_step}")
    return "\n".join(lines)


def infer_recommended_actions(session: UserSession) -> list[SupportedAction]:
    return list(infer_session_analysis(session).recommended_actions)


def build_next_step_hint(session: UserSession) -> str:
    return infer_session_analysis(session).next_step


def _build_session_inventory(files: list[SessionFile]) -> SessionInventory:
    image_count = 0
    pdf_count = 0
    excel_count = 0
    for item in files:
        if item.kind == FileKind.IMAGE:
            image_count += 1
        elif item.kind == FileKind.PDF:
            pdf_count += 1
        elif item.kind == FileKind.EXCEL:
            excel_count += 1
    return SessionInventory(
        total_files=len(files),
        image_count=image_count,
        pdf_count=pdf_count,
        excel_count=excel_count,
        file_preview=_build_file_preview(files),
    )


def _infer_supported_actions(inventory: SessionInventory) -> tuple[SupportedAction, ...]:
    if inventory.total_files == 0:
        return ()

    if inventory.kinds == frozenset({FileKind.IMAGE}):
        return IMAGE_ONLY_ACTIONS

    if inventory.kinds == frozenset({FileKind.PDF}):
        if inventory.pdf_count > 1:
            return (SupportedAction.PDF_MERGE,)
        if inventory.pdf_count == 1:
            return SINGLE_PDF_ACTIONS

    if inventory.kinds == frozenset({FileKind.EXCEL}) and inventory.excel_count == 1:
        return SINGLE_EXCEL_ACTIONS

    return ()


def _infer_recommended_actions(
    inventory: SessionInventory,
    supported_actions: tuple[SupportedAction, ...],
) -> tuple[SupportedAction, ...]:
    supported = set(supported_actions)
    if not supported:
        return ()

    if inventory.kinds == frozenset({FileKind.IMAGE}):
        ordered_candidates = (
            SupportedAction.IMAGES_TO_PDF,
            SupportedAction.DOCUMENT_PHOTO_FIX,
            SupportedAction.IMAGES_TO_PDF_CROP,
            SupportedAction.IMAGES_TO_PDF_GRAYSCALE,
            SupportedAction.AUTO_ORIENT,
        )
    elif inventory.kinds == frozenset({FileKind.PDF}) and inventory.pdf_count > 1:
        ordered_candidates = (SupportedAction.PDF_MERGE,)
    elif inventory.kinds == frozenset({FileKind.EXCEL}):
        ordered_candidates = (SupportedAction.EXCEL_UNLOCK_EDITING,)
    else:
        ordered_candidates = (
            SupportedAction.PDF_COMPRESS,
            SupportedAction.PDF_CROP,
            SupportedAction.PDF_GRAYSCALE,
            SupportedAction.PDF_EXTRACT_PAGES,
            SupportedAction.PDF_SPLIT,
        )

    return tuple(action for action in ordered_candidates if action in supported)


def _infer_session_warnings(
    session: UserSession,
    inventory: SessionInventory,
    supported_actions: tuple[SupportedAction, ...],
) -> tuple[str, ...]:
    warnings: list[str] = []
    if len(inventory.kinds) > 1:
        warnings.append("La sessione contiene tipi di file diversi: usa /reset e invia un solo tipo di file.")
    elif inventory.total_files and not supported_actions:
        warnings.append("Non vedo azioni compatibili con i file correnti.")
    if session.pending_action:
        warnings.append("Sto aspettando un dettaglio prima di avviare il job.")
    return tuple(warnings)


def _build_next_step_hint(session: UserSession, inventory: SessionInventory) -> str:
    if session.pending_action:
        return f"rispondimi in chat con i dettagli per {get_action_label(session.pending_action).lower()}."

    if inventory.kinds == frozenset({FileKind.IMAGE}):
        if inventory.image_count == 1:
            return "puoi inviarmi altre immagini oppure scegliere già un'azione qui sotto."
        return "scegli se creare un PDF unico, ritagliare i bordi o correggere l'orientamento."
    if inventory.kinds == frozenset({FileKind.PDF}):
        if inventory.pdf_count > 1:
            return 'se vuoi unirli, scegli "Unisci PDF" qui sotto.'
        return 'scegli un\'azione qui sotto oppure scrivimi ad esempio "comprimi questo pdf".'
    if inventory.kinds == frozenset({FileKind.EXCEL}):
        return 'scegli "Sblocca modifica Excel" qui sotto oppure scrivimi "sblocca questo Excel".'
    return "scegli un'azione compatibile qui sotto."


def infer_result_followup_actions(source_action: SupportedAction | str | None) -> list[SupportedAction]:
    try:
        resolved_action = SupportedAction(source_action) if source_action is not None else None
    except ValueError:
        resolved_action = None

    followup_actions = [action for action in RESULT_FOLLOWUP_ACTIONS if action != resolved_action]
    return followup_actions[:4]


def _build_file_preview(files: list[SessionFile], max_items: int = 3) -> str:
    if not files:
        return ""

    displayed_files = [sanitize_filename(item.file_name) for item in files[:max_items]]
    preview = ", ".join(displayed_files)
    remaining = len(files) - len(displayed_files)
    if remaining > 0:
        preview += f" e altri {remaining}"
    return preview


def _format_action_list(actions: Sequence[SupportedAction], max_items: int = 3) -> str:
    labels = [get_action_label(action) for action in actions[:max_items]]
    formatted = ", ".join(labels)
    remaining = len(actions) - len(labels)
    if remaining > 0:
        formatted += f" e altre {remaining}"
    return formatted


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
