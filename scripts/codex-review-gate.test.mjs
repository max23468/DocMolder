import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import {
  CODEX_REVIEW_POLLING,
  classifyCodexReview,
  codexRetryCutoff,
  hasSuccessfulCodexStatus,
  isRetryableGitHubResponse,
  latestCodexInvocation,
  pullRequestNumber,
  retryGitHubWrite,
} from "./codex-review-gate.mjs";

const headSha = "0123456789abcdef0123456789abcdef01234567";
const requestedAt = "2026-08-04T12:00:00Z";
const bot = { login: "chatgpt-codex-connector[bot]" };

const classify = (overrides = {}) =>
  classifyCodexReview({
    headSha,
    requestedAt,
    now: new Date(requestedAt).getTime() + 60_000,
    comments: [],
    reactions: [],
    reviewComments: [],
    ...overrides,
  });

test("resta pending senza un esito Codex", () => {
  assert.equal(classify().state, "pending");
});

test("ignora segnali che non provengono dal bot Codex esatto", () => {
  assert.equal(
    classify({
      comments: [
        {
          user: { login: "chatgpt-codex-connector" },
          created_at: "2026-08-04T12:00:01Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
      reactions: [
        {
          user: { login: "max23468" },
          content: "+1",
          created_at: "2026-08-04T12:00:02Z",
        },
      ],
    }).state,
    "pending",
  );
});

test("il pollice sulla PR approva la review automatica iniziale", () => {
  assert.equal(
    classify({
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:03Z" }],
    }).state,
    "success",
  );
});

test("un pollice tardivo non approva una review del commit precedente", () => {
  assert.equal(
    classify({
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:02Z" }],
      requiresReviewedCommit: true,
      reviews: [
        {
          user: bot,
          submitted_at: "2026-08-04T12:00:01Z",
          body: "**Reviewed commit:** `abcdef0123`",
        },
      ],
    }).state,
    "pending",
  );
});

test("il commit_id nativo approva una review pulita con corpo vuoto", () => {
  assert.equal(
    classify({
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:03Z" }],
      requiresReviewedCommit: true,
      reviews: [
        {
          user: bot,
          commit_id: headSha,
          submitted_at: "2026-08-04T12:00:02Z",
          body: "",
        },
      ],
    }).state,
    "success",
  );
});

test("un vecchio pollice non approva una review successiva dello stesso commit", () => {
  assert.equal(
    classify({
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:01Z" }],
      requiresReviewedCommit: true,
      reviews: [
        {
          user: bot,
          submitted_at: "2026-08-04T12:00:02Z",
          body: `**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "pending",
  );
});

test("il pollice senza Reviewed commit non approva", () => {
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:01Z" }],
    }).state,
    "pending",
  );
});

test("il pollice sull'invocazione corrente approva l'HEAD senza review testuale", () => {
  const reaction = { user: bot, content: "+1", created_at: "2026-08-04T12:00:01Z" };
  assert.equal(
    classify({
      exactReactions: [reaction],
      reactions: [reaction],
      requiresReviewedCommit: true,
    }).state,
    "success",
  );
});

test("un rerun non riusa il pollice di una vecchia invocazione", () => {
  const reaction = { user: bot, content: "+1", created_at: "2026-08-04T12:00:01Z" };
  assert.equal(
    classify({
      exactReactions: [reaction],
      reactions: [reaction],
      requestedAt: "2026-08-04T12:00:02Z",
      requiresReviewedCommit: true,
    }).state,
    "pending",
  );
  assert.equal(
    latestCodexInvocation(
      [
        {
          id: 1,
          user: { login: "max23468" },
          body: "@codex review",
          created_at: "2026-08-04T12:00:01Z",
        },
      ],
      "2026-08-04T12:00:02Z",
    ),
    undefined,
  );
});

test("il verdetto pulito del task agent approva soltanto l'HEAD dichiarato", () => {
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "success",
  );
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** `abcdef0123`",
        },
      ],
    }).state,
    "pending",
  );
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: `Nessun problema.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "pending",
  );
});

test("un finding sull'HEAD corrente blocca il gate", () => {
  assert.equal(
    classify({
      reviewComments: [
        {
          user: bot,
          commit_id: headSha,
          created_at: "2026-08-04T12:00:01Z",
          body: "**P1** Correggi questo caso",
        },
      ],
    }).state,
    "failure",
  );
});

test("un finding del tentativo corrente prevale sul pollice", () => {
  assert.equal(
    classify({
      reviewComments: [
        {
          user: bot,
          commit_id: headSha,
          created_at: "2026-08-04T12:00:01Z",
          body: "**P1** Correggi questo caso",
        },
      ],
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:02Z" }],
    }).state,
    "failure",
  );
});

test("un finding top-level sull'HEAD prevale sul riepilogo pulito", () => {
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: `**P2** Correggi il gate.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
        {
          user: bot,
          created_at: "2026-08-04T12:00:02Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "failure",
  );
});

test("un finding top-level senza correlazione non migra su un nuovo tentativo", () => {
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "**P2** Correggi il gate.",
        },
        {
          user: bot,
          created_at: "2026-08-04T12:00:02Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "success",
  );
});

test("un finding top-level dopo eyes sulla specifica invocazione blocca", () => {
  const eyes = { user: bot, content: "eyes", created_at: "2026-08-04T12:00:01Z" };
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      exactReactions: [eyes],
      reactions: [eyes],
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:02Z",
          body: "**P2** Correggi il gate.",
        },
      ],
    }).state,
    "failure",
  );
});

test("un finding top-level marcato su un altro SHA non blocca l'HEAD", () => {
  assert.equal(
    classify({
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "**P2** Finding precedente.\n\n**Reviewed commit:** `abcdef0123`",
        },
        {
          user: bot,
          created_at: "2026-08-04T12:00:02Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "success",
  );
});

test("un rerun ignora i finding top-level precedenti al cutoff", () => {
  assert.equal(
    classify({
      requestedAt: "2026-08-04T12:00:02Z",
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "**P2** Finding di un tentativo precedente.",
        },
        {
          user: bot,
          created_at: "2026-08-04T12:00:03Z",
          body: `Codex Review: Didn't find any major issues.\n\n**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
    }).state,
    "success",
  );
});

test("una review Codex vuota non viene scambiata per un finding", () => {
  assert.equal(
    classify({
      reviewComments: [
        {
          user: bot,
          commit_id: headSha,
          created_at: "2026-08-04T12:00:01Z",
          body: "Nessuna modifica necessaria.",
        },
      ],
    }).state,
    "pending",
  );
});

test("un finding precedente non segue l'HEAD dopo un rebase", () => {
  assert.equal(
    classify({
      reviewComments: [
        {
          user: bot,
          commit_id: headSha,
          original_commit_id: "abcdef0123456789abcdef0123456789abcdef01",
          created_at: "2026-08-04T12:00:01Z",
          body: "**P1** Finding già corretto",
        },
      ],
    }).state,
    "pending",
  );
});

test("un finding precedente non chiude un nuovo tentativo sullo stesso HEAD", () => {
  assert.equal(
    classify({
      reviewComments: [
        {
          user: bot,
          commit_id: headSha,
          original_commit_id: headSha,
          created_at: "2026-08-04T11:59:59Z",
          body: "**P1** Finding precedente",
        },
      ],
      reviews: [
        {
          user: bot,
          submitted_at: "2026-08-04T12:00:02Z",
          body: `**Reviewed commit:** \`${headSha.slice(0, 10)}\``,
        },
      ],
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:03Z" }],
    }).state,
    "success",
  );
});

test("un limite Codex chiude il gate senza lasciare il workflow appeso", () => {
  assert.equal(
    classify({
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "You have reached your Codex usage limits for code reviews.",
        },
      ],
    }).state,
    "failure",
  );
});

test("un errore Codex sconosciuto chiude il gate", () => {
  assert.equal(
    classify({
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "Codex Review: Something went wrong. Try again later.\n\nUnknown error",
        },
      ],
    }).state,
    "failure",
  );
});

test("un errore tardivo non chiude una review corrente ancora in corso", () => {
  assert.equal(
    classify({
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "Codex could not complete the review",
        },
      ],
      progressReactions: [{ user: bot, content: "eyes", created_at: "2026-08-04T12:00:02Z" }],
    }).state,
    "pending",
  );
});

test("un errore successivo a eyes chiude il tentativo", () => {
  assert.equal(
    classify({
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:03Z",
          body: "Codex could not complete the review",
        },
      ],
      progressReactions: [{ user: bot, content: "eyes", created_at: "2026-08-04T12:00:02Z" }],
    }).state,
    "failure",
  );
});

test("un rerun ignora un errore transitorio storico", () => {
  assert.equal(
    classify({
      requestedAt: "2026-08-04T12:00:02Z",
      requiresReviewedCommit: true,
      comments: [
        {
          user: bot,
          created_at: "2026-08-04T12:00:01Z",
          body: "Codex could not complete the review",
        },
      ],
      reviews: [
        {
          user: bot,
          commit_id: headSha,
          submitted_at: "2026-08-04T12:00:03Z",
          body: "",
        },
      ],
      reactions: [{ user: bot, content: "+1", created_at: "2026-08-04T12:00:04Z" }],
    }).state,
    "success",
  );
});

test("un rerun sullo stesso SHA accetta la nuova invocazione esatta", () => {
  const reaction = { user: bot, content: "+1", created_at: "2026-08-04T12:00:03Z" };
  assert.equal(
    classify({
      exactReactions: [reaction],
      reactions: [reaction],
      requestedAt: "2026-08-04T12:00:02Z",
      requiresReviewedCommit: true,
    }).state,
    "success",
  );
});

test("il polling mantiene cinque ore senza saturare la quota con cinque PR", () => {
  assert.equal(CODEX_REVIEW_POLLING.attempts * CODEX_REVIEW_POLLING.intervalMs, 5 * 60 * 60 * 1000);
  assert.ok((5 * 5 * 60 * 60 * 1000) / CODEX_REVIEW_POLLING.intervalMs <= 500);
});

test("legge le reazioni dall'ultima invocazione Codex del tentativo corrente", () => {
  assert.equal(
    latestCodexInvocation(
      [
        { id: 1, user: bot, body: "@codex review", created_at: "2026-08-04T12:00:03Z" },
        {
          id: 2,
          user: { login: "max23468" },
          body: "@codex review",
          created_at: "2026-08-04T12:00:01Z",
        },
        {
          id: 3,
          user: { login: "max23468" },
          body: "@codex review",
          created_at: "2026-08-04T12:00:02Z",
        },
      ],
      requestedAt,
    ).id,
    3,
  );
});

test("il bootstrap accetta soltanto un numero PR", () => {
  assert.equal(pullRequestNumber({ pull_request: { number: 42 } }), "42");
  assert.equal(pullRequestNumber({}, "208"), "208");
  assert.throws(() => pullRequestNumber({}, "208/merge"), /Numero PR non valido/);
});

test("ritenta soltanto errori GitHub recuperabili", () => {
  assert.equal(isRetryableGitHubResponse(429, null), true);
  assert.equal(isRetryableGitHubResponse(502, null), true);
  assert.equal(isRetryableGitHubResponse(403, "0"), true);
  assert.equal(isRetryableGitHubResponse(403, "4999"), false);
  assert.equal(isRetryableGitHubResponse(404, null), false);
});

test("il retry manuale parte dallo status Codex precedente dello stesso SHA", () => {
  assert.equal(
    codexRetryCutoff(
      [
        {
          context: "codex-review",
          state: "failure",
          created_at: "2026-08-04T12:00:01Z",
        },
      ],
      "2026-08-04T11:00:00Z",
    ),
    "2026-08-04T12:00:01Z",
  );
  assert.equal(codexRetryCutoff([], "2026-08-04T11:00:00Z"), "2026-08-04T11:00:00Z");
});

test("le scritture GitHub ritentano soltanto errori recuperabili", async () => {
  let attempts = 0;
  const waits = [];
  const result = await retryGitHubWrite(
    async () => {
      attempts += 1;
      if (attempts < 3) throw Object.assign(new Error("rate limit"), { retryable: true });
      return "ok";
    },
    async (ms) => waits.push(ms),
  );
  assert.equal(result, "ok");
  assert.equal(attempts, 3);
  assert.deepEqual(waits, [5_000, 5_000]);

  attempts = 0;
  await assert.rejects(
    retryGitHubWrite(async () => {
      attempts += 1;
      throw Object.assign(new Error("forbidden"), { retryable: false });
    }),
    /forbidden/,
  );
  assert.equal(attempts, 1);
});

test("un rerun riusa soltanto l'ultimo status Codex riuscito dello stesso SHA", () => {
  assert.equal(
    hasSuccessfulCodexStatus([
      { context: "codex-review", state: "success" },
      { context: "codex-review", state: "pending" },
    ]),
    true,
  );
  assert.equal(
    hasSuccessfulCodexStatus([
      { context: "codex-review", state: "failure" },
      { context: "codex-review", state: "success" },
    ]),
    false,
  );
});

test("il workflow usa eventi, permessi e branch fidato esatti", () => {
  const source = readFileSync(
    new URL("../.github/workflows/codex-review-gate.yml", import.meta.url),
    "utf8",
  );

  assert.match(source, /pull_request_target:\n\s+types: \[opened, synchronize, reopened, ready_for_review\]/);
  assert.match(source, /workflow_dispatch:\n\s+inputs:\n\s+pull_request:[\s\S]*?type: number/);
  assert.match(
    source,
    /permissions:\n  contents: read\n  issues: read\n  pull-requests: read\n  statuses: write\n/,
  );
  assert.match(source, /group: codex-review-\$\{\{ github\.event\.pull_request\.number \|\| inputs\.pull_request \}\}/);
  assert.match(source, /cancel-in-progress: true/);
  assert.match(source, /timeout-minutes: 310/);
  assert.match(source, /actions\/checkout@[0-9a-f]{40}/);
  assert.match(source, /ref: \$\{\{ github\.event\.repository\.default_branch \}\}/);
  assert.match(source, /run: node scripts\/codex-review-gate\.mjs/);
  assert.doesNotMatch(source, /github\.event\.pull_request\.head|github\.head_ref|refs\/pull/);
});

test("l'import in GitHub Actions non avvia la CLI", () => {
  const result = spawnSync(
    process.execPath,
    [
      "--input-type=module",
      "--eval",
      `import(${JSON.stringify(import.meta.resolve("./codex-review-gate.mjs"))})`,
    ],
    {
      env: { ...process.env, GITHUB_ACTIONS: "true", GITHUB_EVENT_PATH: "/non-esiste" },
      encoding: "utf8",
    },
  );
  assert.equal(result.status, 0, result.stderr);
});
