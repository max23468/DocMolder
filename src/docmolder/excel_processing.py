from __future__ import annotations

from pathlib import Path

from docmolder.excel_unlock import ExcelUnlockError, ExcelUnlocker
from docmolder.processing_models import ProcessingResult, ProcessingUserError


class ExcelProcessor:
    """Capacità Excel mirata: rimuove protezioni di modifica da file apribili."""

    def __init__(self, runtime_dir: Path, libreoffice_timeout_seconds: int) -> None:
        self.unlocker = ExcelUnlocker(
            runtime_dir=runtime_dir,
            libreoffice_timeout_seconds=max(1, libreoffice_timeout_seconds),
        )

    def unlock_editing(self, excel_path: Path, output_stem: str) -> ProcessingResult:
        try:
            unlocked = self.unlocker.unlock_editing(excel_path, output_stem)
        except ExcelUnlockError as exc:
            raise ProcessingUserError(str(exc)) from exc
        return ProcessingResult(
            output_path=unlocked.path,
            output_name=unlocked.name,
            message=(
                "Excel pronto. Ho creato una copia nello stesso formato rimuovendo le protezioni di modifica "
                f"trovate ({unlocked.removed_protection_count})."
            ),
            processing_mode=f"excel-{unlocked.mode}",
        )
