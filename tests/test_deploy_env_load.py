from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DeployEnvLoadTest(unittest.TestCase):
    def test_env_loader_trims_unquoted_values_and_expands_safe_venv_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "docmolder.env"
            env_file.write_text(
                "\n".join(
                    [
                        "DOCMOLDER_SMOKE_CHECK_ATTEMPTS=12 # retry count",
                        "DOCMOLDER_SMOKE_CHECK_SLEEP_SECONDS=5" + "   ",
                        "DOCMOLDER_VENV_DIR=${VENV_DIR}/custom",
                        "DOCMOLDER_HEALTHCHECK_BIN=${VENV_DIR}/bin/docmolder-healthcheck",
                        "DOCMOLDER_LITERAL='${VENV_DIR}/literal'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        "source deploy/env-load.sh; "
                        "VENV_DIR=/opt/docmolder/venv; "
                        f"load_docmolder_env_file {env_file}; "
                        "printf '%s\\n%s\\n%s\\n%s\\n%s\\n' "
                        "\"${DOCMOLDER_SMOKE_CHECK_ATTEMPTS}\" "
                        "\"${DOCMOLDER_SMOKE_CHECK_SLEEP_SECONDS}\" "
                        "\"${DOCMOLDER_VENV_DIR}\" "
                        "\"${DOCMOLDER_HEALTHCHECK_BIN}\" "
                        "\"${DOCMOLDER_LITERAL}\""
                    ),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            result.stdout.splitlines(),
            [
                "12",
                "5",
                "/opt/docmolder/venv/custom",
                "/opt/docmolder/venv/custom/bin/docmolder-healthcheck",
                "${VENV_DIR}/literal",
            ],
        )

    def test_empty_docmolder_venv_dir_does_not_clear_existing_venv_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / "docmolder.env"
            env_file.write_text(
                "\n".join(
                    [
                        "DOCMOLDER_VENV_DIR=",
                        "DOCMOLDER_HEALTHCHECK_BIN=${VENV_DIR}/bin/docmolder-healthcheck",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    (
                        "source deploy/env-load.sh; "
                        "VENV_DIR=/opt/docmolder/venv; "
                        f"load_docmolder_env_file {env_file}; "
                        "printf '%s\\n%s\\n%s\\n' "
                        "\"${DOCMOLDER_VENV_DIR-unset}\" "
                        "\"${VENV_DIR}\" "
                        "\"${DOCMOLDER_HEALTHCHECK_BIN}\""
                    ),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

        self.assertEqual(
            result.stdout.splitlines(),
            [
                "",
                "/opt/docmolder/venv",
                "/opt/docmolder/venv/bin/docmolder-healthcheck",
            ],
        )


if __name__ == "__main__":
    unittest.main()
