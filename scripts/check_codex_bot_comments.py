#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass


BOT_LOGINS = {
    "chatgpt-codex-connector",
    "chatgpt-codex-connector[bot]",
}


@dataclass(frozen=True)
class BotComment:
    author: str
    body: str
    path: str
    url: str
    resolved: bool
    source: str


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=check, capture_output=True, text=True)


def gh_json(args: list[str]) -> object:
    result = run(["gh", *args], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh command failed")
    return json.loads(result.stdout or "{}")


def repo_owner_name() -> tuple[str, str]:
    result = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "gh repo view failed")
    output = result.stdout.strip()
    if "/" not in output:
        raise RuntimeError("gh repo view returned an invalid repository name")
    owner, name = output.split("/", 1)
    return owner, name


def current_pr_number() -> int | None:
    result = run(["gh", "pr", "view", "--json", "number", "--jq", ".number"], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return int(result.stdout.strip())


def pr_head_oid(number: int) -> str:
    result = run(["gh", "pr", "view", str(number), "--json", "headRefOid", "--jq", ".headRefOid"])
    return result.stdout.strip()


def load_rest_review_comments(owner: str, repo: str, number: int) -> list[dict[str, object]]:
    result = run(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{number}/comments",
            "--paginate",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "gh api pull comments failed")
    return json.loads(result.stdout or "[]")


def load_pr_threads(owner: str, repo: str, number: int) -> dict[str, object]:
    query = """
    query($owner: String!, $repo: String!, $number: Int!) {
      repository(owner: $owner, name: $repo) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes {
              isResolved
              isOutdated
              path
              line
              comments(first: 50) {
                nodes {
                  author { login }
                  body
                  url
                }
              }
            }
          }
          comments(first: 100) {
            nodes {
              author { login }
              body
              url
            }
          }
        }
      }
    }
    """
    return gh_json(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"repo={repo}",
            "-F",
            f"number={number}",
        ]
    )


def body_summary(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:160]
    return "(commento senza testo)"


def find_bot_comments(
    payload: dict[str, object],
    rest_comments: list[dict[str, object]],
    *,
    head_oid: str,
    include_resolved: bool,
    include_outdated: bool,
) -> list[BotComment]:
    pull = payload["data"]["repository"]["pullRequest"]  # type: ignore[index]
    found: list[BotComment] = []
    seen_urls: set[str] = set()

    for thread in pull["reviewThreads"]["nodes"]:  # type: ignore[index]
        resolved = bool(thread["isResolved"])
        path = str(thread.get("path") or "(thread)")
        for comment in thread["comments"]["nodes"]:
            author = ((comment.get("author") or {}).get("login") or "")
            if author in BOT_LOGINS:
                seen_urls.add(str(comment.get("url") or ""))
                if resolved and not include_resolved:
                    continue
                if bool(thread.get("isOutdated")) and not include_outdated:
                    continue
                found.append(
                    BotComment(
                        author=author,
                        body=str(comment.get("body") or ""),
                        path=path,
                        url=str(comment.get("url") or ""),
                        resolved=resolved,
                        source="graphql-thread",
                    )
                )

    for comment in pull["comments"]["nodes"]:  # type: ignore[index]
        author = ((comment.get("author") or {}).get("login") or "")
        if author in BOT_LOGINS:
            found.append(
                BotComment(
                    author=author,
                    body=str(comment.get("body") or ""),
                    path="(PR comment)",
                    url=str(comment.get("url") or ""),
                    resolved=False,
                    source="graphql-pr-comment",
                )
            )
            seen_urls.add(str(comment.get("url") or ""))

    for comment in rest_comments:
        author = ((comment.get("user") or {}).get("login") or "")
        url = str(comment.get("html_url") or "")
        if author not in BOT_LOGINS or url in seen_urls:
            continue
        if not include_outdated and comment.get("commit_id") != head_oid:
            continue
        found.append(
            BotComment(
                author=author,
                body=str(comment.get("body") or ""),
                path=str(comment.get("path") or "(review comment)"),
                url=url,
                resolved=False,
                source="rest-current-head-review-comment",
            )
        )

    return found


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Controlla commenti aperti del Codex connector bot su una PR."
    )
    parser.add_argument("--pr", type=int, help="Numero PR. Default: PR della branch corrente.")
    parser.add_argument("--include-resolved", action="store_true", help="Mostra anche thread già risolti.")
    parser.add_argument("--include-outdated", action="store_true", help="Mostra anche commenti REST su commit non più head.")
    parser.add_argument("--fail", action="store_true", help="Esce con codice 1 se trova commenti aperti.")
    args = parser.parse_args()

    if shutil.which("gh") is None:
        print("GitHub CLI non disponibile: salto controllo commenti Codex connector bot.", file=sys.stderr)
        return 0

    number = args.pr or current_pr_number()
    if number is None:
        print("Nessuna PR corrente: salto controllo commenti Codex connector bot.")
        return 0

    try:
        owner, repo = repo_owner_name()
        head_oid = pr_head_oid(number)
        comments = find_bot_comments(
            load_pr_threads(owner, repo, number),
            load_rest_review_comments(owner, repo, number),
            head_oid=head_oid,
            include_resolved=args.include_resolved,
            include_outdated=args.include_outdated,
        )
    except RuntimeError as exc:
        print(f"Impossibile leggere i commenti Codex connector bot: {exc}", file=sys.stderr)
        return 2 if args.fail else 0

    if not comments:
        print(f"Nessun commento aperto del Codex connector bot sulla PR #{number}.")
        return 0

    print(f"Commenti Codex connector bot da gestire sulla PR #{number}:")
    for comment in comments:
        status = "resolved" if comment.resolved else "open"
        print(f"- [{status}] {comment.path} ({comment.source}): {body_summary(comment.body)}")
        if comment.url:
            print(f"  {comment.url}")
    return 1 if args.fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
