#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def read_pyproject_version(path: Path) -> str:
    payload = tomllib.loads(path.read_text(encoding="utf-8"))
    return str(payload["project"]["version"])


def read_init_version(path: Path) -> str:
    match = re.search(r'^__version__\s*=\s*"([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError("__version__ non trovato in src/docmolder/__init__.py")
    return match.group(1)


def latest_docmolder_tag() -> str | None:
    result = subprocess.run(
        ["git", "tag", "--list", "docmolder-v*", "--sort=-v:refname"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    return next((line.strip() for line in result.stdout.splitlines() if line.strip()), None)


def collect_errors() -> list[str]:
    errors: list[str] = []
    manifest = read_json(ROOT / ".release-please-manifest.json")
    config = read_json(ROOT / "release-please-config.json")
    if not isinstance(manifest, dict) or "." not in manifest:
        errors.append(".release-please-manifest.json non contiene la chiave '.'.")
        manifest_version = ""
    else:
        manifest_version = str(manifest["."])

    pyproject_version = read_pyproject_version(ROOT / "pyproject.toml")
    init_version = read_init_version(ROOT / "src" / "docmolder" / "__init__.py")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    versions = {
        "manifest": manifest_version,
        "pyproject": pyproject_version,
        "__init__": init_version,
    }
    if len(set(versions.values())) != 1:
        errors.append(f"Versioni non allineate: {versions}")

    if manifest_version and f"## [{manifest_version}]" not in changelog:
        errors.append(f"CHANGELOG.md non contiene una sezione per {manifest_version}.")

    package_config = config.get("packages", {}).get(".") if isinstance(config, dict) else None
    if not isinstance(package_config, dict):
        errors.append("release-please-config.json non contiene packages['.'].")
    else:
        if package_config.get("release-type") != "python":
            errors.append("release-please-config.json deve usare release-type python.")
        if "src/docmolder/__init__.py" not in package_config.get("extra-files", []):
            errors.append("release-please-config.json deve aggiornare src/docmolder/__init__.py.")
        if package_config.get("changelog-path") != "CHANGELOG.md":
            errors.append("release-please-config.json deve puntare a CHANGELOG.md.")

    latest_tag = latest_docmolder_tag()
    expected_tag = f"docmolder-v{manifest_version}" if manifest_version else ""
    if latest_tag and expected_tag and latest_tag != expected_tag:
        errors.append(f"Ultimo tag locale {latest_tag}, atteso {expected_tag}.")

    print("## Release sanity")
    print(f"- Versione manifest: {manifest_version or 'n/d'}")
    print(f"- Versione pyproject: {pyproject_version}")
    print(f"- Versione __init__: {init_version}")
    print(f"- Ultimo tag locale: {latest_tag or 'n/d'}")
    print(f"- Tag atteso: {expected_tag or 'n/d'}")
    return errors


def main() -> int:
    try:
        errors = collect_errors()
    except Exception as exc:
        print(f"release sanity failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        print("\n## Errori")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nRelease metadata OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
