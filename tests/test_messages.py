from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.keyboards import build_admin_dashboard_keyboard
from docmolder.models import JobStatus
from docmolder.messages import HELP_MESSAGE


class MessageGoldenTest(unittest.TestCase):
    def test_help_message_lists_reduced_command_surface(self) -> None:
        self.assertIn("/start", HELP_MESSAGE)
        self.assertIn("/help", HELP_MESSAGE)
        self.assertIn("/history", HELP_MESSAGE)
        self.assertIn("/status", HELP_MESSAGE)
        self.assertIn("/reset", HELP_MESSAGE)
        self.assertNotIn("/request_access", HELP_MESSAGE)
        self.assertNotIn("/policy", HELP_MESSAGE)
        self.assertNotIn("/last", HELP_MESSAGE)
        self.assertNotIn("/access", HELP_MESSAGE)
        self.assertNotIn("/admin", HELP_MESSAGE)

    def test_admin_keyboard_keeps_maintenance_shortcut(self) -> None:
        keyboard = build_admin_dashboard_keyboard(service_paused=False)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Manutenzione", labels)
        self.assertIn("admin:maintenance", callbacks)

    def test_admin_keyboard_hides_unavailable_job_status_shortcuts(self) -> None:
        keyboard = build_admin_dashboard_keyboard(
            service_paused=False,
            available_job_statuses={JobStatus.FAILED},
        )

        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Ultimo fallito", labels)
        self.assertIn("Ultimo job", labels)
        self.assertNotIn("In esecuzione", labels)
        self.assertNotIn("Ultimo queued", labels)
        self.assertNotIn("Ultimo riuscito", labels)

    def test_admin_keyboard_hides_job_shortcuts_when_no_jobs_exist(self) -> None:
        keyboard = build_admin_dashboard_keyboard(
            service_paused=False,
            available_job_statuses=set(),
        )

        labels = [button.text for row in keyboard.inline_keyboard for button in row]

        self.assertNotIn("Ultimo job", labels)
        self.assertNotIn("Ultimo fallito", labels)
