from __future__ import annotations

from docmolder.bot import build_application
from docmolder.config import load_settings


def main() -> None:
    settings = load_settings()
    application = build_application(settings)
    application.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
