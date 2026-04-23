from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docmolder.keyboards import build_admin_dashboard_keyboard
from docmolder.messages import HELP_MESSAGE


class MessageGoldenTest(unittest.TestCase):
    def test_help_message_lists_access_and_policy_commands(self) -> None:
        self.assertIn("/request_access", HELP_MESSAGE)
        self.assertIn("/policy", HELP_MESSAGE)
        self.assertIn("/history", HELP_MESSAGE)
        self.assertIn("/last", HELP_MESSAGE)

    def test_admin_keyboard_keeps_maintenance_shortcut(self) -> None:
        keyboard = build_admin_dashboard_keyboard(service_paused=False)
        labels = [button.text for row in keyboard.inline_keyboard for button in row]
        callbacks = [button.callback_data for row in keyboard.inline_keyboard for button in row]

        self.assertIn("Manutenzione", labels)
        self.assertIn("admin:maintenance", callbacks)
