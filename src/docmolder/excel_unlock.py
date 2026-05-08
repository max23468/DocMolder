from __future__ import annotations

import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import textwrap
import zipfile
from dataclasses import dataclass
from importlib import import_module, util
from pathlib import Path
from types import ModuleType

logger = logging.getLogger(__name__)

OOXML_EXCEL_SUFFIXES = {".xlsx", ".xlsm"}
LIBREOFFICE_EXCEL_SUFFIXES = {".xls"}
ASPOSE_EXCEL_SUFFIXES = {".xlsb"}
SUPPORTED_EXCEL_SUFFIXES = OOXML_EXCEL_SUFFIXES | LIBREOFFICE_EXCEL_SUFFIXES | ASPOSE_EXCEL_SUFFIXES

_OOXML_PROTECTION_TAGS = (
    "sheetProtection",
    "workbookProtection",
    "fileSharing",
    "protectedRanges",
)

_OOXML_PROTECTION_PATTERNS = tuple(
    pattern
    for tag in _OOXML_PROTECTION_TAGS
    for pattern in (
        re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?%b\b[^>]*/>" % tag.encode("ascii"), re.DOTALL),
        re.compile(rb"<(?:[A-Za-z_][\w.-]*:)?%b\b[^>]*>.*?</(?:[A-Za-z_][\w.-]*:)?%b>" % (tag.encode("ascii"), tag.encode("ascii")), re.DOTALL),
    )
)


@dataclass(frozen=True, slots=True)
class ExcelUnlockResult:
    path: Path
    name: str
    removed_protection_count: int
    mode: str


class ExcelUnlockError(Exception):
    pass


class ExcelUnlocker:
    def __init__(
        self,
        runtime_dir: Path,
        *,
        libreoffice_timeout_seconds: int = 120,
        aspose_cells_license_path: Path | None = None,
    ) -> None:
        self.runtime_dir = runtime_dir
        self.libreoffice_timeout_seconds = max(1, libreoffice_timeout_seconds)
        self.aspose_cells_license_path = aspose_cells_license_path

    def unlock_editing(self, input_path: Path, output_stem: str) -> ExcelUnlockResult:
        suffix = input_path.suffix.lower()
        if suffix not in SUPPORTED_EXCEL_SUFFIXES:
            raise ExcelUnlockError(
                "Questo file Excel non è in un formato supportato. "
                "Posso lavorare su .xlsx, .xlsm, .xls e .xlsb."
            )
        output_path = input_path.with_name(f"{output_stem}{suffix}")
        if suffix in OOXML_EXCEL_SUFFIXES:
            removed_count = self._unlock_ooxml_excel(input_path, output_path)
            return ExcelUnlockResult(
                path=output_path,
                name=output_path.name,
                removed_protection_count=removed_count,
                mode="ooxml",
            )
        if suffix in ASPOSE_EXCEL_SUFFIXES:
            removed_count = self._unlock_xlsb_with_aspose(input_path, output_path)
            return ExcelUnlockResult(
                path=output_path,
                name=output_path.name,
                removed_protection_count=removed_count,
                mode="aspose",
            )
        removed_count = self._unlock_binary_excel_with_libreoffice(input_path, output_path)
        return ExcelUnlockResult(
            path=output_path,
            name=output_path.name,
            removed_protection_count=removed_count,
            mode="libreoffice",
        )

    def _unlock_ooxml_excel(self, input_path: Path, output_path: Path) -> int:
        removed_count = 0
        try:
            with zipfile.ZipFile(input_path, "r") as source, zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as target:
                for item in source.infolist():
                    data = source.read(item.filename)
                    cleaned = data
                    if item.filename.endswith(".xml") and item.filename.startswith("xl/"):
                        cleaned, item_removed_count = _remove_ooxml_protection_tags(cleaned)
                        removed_count += item_removed_count
                    target.writestr(item, cleaned)
        except zipfile.BadZipFile as exc:
            raise ExcelUnlockError(
                "Questo Excel sembra cifrato, corrotto o non leggibile come file Office moderno. "
                "Per ora posso sbloccare solo file che si aprono già senza password."
            ) from exc
        except OSError as exc:
            raise ExcelUnlockError("Non riesco a leggere questo Excel o a creare la copia sbloccata.") from exc

        if removed_count == 0:
            raise ExcelUnlockError(
                "Non ho trovato protezioni di modifica da rimuovere in questo Excel. "
                "Se il file chiede una password all'apertura, non posso sbloccarlo senza quella password."
            )
        return removed_count

    def _unlock_xlsb_with_aspose(self, input_path: Path, output_path: Path) -> int:
        if self.aspose_cells_license_path is None:
            raise ExcelUnlockError(
                "Per sbloccare Excel .xlsb mantenendo il formato originale serve Aspose.Cells con licenza "
                "configurata sul server. Non uso Aspose in modalità evaluation perché aggiunge fogli watermark "
                "al file; con LibreOffice non posso salvare una copia .xlsb affidabile."
            )
        if not self.aspose_cells_license_path.is_file():
            raise ExcelUnlockError(
                "La licenza Aspose.Cells configurata per sbloccare .xlsb non è disponibile sul server."
            )
        try:
            cells = _load_aspose_cells_module()
            license_obj = cells.License()
            license_obj.set_license(str(self.aspose_cells_license_path))
            workbook = cells.Workbook(str(input_path))
        except ExcelUnlockError:
            raise
        except Exception as exc:
            logger.warning("Configurazione Aspose.Cells non utilizzabile per .xlsb: %s", str(exc)[:500])
            raise ExcelUnlockError(
                "Aspose.Cells non è configurato correttamente per sbloccare Excel .xlsb sul server."
            ) from exc

        removed_count = 0
        try:
            settings = getattr(workbook, "settings", None)
            if settings is not None and bool(getattr(settings, "is_protected", False)):
                _unprotect_aspose_workbook(workbook)
                if not bool(getattr(settings, "is_protected", False)):
                    removed_count += 1
            worksheets = workbook.worksheets
            for index in range(len(worksheets)):
                sheet = _get_aspose_worksheet(worksheets, index)
                if bool(getattr(sheet, "is_protected", False)):
                    _unprotect_aspose_sheet(sheet)
                    if not bool(getattr(sheet, "is_protected", False)):
                        removed_count += 1
            workbook.save(str(output_path), cells.SaveFormat.XLSB)
        except ExcelUnlockError:
            raise
        except Exception as exc:
            logger.warning("Sblocco Excel .xlsb via Aspose.Cells non riuscito: %s", str(exc)[:500])
            raise ExcelUnlockError(
                "Aspose.Cells non è riuscito a rimuovere la protezione di modifica da questo Excel .xlsb. "
                "Se il foglio richiede davvero una password per essere sbloccato, non posso aggirarla senza password."
            ) from exc

        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ExcelUnlockError("Aspose.Cells non ha creato una copia .xlsb valida.")
        if removed_count == 0:
            raise ExcelUnlockError(
                "Non ho trovato fogli o workbook protetti da sbloccare in questo Excel .xlsb."
            )
        return removed_count

    def _unlock_binary_excel_with_libreoffice(self, input_path: Path, output_path: Path) -> int:
        libreoffice = _find_libreoffice_binary()
        if libreoffice is None:
            raise ExcelUnlockError(
                "Per sbloccare Excel .xls mantenendo il formato originale serve LibreOffice sul server. "
                "Installa LibreOffice e riprova, oppure invia una copia .xlsx/.xlsm."
            )

        with tempfile.TemporaryDirectory(prefix="docmolder_lo_", dir=self.runtime_dir) as raw_tmp_dir:
            tmp_dir = Path(raw_tmp_dir)
            profile_dir = tmp_dir / "profile"
            profile_dir.mkdir(parents=True, exist_ok=True)
            port = _pick_local_port()
            try:
                office = subprocess.Popen(
                    [
                        libreoffice,
                        "--headless",
                        "--invisible",
                        "--norestore",
                        "--nodefault",
                        "--nolockcheck",
                        f"-env:UserInstallation={profile_dir.as_uri()}",
                        f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except OSError as exc:
                raise ExcelUnlockError("Non riesco ad avviare LibreOffice per lavorare questo Excel.") from exc
            try:
                script_path = tmp_dir / "unlock_excel_uno.py"
                script_path.write_text(_build_uno_unlock_script(), encoding="utf-8")
                completed = subprocess.run(
                    [
                        _find_uno_python(),
                        str(script_path),
                        str(port),
                        str(input_path),
                        str(output_path),
                        _libreoffice_filter_for_suffix(input_path.suffix.lower()),
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.libreoffice_timeout_seconds,
                    env=_libreoffice_python_env(),
                )
            except subprocess.TimeoutExpired as exc:
                raise ExcelUnlockError(
                    "LibreOffice ha impiegato troppo tempo a sbloccare questo Excel. "
                    "Riprova con un file più leggero o una copia .xlsx."
                ) from exc
            except OSError as exc:
                raise ExcelUnlockError("Non riesco ad avviare il bridge Python di LibreOffice.") from exc
            finally:
                office.terminate()
                try:
                    office.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    office.kill()
                    office.wait(timeout=5)

        if completed.returncode != 0:
            stderr = (completed.stderr or completed.stdout or "").strip()
            logger.warning("Sblocco Excel via LibreOffice non riuscito: %s", stderr[:500])
            raise ExcelUnlockError(
                "LibreOffice non è riuscito a rimuovere la protezione di modifica da questo Excel. "
                "Se il foglio richiede davvero una password per essere sbloccato, non posso aggirarla senza password."
            )
        if not output_path.exists() or output_path.stat().st_size == 0:
            raise ExcelUnlockError("LibreOffice non ha creato una copia Excel valida.")
        removed_count = _parse_uno_removed_count(completed.stdout)
        if removed_count == 0:
            raise ExcelUnlockError(
                "Non ho trovato fogli protetti da sbloccare in questo Excel, oppure LibreOffice li ha mantenuti protetti."
            )
        return removed_count


def _remove_ooxml_protection_tags(data: bytes) -> tuple[bytes, int]:
    removed_count = 0
    cleaned = data
    for pattern in _OOXML_PROTECTION_PATTERNS:
        cleaned, count = pattern.subn(b"", cleaned)
        removed_count += count
    return cleaned, removed_count


def _find_libreoffice_binary() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def _find_uno_python() -> str:
    return shutil.which("python3") or shutil.which("python") or "python3"


def _load_aspose_cells_module() -> ModuleType:
    try:
        module_spec = util.find_spec("aspose.cells")
    except ModuleNotFoundError:
        module_spec = None
    if module_spec is None:
        raise ExcelUnlockError(
            "Il supporto .xlsb richiede il pacchetto Python aspose-cells-python installato sul server."
        )
    os.environ.setdefault("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")
    return import_module("aspose.cells")


def _get_aspose_worksheet(worksheets: object, index: int) -> object:
    get_worksheet = getattr(worksheets, "get", None)
    if callable(get_worksheet):
        return get_worksheet(index)
    return worksheets[index]  # type: ignore[index]


def _unprotect_aspose_workbook(workbook: object) -> None:
    try:
        workbook.unprotect("")
    except Exception as exc:
        raise ExcelUnlockError(
            "Questo Excel .xlsb ha la struttura workbook protetta da una password reale. "
            "Non posso aggirarla senza password."
        ) from exc


def _unprotect_aspose_sheet(sheet: object) -> None:
    sheet_name = str(getattr(sheet, "name", "") or "un foglio")
    try:
        sheet.unprotect()
    except Exception as exc:
        raise ExcelUnlockError(
            f"Questo Excel .xlsb ha {sheet_name} protetto da una password reale. "
            "Non posso aggirarla senza password."
        ) from exc


def _pick_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _libreoffice_filter_for_suffix(suffix: str) -> str:
    if suffix == ".xls":
        return "MS Excel 97"
    raise ExcelUnlockError("Formato Excel binario non supportato.")


def _libreoffice_python_env() -> dict[str, str]:
    env = os.environ.copy()
    candidates = [
        "/usr/lib/libreoffice/program",
        "/usr/lib64/libreoffice/program",
        "/usr/lib/python3/dist-packages",
    ]
    existing = [path for path in candidates if Path(path).exists()]
    if existing:
        current = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join([*existing, current] if current else existing)
    return env


def _build_uno_unlock_script() -> str:
    return textwrap.dedent(
        r'''
        from __future__ import annotations

        import sys
        import time

        import uno
        from com.sun.star.beans import PropertyValue


        def prop(name, value):
            item = PropertyValue()
            item.Name = name
            item.Value = value
            return item


        def connect(port: str):
            local_ctx = uno.getComponentContext()
            resolver = local_ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.bridge.UnoUrlResolver",
                local_ctx,
            )
            url = f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext"
            last_error = None
            for _ in range(80):
                try:
                    return resolver.resolve(url)
                except Exception as exc:
                    last_error = exc
                    time.sleep(0.1)
            raise RuntimeError(f"LibreOffice UNO non disponibile: {last_error}")


        def unprotect_if_possible(target) -> int:
            is_protected = getattr(target, "isProtected", None)
            unprotect = getattr(target, "unprotect", None)
            if not callable(is_protected) or not callable(unprotect):
                return 0
            if not is_protected():
                return 0
            unprotect("")
            return 0 if is_protected() else 1


        def main() -> int:
            port, input_path, output_path, filter_name = sys.argv[1:5]
            ctx = connect(port)
            desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            document = desktop.loadComponentFromURL(
                uno.systemPathToFileUrl(input_path),
                "_blank",
                0,
                (
                    prop("Hidden", True),
                    prop("ReadOnly", False),
                    prop("MacroExecutionMode", 0),
                    prop("UpdateDocMode", 0),
                ),
            )
            if document is None:
                raise RuntimeError("LibreOffice non ha aperto il file.")
            removed = 0
            try:
                removed += unprotect_if_possible(document)
                sheets = document.getSheets()
                for name in sheets.getElementNames():
                    removed += unprotect_if_possible(sheets.getByName(name))
                document.storeAsURL(
                    uno.systemPathToFileUrl(output_path),
                    (
                        prop("FilterName", filter_name),
                        prop("Overwrite", True),
                    ),
                )
            finally:
                document.close(True)
            print(f"removed={removed}")
            return 0


        if __name__ == "__main__":
            raise SystemExit(main())
        '''
    ).lstrip()


def _parse_uno_removed_count(output: str) -> int:
    match = re.search(r"removed=(\d+)", output)
    if match is None:
        return 0
    return int(match.group(1))
