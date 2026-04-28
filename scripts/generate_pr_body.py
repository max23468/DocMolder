#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(args: list[str]) -> str:
    return subprocess.run(args, check=True, capture_output=True, text=True).stdout.strip()


def load_report(base: str) -> dict[str, object]:
    output = run(["python3", "scripts/classify_changes.py", "--base", base, "--format", "json"])
    return json.loads(output)


def checkbox(value: bool, label: str) -> str:
    return f"- [{'x' if value else ' '}] {label}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera un body PR DocMolder dal diff corrente.")
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--context", default="Aggiornamento preparato da Codex.")
    args = parser.parse_args()

    report = load_report(args.base)
    changed = "\n".join(f"- `{path}`" for path in report["changed_files"]) or "- Nessun file modificato"
    deploy = bool(report["recommended_deploy"])
    release_owned = bool(report["release_owned"])
    release_type = str(report["recommended_release_type"])

    body = f"""## Contesto
{args.context}

## Soluzione adottata
Modifica focalizzata sui file elencati sotto.

## Impatto operativo
{checkbox(not deploy, "Deploy VPS non necessario")}
{checkbox(deploy, "Deploy VPS automatico atteso al merge su main")}
{checkbox(False, "Deploy VPS manuale richiesto")}

## Release impact
- Tipo consigliato: `{release_type}`
- File release-owned toccati: `{"sì" if release_owned else "no"}`

## File modificati
{changed}

## Checklist
- [ ] Ho mantenuto la modifica focalizzata e minima
- [ ] Ho aggiornato la documentazione necessaria
- [ ] Ho eseguito i test/check rilevanti
- [ ] Non ho introdotto segreti o dati sensibili
- [ ] Non ho fatto bump manuali di versione o changelog fuori dalla Release PR

## Evidenze test
Da compilare prima del merge.
"""
    if args.output:
        args.output.write_text(body, encoding="utf-8")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
