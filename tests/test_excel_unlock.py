from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.excel_unlock import (
    ExcelUnlockError,
    ExcelUnlocker,
    _libreoffice_filter_for_suffix,
    _libreoffice_python_env,
    _parse_uno_removed_count,
)
from docmolder.processing import DocumentProcessor, ProcessingUserError
from docmolder.models import SupportedAction


class ExcelUnlockerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name)
        self.unlocker = ExcelUnlocker(self.runtime_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_unlock_ooxml_excel_removes_editing_protections(self) -> None:
        source = self.runtime_dir / "protetto.xlsx"
        _write_minimal_xlsx(source, protected=True)

        result = self.unlocker.unlock_editing(source, "protetto_unlocked")

        self.assertEqual(result.name, "protetto_unlocked.xlsx")
        self.assertEqual(result.mode, "ooxml")
        self.assertGreaterEqual(result.removed_protection_count, 3)
        with zipfile.ZipFile(result.path) as unlocked:
            workbook = unlocked.read("xl/workbook.xml")
            sheet = unlocked.read("xl/worksheets/sheet1.xml")
        self.assertNotIn(b"workbookProtection", workbook)
        self.assertNotIn(b"fileSharing", workbook)
        self.assertNotIn(b"sheetProtection", sheet)
        self.assertNotIn(b"protectedRanges", sheet)
        self.assertIn(b"test", sheet)

    def test_unlock_ooxml_excel_requires_existing_protection(self) -> None:
        source = self.runtime_dir / "libero.xlsx"
        _write_minimal_xlsx(source, protected=False)

        with self.assertRaisesRegex(ExcelUnlockError, "Non ho trovato protezioni"):
            self.unlocker.unlock_editing(source, "libero_unlocked")

    def test_binary_excel_uses_libreoffice_for_xls_and_keeps_suffix(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")

        def fake_run(args, **kwargs):
            output_path = Path(args[4])
            output_path.write_bytes(b"unlocked-binary-excel")
            return subprocess.CompletedProcess(args, 0, stdout="removed=2\n", stderr="")

        fake_office = SimpleNamespace(terminate=lambda: None, wait=lambda timeout=0: None, kill=lambda: None)
        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=fake_office),
            patch("docmolder.excel_unlock.subprocess.run", side_effect=fake_run),
        ):
            result = self.unlocker.unlock_editing(source, "protetto_unlocked")

        self.assertEqual(result.path.suffix, ".xls")
        self.assertEqual(result.mode, "libreoffice")
        self.assertEqual(result.removed_protection_count, 2)
        self.assertEqual(result.path.read_bytes(), b"unlocked-binary-excel")

    def test_unlock_ooxml_excel_rejects_bad_zip_files(self) -> None:
        source = self.runtime_dir / "corrotto.xlsx"
        source.write_bytes(b"not-a-zip")

        with self.assertRaisesRegex(ExcelUnlockError, "cifrato, corrotto o non leggibile"):
            self.unlocker.unlock_editing(source, "corrotto_unlocked")

    def test_unlock_ooxml_excel_surfaces_os_errors(self) -> None:
        source = self.runtime_dir / "protetto.xlsx"
        _write_minimal_xlsx(source, protected=True)

        with patch("docmolder.excel_unlock.zipfile.ZipFile", side_effect=OSError("disk full")):
            with self.assertRaisesRegex(ExcelUnlockError, "Non riesco a leggere questo Excel"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_requires_libreoffice_binary(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")

        with patch("docmolder.excel_unlock._find_libreoffice_binary", return_value=None):
            with self.assertRaisesRegex(ExcelUnlockError, "serve LibreOffice sul server"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_surfaces_libreoffice_launch_error(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")

        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock.subprocess.Popen", side_effect=OSError("launch failed")),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "Non riesco ad avviare LibreOffice"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_timeout_kills_stuck_libreoffice_process(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")
        calls: list[str] = []

        class FakeOffice:
            def terminate(self) -> None:
                calls.append("terminate")

            def wait(self, timeout: int = 0) -> None:
                if calls == ["terminate"]:
                    calls.append("wait-timeout")
                    raise subprocess.TimeoutExpired(cmd="soffice", timeout=timeout)
                calls.append("wait-ok")

            def kill(self) -> None:
                calls.append("kill")

        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=FakeOffice()),
            patch(
                "docmolder.excel_unlock.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="python3", timeout=5),
            ),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "ha impiegato troppo tempo"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

        self.assertEqual(calls, ["terminate", "wait-timeout", "kill", "wait-ok"])

    def test_binary_excel_surfaces_uno_bridge_launch_error(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")
        fake_office = SimpleNamespace(terminate=lambda: None, wait=lambda timeout=0: None, kill=lambda: None)

        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=fake_office),
            patch("docmolder.excel_unlock.subprocess.run", side_effect=OSError("uno missing")),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "bridge Python di LibreOffice"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_rejects_failed_uno_execution(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")
        fake_office = SimpleNamespace(terminate=lambda: None, wait=lambda timeout=0: None, kill=lambda: None)

        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=fake_office),
            patch(
                "docmolder.excel_unlock.subprocess.run",
                return_value=subprocess.CompletedProcess(["python3"], 1, stdout="", stderr="password required"),
            ),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "non è riuscito a rimuovere la protezione"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_requires_non_empty_output_file(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")

        def fake_run(args, **kwargs):
            output_path = Path(args[4])
            output_path.write_bytes(b"")
            return subprocess.CompletedProcess(args, 0, stdout="removed=2\n", stderr="")

        fake_office = SimpleNamespace(terminate=lambda: None, wait=lambda timeout=0: None, kill=lambda: None)
        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=fake_office),
            patch("docmolder.excel_unlock.subprocess.run", side_effect=fake_run),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "non ha creato una copia Excel valida"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_binary_excel_requires_detected_removed_protections(self) -> None:
        source = self.runtime_dir / "protetto.xls"
        source.write_bytes(b"binary-excel-placeholder")

        def fake_run(args, **kwargs):
            output_path = Path(args[4])
            output_path.write_bytes(b"unlocked-binary-excel")
            return subprocess.CompletedProcess(args, 0, stdout="removed=0\n", stderr="")

        fake_office = SimpleNamespace(terminate=lambda: None, wait=lambda timeout=0: None, kill=lambda: None)
        with (
            patch("docmolder.excel_unlock._find_libreoffice_binary", return_value="/usr/bin/soffice"),
            patch("docmolder.excel_unlock._find_uno_python", return_value="/usr/bin/python3"),
            patch("docmolder.excel_unlock.subprocess.Popen", return_value=fake_office),
            patch("docmolder.excel_unlock.subprocess.run", side_effect=fake_run),
        ):
            with self.assertRaisesRegex(ExcelUnlockError, "Non ho trovato fogli protetti"):
                self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_xlsb_is_not_supported(self) -> None:
        source = self.runtime_dir / "protetto.xlsb"
        source.write_bytes(b"xlsb-placeholder")

        with self.assertRaisesRegex(ExcelUnlockError, r"\.xlsx, \.xlsm e \.xls"):
            self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_libo_helpers_cover_filter_env_and_removed_count_parsing(self) -> None:
        original_env = {"PYTHONPATH": "already-there"}
        with patch.dict("docmolder.excel_unlock.os.environ", original_env, clear=True), patch.object(
            Path,
            "exists",
            autospec=True,
            side_effect=lambda path: str(path) in {"/usr/lib/libreoffice/program", "/usr/lib/python3/dist-packages"},
        ):
            env = _libreoffice_python_env()

        self.assertEqual(_libreoffice_filter_for_suffix(".xls"), "MS Excel 97")
        self.assertIn("/usr/lib/libreoffice/program", env["PYTHONPATH"])
        self.assertIn("/usr/lib/python3/dist-packages", env["PYTHONPATH"])
        self.assertTrue(env["PYTHONPATH"].endswith("already-there"))
        self.assertEqual(_parse_uno_removed_count("removed=7"), 7)
        self.assertEqual(_parse_uno_removed_count("no marker"), 0)
        with self.assertRaisesRegex(ExcelUnlockError, "Formato Excel binario non supportato"):
            _libreoffice_filter_for_suffix(".ods")


class ExcelProcessingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.runtime_dir = Path(self.temp_dir.name)
        self.processor = DocumentProcessor(self.runtime_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_processor_unlocks_ooxml_excel_action(self) -> None:
        source = self.runtime_dir / "input" / "protetto.xlsm"
        source.parent.mkdir()
        _write_minimal_xlsx(source, protected=True)

        result = self.processor.process(SupportedAction.EXCEL_UNLOCK_EDITING, [source], "protetto_unlocked")

        self.assertEqual(result.output_name, "protetto_unlocked.xlsm")
        self.assertEqual(result.processing_mode, "excel-ooxml")
        self.assertIn("Excel pronto", result.message)

    def test_processor_surfaces_excel_unlock_errors_as_user_errors(self) -> None:
        source = self.runtime_dir / "libero.xlsx"
        _write_minimal_xlsx(source, protected=False)

        with self.assertRaises(ProcessingUserError):
            self.processor.process(SupportedAction.EXCEL_UNLOCK_EDITING, [source], "libero_unlocked")


def _write_minimal_xlsx(path: Path, *, protected: bool) -> None:
    workbook_protection = '<fileSharing readOnlyRecommended="1" reservationPassword="ABCD"/><workbookProtection workbookPassword="ABCD" lockStructure="1"/>'
    sheet_protection = '<sheetProtection password="ABCD" sheet="1" objects="1" scenarios="1"/><protectedRanges><protectedRange name="Area" sqref="A1" password="ABCD"/></protectedRanges>'
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"{workbook_protection if protected else ''}"
            '<sheets><sheet name="Foglio1" sheetId="1" r:id="rId1"/></sheets>'
            "</workbook>",
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetPr/><dimension ref="A1"/><sheetViews><sheetView workbookViewId="0"/></sheetViews>'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>test</t></is></c></row></sheetData>'
            f"{sheet_protection if protected else ''}"
            "</worksheet>",
        )


if __name__ == "__main__":
    unittest.main()
