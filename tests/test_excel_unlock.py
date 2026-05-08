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

from docmolder.excel_unlock import ExcelUnlockError, ExcelUnlocker
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

    def test_xlsb_requires_configured_aspose_license(self) -> None:
        source = self.runtime_dir / "protetto.xlsb"
        source.write_bytes(b"xlsb-placeholder")

        with self.assertRaisesRegex(ExcelUnlockError, "Aspose.Cells con licenza"):
            self.unlocker.unlock_editing(source, "protetto_unlocked")

    def test_xlsb_requires_aspose_package_when_license_is_configured(self) -> None:
        source = self.runtime_dir / "protetto.xlsb"
        source.write_bytes(b"xlsb-placeholder")
        license_path = self.runtime_dir / "Aspose.Cells.lic"
        license_path.write_text("fake-license", encoding="utf-8")
        unlocker = ExcelUnlocker(self.runtime_dir, aspose_cells_license_path=license_path)

        with patch("docmolder.excel_unlock.util.find_spec", return_value=None):
            with self.assertRaisesRegex(ExcelUnlockError, "aspose-cells-python"):
                unlocker.unlock_editing(source, "protetto_unlocked")

    def test_xlsb_uses_aspose_when_license_is_configured(self) -> None:
        source = self.runtime_dir / "protetto.xlsb"
        source.write_bytes(b"xlsb-placeholder")
        license_path = self.runtime_dir / "Aspose.Cells.lic"
        license_path.write_text("fake-license", encoding="utf-8")
        unlocker = ExcelUnlocker(self.runtime_dir, aspose_cells_license_path=license_path)

        class FakeLicense:
            def set_license(self, path: str) -> None:
                self.path = path

        class FakeSettings:
            is_protected = True

        class FakeSheet:
            is_protected = True

            def unprotect(self) -> None:
                self.is_protected = False

        class FakeWorkbook:
            def __init__(self, path: str) -> None:
                self.path = path
                self.settings = FakeSettings()
                self.worksheets = [FakeSheet()]

            def unprotect(self, password: str) -> None:
                self.settings.is_protected = False

            def save(self, output_path: str, save_format: object) -> None:
                Path(output_path).write_bytes(b"unlocked-xlsb")

        fake_cells = SimpleNamespace(
            License=FakeLicense,
            Workbook=FakeWorkbook,
            SaveFormat=SimpleNamespace(XLSB="xlsb"),
        )
        with patch("docmolder.excel_unlock._load_aspose_cells_module", return_value=fake_cells):
            result = unlocker.unlock_editing(source, "protetto_unlocked")

        self.assertEqual(result.path.suffix, ".xlsb")
        self.assertEqual(result.mode, "aspose")
        self.assertEqual(result.removed_protection_count, 2)
        self.assertEqual(result.path.read_bytes(), b"unlocked-xlsb")


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
