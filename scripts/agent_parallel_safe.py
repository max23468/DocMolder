#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


COORDINATION_PATH = Path("docs/AGENT_COORDINATION.md")
INACTIVE_STATES = {"libero", "done", "chiuso", "closed", "merged", "-"}


@dataclass(frozen=True)
class WorkItem:
    state: str
    owner: str
    branch: str
    area: str
    notes: str


def run_git(args: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], check=check, capture_output=True, text=True)


def current_branch() -> str:
    return run_git(["branch", "--show-current"]).stdout.strip()


def porcelain_paths(output: str) -> list[str]:
    paths: list[str] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:]
        if " -> " in path:
            _old, path = path.split(" -> ", 1)
        paths.append(path.strip())
    return sorted(set(paths))


def changed_paths() -> list[str]:
    result = run_git(["status", "--porcelain"], check=True)
    return porcelain_paths(result.stdout)


def parse_coordination_table(text: str) -> list[WorkItem]:
    items: list[WorkItem] = []
    in_code_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence:
            continue
        if not line.startswith("|") or "---" in line:
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) < 5 or cells[0].lower() == "stato":
            continue
        items.append(WorkItem(state=cells[0], owner=cells[1], branch=cells[2], area=cells[3], notes=cells[4]))
    return items


def active_items(path: Path = COORDINATION_PATH) -> list[WorkItem]:
    if not path.exists():
        return []
    items = parse_coordination_table(path.read_text(encoding="utf-8"))
    return [item for item in items if item.state.strip().lower() not in INACTIVE_STATES]


def normalize_tokens(value: str) -> set[str]:
    tokens = set(re.findall(r"[a-zA-Z0-9_./-]+", value.lower()))
    return {token for token in tokens if token not in {"-", "e", "o", "su", "in", "di", "da", "per"}}


def item_matches_paths(item: WorkItem, paths: list[str]) -> bool:
    area_tokens = normalize_tokens(" ".join([item.area, item.notes]))
    if not area_tokens:
        return False
    for path in paths:
        path_lower = path.lower()
        path_tokens = normalize_tokens(path_lower)
        for token in area_tokens:
            if "/" in token or "." in token:
                if token in path_lower:
                    return True
            elif token in path_tokens:
                return True
    return False


def print_report(*, owner: str | None, fail_on_active: bool) -> int:
    branch = current_branch()
    paths = changed_paths()
    items = active_items()

    print(f"Parallel-safe preflight: {branch or '(detached)'}")
    if not branch:
        print("BLOCKER: HEAD detached. Crea o passa a una branch dedicata prima di lavorare.")

    if paths:
        print(f"Working tree: {len(paths)} file modificati/non tracciati.")
        for path in paths:
            print(f"- {path}")
    else:
        print("Working tree: pulito.")

    if not items:
        print("Registro agenti: nessun lavoro attivo registrato.")
    else:
        print("Registro agenti: lavori attivi.")
        for item in items:
            marker = "MATCH" if item_matches_paths(item, paths) else "INFO"
            owned_by_current = owner and item.owner.lower() == owner.lower()
            if owned_by_current:
                marker = "OWN"
            print(f"{marker}: {item.state} | {item.owner} | {item.branch} | {item.area} | {item.notes}")

    blockers = not branch
    conflicts = [item for item in items if not (owner and item.owner.lower() == owner.lower()) and item_matches_paths(item, paths)]
    if conflicts:
        blockers = True
        print("BLOCKER: i cambi locali sembrano sovrapporsi ad aree gia presidiate nel registro.")
    elif items and fail_on_active:
        blockers = True
        print("BLOCKER: esistono lavori attivi nel registro e --fail-on-active e abilitato.")

    return 1 if blockers else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlla rischi di overlap tra worktree e registro agenti.")
    parser.add_argument("--owner", default=None, help="Owner/chat corrente, per ignorare le proprie righe attive.")
    parser.add_argument(
        "--fail-on-active",
        action="store_true",
        help="Esci con codice 1 se esiste qualunque lavoro attivo registrato.",
    )
    args = parser.parse_args()
    return print_report(owner=args.owner, fail_on_active=args.fail_on_active)


if __name__ == "__main__":
    raise SystemExit(main())
