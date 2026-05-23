#!/usr/bin/env node

import { readFile } from "node:fs/promises";
import process from "node:process";

const repository = process.env.GITHUB_REPOSITORY;
const token = process.env.GITHUB_TOKEN;
const codexLoginPattern = new RegExp(process.env.CODEX_BOT_LOGIN_PATTERN ?? "codex", "i");
const inboxIssueTitle = process.env.CODEX_INBOX_ISSUE_TITLE ?? "Codex feedback inbox";
const repositoryName = repository?.split("/")[1] ?? "repository";
const inboxMarker =
  process.env.CODEX_INBOX_MARKER ??
  `<!-- ${normalizeInboxMarkerName(repositoryName)}-codex-feedback-inbox -->`;
const dryRun = process.env.DRY_RUN === "true";
const eventName = process.env.GITHUB_EVENT_NAME ?? "";
const eventPayload = await readGitHubEventPayload();
const fullScan = shouldRunFullScan();
const eventPullRequestNumber = getEventPullRequestNumber(eventPayload);
const recentPrLimit = parsePositiveInteger(process.env.CODEX_RECENT_PR_LIMIT, 50);
const recentPrDays = parsePositiveInteger(process.env.CODEX_RECENT_PR_DAYS, 30);
const historyPrLimit = parsePositiveInteger(process.env.CODEX_HISTORY_PR_LIMIT, 8);
const historyThreadLimit = parsePositiveInteger(process.env.CODEX_HISTORY_THREAD_LIMIT, 5);
const githubApiAttempts = parsePositiveInteger(process.env.CODEX_GITHUB_API_ATTEMPTS, 4);
const githubApiRetryBaseMs = parsePositiveInteger(process.env.CODEX_GITHUB_API_RETRY_BASE_MS, 1500);

if (!repository) {
  fail("GITHUB_REPOSITORY non impostato.");
}

if (!token) {
  fail("GITHUB_TOKEN non impostato.");
}

const [owner, repo] = repository.split("/");

if (!owner || !repo) {
  fail(`GITHUB_REPOSITORY non valido: ${repository}`);
}

const prs = await listPullRequests();
const inboxEntries = [];

for (const pr of prs) {
  const threads = await listReviewThreads(pr.number);
  const codexThreads = threads.filter(isCodexThread);

  if (codexThreads.length === 0) continue;

  const actionableThreads = codexThreads.filter(isActionableThread);
  const historicalThreads = codexThreads.filter((thread) => !isActionableThread(thread));

  inboxEntries.push({
    actionableThreads,
    historicalThreads,
    number: pr.number,
    state: pr.state,
    title: pr.title,
    url: pr.html_url,
    wasMerged: Boolean(pr.merged_at),
  });
}

const inboxIssue = await upsertInboxIssue(inboxEntries);

console.log(
  JSON.stringify(
    {
      automaticPrComments: false,
      closedDuplicateInboxIssues: inboxIssue.closedDuplicateNumbers,
      dryRun,
      eventName,
      fullScan,
      inboxIssue: inboxIssue.issue?.html_url ?? null,
      prsScanned: prs.length,
      prsWithCodexThreads: inboxEntries.length,
      totalActionableThreads: inboxEntries.reduce(
        (total, entry) => total + entry.actionableThreads.length,
        0,
      ),
      totalHistoricalThreads: inboxEntries.reduce(
        (total, entry) => total + entry.historicalThreads.length,
        0,
      ),
    },
    null,
    2,
  ),
);

async function listPullRequests() {
  if (fullScan) return listAllPullRequests();

  const prsByNumber = new Map();

  for (const pr of await listOpenPullRequests()) {
    prsByNumber.set(pr.number, pr);
  }

  for (const pr of await listRecentPullRequests()) {
    prsByNumber.set(pr.number, pr);
  }

  for (const prNumber of await listInboxPullRequestNumbers()) {
    if (prsByNumber.has(prNumber)) continue;

    const inboxPr = await getPullRequestFromInbox(prNumber);
    if (!inboxPr) continue;

    prsByNumber.set(inboxPr.number, inboxPr);
  }

  if (eventPullRequestNumber && !prsByNumber.has(eventPullRequestNumber)) {
    const eventPr = await githubJson(`/repos/${owner}/${repo}/pulls/${eventPullRequestNumber}`);
    prsByNumber.set(eventPr.number, eventPr);
  }

  return [...prsByNumber.values()].sort(
    (left, right) => new Date(right.updated_at) - new Date(left.updated_at),
  );
}

async function listAllPullRequests() {
  return listPullRequestPages({ state: "all" });
}

async function getPullRequestFromInbox(prNumber) {
  try {
    return await githubJson(`/repos/${owner}/${repo}/pulls/${prNumber}`);
  } catch (error) {
    if (error.status === 404) {
      console.warn(`PR #${prNumber} presente nella inbox ma non trovata: la salto.`);
      return null;
    }

    throw error;
  }
}

async function listInboxPullRequestNumbers() {
  const existingIssue = chooseCanonicalInboxIssue(await findInboxIssues());

  return existingIssue ? extractInboxPullRequestNumbers(existingIssue.body ?? "") : [];
}

function extractInboxPullRequestNumbers(body) {
  return [
    ...new Set(
      [...body.matchAll(/^### PR #(\d+) - /gm)]
        .map((match) => Number.parseInt(match[1], 10))
        .filter(Number.isInteger),
    ),
  ];
}

async function listOpenPullRequests() {
  return listPullRequestPages({ state: "open" });
}

async function listRecentPullRequests() {
  const cutoff = Date.now() - recentPrDays * 24 * 60 * 60 * 1000;

  return listPullRequestPages({
    limit: recentPrLimit,
    state: "all",
    stopAfterBatch: (batch) => {
      const oldestPr = batch.at(-1);
      return oldestPr ? new Date(oldestPr.updated_at).getTime() < cutoff : true;
    },
  });
}

async function listPullRequestPages({ limit = Infinity, state, stopAfterBatch } = {}) {
  const results = [];

  for (let page = 1; results.length < limit; page++) {
    const query = new URLSearchParams({
      direction: "desc",
      page: String(page),
      per_page: "100",
      sort: "updated",
      state,
    });
    const batch = await githubJson(`/repos/${owner}/${repo}/pulls?${query}`);

    if (batch.length === 0) break;

    results.push(...batch);

    if (stopAfterBatch?.(batch)) break;
  }

  return results.slice(0, limit);
}

async function listReviewThreads(prNumber) {
  const query = `query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
    repository(owner: $owner, name: $repo) {
      pullRequest(number: $number) {
        reviewThreads(first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            id
            isResolved
            isOutdated
            path
            line
            originalLine
            comments(first: 100) {
              pageInfo {
                hasNextPage
                endCursor
              }
              nodes {
                id
                author {
                  login
                }
                body
                createdAt
                url
              }
            }
          }
        }
      }
    }
  }`;

  const threads = [];
  let cursor = null;

  do {
    const data = await githubGraphql(query, {
      cursor,
      number: prNumber,
      owner,
      repo,
    });
    const page = data.repository.pullRequest.reviewThreads;

    threads.push(...page.nodes);
    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);

  for (const thread of threads) {
    if (!thread.comments.pageInfo.hasNextPage) continue;

    thread.comments.nodes.push(
      ...(await listReviewThreadComments(thread.id, thread.comments.pageInfo.endCursor)),
    );
  }

  return threads;
}

async function listReviewThreadComments(threadId, cursor) {
  const query = `query($threadId: ID!, $cursor: String) {
    node(id: $threadId) {
      ... on PullRequestReviewThread {
        comments(first: 100, after: $cursor) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            id
            author {
              login
            }
            body
            createdAt
            url
          }
        }
      }
    }
  }`;
  const comments = [];

  do {
    const data = await githubGraphql(query, {
      cursor,
      threadId,
    });
    const page = data.node.comments;

    comments.push(...page.nodes);
    cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
  } while (cursor);

  return comments;
}

function isCodexThread(thread) {
  return thread.comments.nodes.some((comment) =>
    codexLoginPattern.test(comment.author?.login ?? ""),
  );
}

function isActionableThread(thread) {
  return isCodexThread(thread) && !thread.isResolved && !thread.isOutdated;
}

async function upsertInboxIssue(entries) {
  const body = buildInboxBody(entries);
  const inboxIssues = await findInboxIssues();
  const existingIssue = chooseCanonicalInboxIssue(inboxIssues);
  const duplicateIssues = inboxIssues.filter(
    (issue) => issue.state === "open" && issue.number !== existingIssue?.number,
  );
  const closedDuplicateNumbers = await closeDuplicateInboxIssues(duplicateIssues, existingIssue);

  if (dryRun) {
    console.log(`DRY RUN: issue inbox non aggiornata.\n${body}`);
    return {
      closedDuplicateNumbers,
      issue: existingIssue,
    };
  }

  if (existingIssue) {
    return {
      closedDuplicateNumbers,
      issue: await githubJson(
        `/repos/${owner}/${repo}/issues/${existingIssue.number}`,
        {
          body,
          state: "open",
          title: inboxIssueTitle,
        },
        "PATCH",
      ),
    };
  }

  return {
    closedDuplicateNumbers,
    issue: await githubJson(`/repos/${owner}/${repo}/issues`, {
      body,
      title: inboxIssueTitle,
    }),
  };
}

async function findInboxIssues() {
  const query = new URLSearchParams({
    per_page: "100",
    q: `repo:${owner}/${repo} is:issue in:title "${inboxIssueTitle}"`,
  });
  const result = await githubJson(`/search/issues?${query}`);
  const exactTitleIssues = result.items.filter((issue) => issue.title === inboxIssueTitle);
  const issues = [];

  for (const issue of exactTitleIssues) {
    const issueDetails = await githubJson(`/repos/${owner}/${repo}/issues/${issue.number}`);

    if (isManagedInboxIssue(issueDetails)) {
      issues.push(issueDetails);
    }
  }

  return issues;
}

function isManagedInboxIssue(issue) {
  return issue.title === inboxIssueTitle && issue.body?.includes(inboxMarker);
}

function chooseCanonicalInboxIssue(issues) {
  return (
    issues
      .filter((issue) => issue.state === "open")
      .sort((left, right) => new Date(right.updated_at) - new Date(left.updated_at))[0] ?? null
  );
}

async function closeDuplicateInboxIssues(issues, canonicalIssue) {
  const closedDuplicateNumbers = [];

  for (const issue of issues) {
    const body = canonicalIssue
      ? `Chiudo come duplicato della inbox attiva #${canonicalIssue.number}.`
      : `Chiudo come duplicato: il workflow ricreerà la inbox canonica "${inboxIssueTitle}".`;

    if (dryRun) {
      console.log(`DRY RUN: chiuderei la issue inbox duplicata #${issue.number}.`);
      closedDuplicateNumbers.push(issue.number);
      continue;
    }

    await githubJson(`/repos/${owner}/${repo}/issues/${issue.number}/comments`, {
      body,
    });
    await githubJson(
      `/repos/${owner}/${repo}/issues/${issue.number}`,
      {
        state: "closed",
        state_reason: "not_planned",
      },
      "PATCH",
    );
    closedDuplicateNumbers.push(issue.number);
  }

  return closedDuplicateNumbers;
}

function buildInboxBody(entries) {
  const actionableEntries = entries
    .map((entry) => ({
      ...entry,
      threads: entry.actionableThreads,
    }))
    .filter((entry) => entry.threads.length > 0);
  const historicalEntries = entries
    .map((entry) => ({
      ...entry,
      threads: entry.historicalThreads,
    }))
    .filter((entry) => entry.threads.length > 0);
  const totalActionable = actionableEntries.reduce(
    (total, entry) => total + entry.threads.length,
    0,
  );
  const totalHistorical = historicalEntries.reduce(
    (total, entry) => total + entry.threads.length,
    0,
  );

  const lines = [
    inboxMarker,
    "# Codex feedback inbox",
    "",
    "Issue aggiornata automaticamente dal workflow `Codex PR comments`.",
    "Fonte di verità: review thread GitHub su tutte le PR, aperte, chiuse e mergiate.",
    "",
    "## Da risolvere ora",
    "",
  ];

  if (totalActionable === 0) {
    lines.push("Nessun thread Codex actionable al momento.", "");
  } else {
    lines.push(`Thread actionable: ${totalActionable}`, "");
    appendEntrySection(lines, actionableEntries, true);
  }

  lines.push("## Storico e audit", "");

  if (totalHistorical === 0) {
    lines.push("Nessun thread Codex storico da mostrare.", "");
  } else {
    const compactHistoricalEntries = compactHistoricalEntriesForInbox(historicalEntries);
    const displayedHistorical = compactHistoricalEntries.reduce(
      (total, entry) => total + entry.threads.length,
      0,
    );

    lines.push(
      `Thread storici totali: ${totalHistorical}. Mostro ${displayedHistorical} thread recenti in ${compactHistoricalEntries.length} PR.`,
      "",
    );
    appendEntrySection(lines, compactHistoricalEntries, false);
  }

  lines.push(
    "## Regola operativa",
    "",
    "Quando questa issue segnala thread actionable, Codex deve risolvere prima i commenti nuovi e poi controllare anche lo storico ancora rilevante. La inbox si aggiorna su eventi PR trusted, commenti issue, dispatch manuale e scansione programmata; se un thread viene solo marcato come risolto nella UI GitHub senza push o commenti, lascia un commento sulla inbox o avvia il workflow manuale per forzare il refresh. I thread pending non pubblicati da GitHub non sono leggibili via API finché la review non viene inviata.",
    "",
  );

  return `${lines.join("\n").trimEnd()}\n`;
}

function compactHistoricalEntriesForInbox(entries) {
  return entries.slice(0, historyPrLimit).map((entry) => ({
    ...entry,
    threads: entry.threads.slice(0, historyThreadLimit),
  }));
}

function appendEntrySection(lines, entries, actionable) {
  for (const entry of entries) {
    lines.push(`### PR #${entry.number} - ${entry.title}`);
    lines.push(`- URL: ${entry.url}`);
    lines.push(`- Stato: ${renderPrState(entry)}`);
    lines.push(`- Thread: ${entry.threads.length}`);
    lines.push("");

    for (const thread of entry.threads) {
      const checkbox = actionable ? "[ ]" : "[x]";
      lines.push(`- ${checkbox} ${renderThread(thread)}`);
    }

    lines.push("");
  }
}

function renderPrState(entry) {
  if (entry.state === "open") return "aperta";
  return entry.wasMerged ? "mergiata" : "chiusa";
}

function renderThread(thread) {
  const firstCodexComment = getFirstCodexComment(thread);
  const location = renderThreadLocation(thread);
  const summary = firstLine(firstCodexComment?.body ?? "commento Codex") ?? "commento Codex";
  const threadUrl = firstCodexComment?.url;
  const state = `resolved=${thread.isResolved ? "yes" : "no"}, outdated=${
    thread.isOutdated ? "yes" : "no"
  }`;
  const link = threadUrl ? ` ([thread](${threadUrl}))` : "";

  return `\`${location}\` - ${summary} (${state})${link}`;
}

function renderThreadLocation(thread) {
  const line = thread.line ?? thread.originalLine;

  return line ? `${thread.path}:${line}` : thread.path;
}

function getFirstCodexComment(thread) {
  return thread.comments.nodes.find((comment) =>
    codexLoginPattern.test(comment.author?.login ?? ""),
  );
}

function firstLine(value) {
  return value
    .split("\n")
    .map((line) => line.replace(/<[^>]+>/g, "").trim())
    .find(Boolean)
    ?.slice(0, 160);
}

async function readGitHubEventPayload() {
  const eventPath = process.env.GITHUB_EVENT_PATH;

  if (!eventPath) return null;

  try {
    return JSON.parse(await readFile(eventPath, "utf8"));
  } catch (error) {
    console.warn(`Impossibile leggere GITHUB_EVENT_PATH: ${error.message}`);
    return null;
  }
}

function shouldRunFullScan() {
  if (process.env.CODEX_FULL_SCAN === "true") return true;
  if (!eventName) return true;
  if (eventName === "schedule" || eventName === "workflow_dispatch") return true;

  return eventName === "issue_comment" && eventPayload?.issue?.title === inboxIssueTitle;
}

function getEventPullRequestNumber(payload) {
  if (payload?.pull_request?.number) return payload.pull_request.number;
  if (payload?.issue?.pull_request) return payload.issue.number;

  return null;
}

function parsePositiveInteger(value, fallback) {
  const parsed = Number.parseInt(value ?? "", 10);

  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeInboxMarkerName(value) {
  return (
    value
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "") || "repository"
  );
}

async function githubJson(path, body, method) {
  const { payload, response, text } = await githubRequest(path, {
    body: body ? JSON.stringify(body) : undefined,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    method: method ?? (body ? "POST" : "GET"),
  });

  if (!response.ok) {
    const error = new Error(`GitHub REST ${path} ha risposto ${response.status}: ${text}`);
    error.status = response.status;
    throw error;
  }

  return payload;
}

async function githubGraphql(query, variables) {
  const { payload, response, text } = await githubRequest("/graphql", {
    body: JSON.stringify({
      query,
      variables,
    }),
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    method: "POST",
  });

  if (!response.ok || payload?.errors || !payload?.data) {
    fail(
      `GitHub GraphQL ha risposto con errore: ${JSON.stringify(payload?.errors ?? payload ?? text)}`,
    );
  }

  return payload.data;
}

async function githubRequest(path, init) {
  const url = `https://api.github.com${path}`;

  for (let attempt = 1; attempt <= githubApiAttempts; attempt++) {
    const response = await fetch(url, init);
    const text = await response.text();

    if (!shouldRetryGitHubRequest(response, text) || attempt === githubApiAttempts) {
      const payload = parseGitHubJson(text, path, { allowInvalidJson: !response.ok });

      return { payload, response, text };
    }

    const delayMs = githubRetryDelayMs(response, attempt);
    console.warn(
      `GitHub API ${path} ha risposto ${response.status}; ritento tra ${Math.round(
        delayMs / 1000,
      )}s (${attempt}/${githubApiAttempts}).`,
    );
    await sleep(delayMs);
  }

  fail(`GitHub API ${path} non completata.`);
}

function parseGitHubJson(text, path, options = {}) {
  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch (error) {
    if (options.allowInvalidJson) return null;

    fail(`GitHub API ${path} ha restituito JSON non valido: ${error.message}`);
  }
}

function shouldRetryGitHubRequest(response, text) {
  if ([429, 500, 502, 503, 504].includes(response.status)) return true;
  if (response.status === 403 && isGitHubRateLimitResponse(response, text)) return true;

  return response.status === 401 && text.includes("Bad credentials");
}

function isGitHubRateLimitResponse(response, text) {
  if (response.headers.get("x-ratelimit-remaining") === "0") return true;

  const normalizedText = text.toLowerCase();

  return normalizedText.includes("rate limit") || normalizedText.includes("abuse detection");
}

function githubRetryDelayMs(response, attempt) {
  const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);

  if (Number.isInteger(retryAfter) && retryAfter > 0) return retryAfter * 1000;

  return githubApiRetryBaseMs * 2 ** (attempt - 1);
}

function sleep(delayMs) {
  return new Promise((resolve) => {
    setTimeout(resolve, delayMs);
  });
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
