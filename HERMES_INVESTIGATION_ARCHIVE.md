# Hermes Agent Investigation Archive

- **Project:** Hermes Agent
- **Branch:** `eilan-integrated-routing` (as reported by the current checkout)
- **Investigation scope:** Semantic/task-based model routing, provider and credential fallback, Gemini/OpenRouter/Groq/Cerebras/BluesMinds/XKiro reports, retry and route identity, route health/quarantine, error classification, Telegram turn/delivery behavior, runtime latency, test results, and previously requested Gateway workflow/live checks.
- **Archive date:** 2026-10-08
- **Evidence limitation:** This archive combines the conversation history and current source/test evidence available in this session, plus a filename-only inventory of Hermes logs. Several earlier assistant reports and live command outputs are not present in the recoverable transcript. They are identified as unavailable rather than reconstructed. No credentials or raw secret-bearing log text are included.

## Current known architecture

The current source has an automatic semantic routing layer in `agent/semantic_model_router.py`. It classifies each task locally, gathers routes from primary, fallback, semantic, named-provider, and custom-provider configuration, consults process-local route health, looks up model capabilities without network discovery, scores candidates, and passes a ranked route list into the Gateway/agent path. The route is resolved through Hermes' normal runtime provider resolver. The agent can rotate credentials in a provider credential pool and can switch configured model/provider routes after classified failures. Telegram session/channel model overrides are checked before semantic selection. Final Telegram delivery runs after the agent turn and has its own delivery ledger/send retry path.

That architecture has multiple related but distinct state/budget mechanisms:

- Semantic route health in the process-global `_ROUTE_HEALTH` map.
- Credential-pool health/cooldowns, including credential and model-scoped state.
- In-agent fallback chain index and per-agent unavailable fallback-key set.
- Per-API-call retry state and credential-rotation/recovery state.
- An outer rebuilt-message restart counter, currently bounded using `max_retries`.
- Telegram delivery tracking after the agent has produced a result.

The source audit found these mechanisms do not share one canonical route identity or one unified attempt budget.

## Current known symptoms

- User-reported Telegram fallback sequences included Gemini 2.5 Flash via Gemini followed by Gemini 2.5 Flash via Gemini again, and later a BluesMinds Nemotron 3.5 Lightning 30B model, followed by an exhaustion message.
- User-reported trivial Telegram messages such as `مرحبا` had noticeable latency.
- A user observed Telegram-visible fallback notices while one `gateway.log` entry for a logged `مرحبا` turn showed one Gemini API call and a successful completion.
- The user reported a “No reply: every provider in the fallback chain kept failing over” response.
- Earlier requests sought live status/failure details for Groq, OpenRouter, and XKiro. The exact resulting runtime report is not recoverable in this session context.

These are user-reported observations, not all independently reproduced in the current audit.

## Important verified runtime facts

- **Current live Gateway state was not checked for this archive.** No PID, current CWD, current config path, live primary route, active fallback order, or current process count is verified here.
- In an earlier user report, PID `86616` was named during a question about whether the Gateway loaded modified source. The exact prior answer and supporting process inspection are not recoverable; this archive does not treat that PID or source-load status as verified.
- A past user report described a successful Gemini API completion in a `gateway.log` entry for `مرحبا`; the user explicitly cautioned that this entry did not prove the separate Telegram-visible fallback sequence. That correction is retained below.
- The current filename-only log inventory found `agent.log`, `errors.log`, `gateway-exit-diag.log`, `gateway-shutdown-diag.log`, `gateway.log`, `gateway_faulthandler.log`, and `scratch-prune.log` under the Hermes log directory, plus Gateway log/start files elsewhere under Hermes home. Their contents were not printed or copied into this archive.
- The latest focused source/test audit passed 284 tests in 14 test files. No live Telegram test was performed as part of that audit.

## Evidence labels

- **CONFIRMED:** Directly supported by current source/test output or an explicit user-provided observation (the latter is marked as user-reported).
- **LIKELY:** Supported by source shape but depends on runtime/config details not available here.
- **POSSIBLE:** A viable path, but not demonstrated as the cause of a particular live turn.
- **HYPOTHESIS:** A proposed explanation that needs logs/runtime evidence.
- **DISPROVED:** Contradicted by later evidence or current source. Superseded items are preserved with a correction note.

# Chronological investigation record

The transcript does not preserve every prior assistant response verbatim. The entries below preserve the detail that is available, and mark missing outcomes explicitly.

## 1. Branch review: semantic routing, free fallback, Telegram, 401/429

**Request:** Review the current Hermes changes on `eilan-integrated-routing`, especially semantic routing, free-provider fallback, Telegram routing, and 401/429 handling; identify configured providers usable as genuinely free fallbacks without paid billing; never expose credentials.

**Recoverable result:** The exact earlier review text, provider inventory, provider billing evidence, and cited source locations are not present in the available transcript. No claim about which configured provider was genuinely free is reproduced here. The current source audit below is a later review of routing behavior, but does not establish live credential presence or free-service eligibility.

**Status:** Earlier report unavailable in full. Do not treat absence of its text as evidence that no review occurred.

## 2. Telegram Gateway persistent development workflow

**Request:** Inspect the Gateway launch method; preserve exactly one running Gateway; keep Telegram connected in a persistent session; verify another Termux SSH session can access `/workspaces/hermes-agent` and run Codex CLI independently.

**Recoverable result:** The full launch-method inspection, process count, tmux/session name, second-session verification, and Codex CLI result are not present in the recoverable report text. A later request referred to restarting the existing Gateway in its existing tmux session, indicating that a tmux session was part of the user’s understanding at that point, but it does not independently prove the original verification details.

**Status:** Prior workflow report incomplete/unavailable; no current process assertion.

## 3. Provider/model pool implementation request and 51-test report

**Request:** Implement task-to-capability model ranking across configured routes, route health/cooldown, fallback after quota/429/auth/outage, credential-pool handling, explicit override preservation, no paid fallback, Telegram behavior, and extensive tests.

**Recoverable facts:** Later, the user stated that “51 focused tests passed and the final validation is clean.” The user then authorized activation of completed changes. The currently modified worktree contains changes in the semantic router, error handling, fallback helpers, Gateway route selection/runner, stream timing, configuration defaults, metrics, and tests. This archive does not claim that the current diff is byte-for-byte identical to the exact implementation version covered by the earlier 51-test report.

**Historical test result (user-reported):** 51 focused tests passed; final validation clean. The exact command/output is unavailable.

## 4. Activation of the completed routing changes

**Request:** Restart only the existing live Gateway in its existing tmux session; keep one Gateway; verify one process; run one trivial live Telegram test and report detailed timings/provider/model/fallback.

**Recoverable result:** The exact restart command, PID before/after, process-count evidence, live test result, and timing values are not available in the transcript. Later turns discuss a post-restart live Telegram observation, but do not provide a complete timing report.

**Status:** A later user message describes the Gateway test as occurring after restart; exact operational proof is unavailable here.

## 5. Simple Telegram latency investigation

**Request:** Investigate end-to-end latency for `مرحبا`; trace Gateway receive, classification, pool build, health, credential resolution, selection, retry, first model request/token, final response, and Telegram send. Do not restart or add an external classifier/model. Add focused diagnostics/tests and optimize only measured bottlenecks.

**Recoverable result:** The user later reported that 51 focused tests passed and final validation was clean, then asked to activate the changes. Exact before/after timings and the prior assistant’s bottleneck conclusion are not recoverable, so no measured latency values are reproduced.

**Current source evidence (later audit):** Timing fields exist for classification, route-pool lookup/cache hit, health filtering, ranking, credential resolution, fallback selection, request preparation, response headers/first chunk/total request, and final platform send clock. `stream_started_at` is recorded at stream-diagnostic initialization, while `connection_ms` and `first_chunk_ms` are deltas from that timestamp; those fields can overlap request setup and are not a clean decomposition into socket connect vs model TTFT. Aggregate retry/backoff/credential rotation/outer restart time is not separately totaled in the inspected instrumentation.

**Status:** Latency instrumentation is confirmed; actual per-stage time for the historical Telegram turn is unavailable.

## 6. Post-restart trivial live Telegram test

**Request:** Restart only the existing Gateway and run one live `مرحبا`, then report total latency, classification, pool lookup, health, ranking, credential resolution, model response/header, first chunk, send, selected route, and fallback.

**Recoverable result:** No complete set of measurements is present in the available context. Later user correction explicitly warns against using one gateway log row as proof of the user-visible fallback chain.

**Status:** Exact outcome/timings unavailable; the later correction governs interpretation.

## 7. User-reported Gemini → Gemini and BluesMinds chain

**Observation provided by user:** After restart, Telegram visibly showed Gemini 2.5 Flash via Gemini unavailable, then the same displayed Gemini model/provider again, then `nvidia/nemotron-3.5-lightning-30b-a3b` via BluesMinds, then all providers exhausted.

**Requested investigation:** Inspect exact `gateway.log` entries for that interaction; establish why Gemini appeared twice, whether route identities/configurations were identical or distinct credentials, which semantic route was selected, why the second attempt happened, why a reasoning-labeled 30B model entered a light task, whether PID 86616 loaded modified source, and available timing fields.

**Recoverable exact result:** The prior assistant’s line-by-line gateway-log report is not fully available in this context. No exact log line or timing is asserted here. The later source audit establishes plausible code paths for repeated same-display routes and insufficient capability filtering, but it does not identify which path happened in this reported turn.

**Current source findings relevant to this observation:**

- Credential identity is part of semantic `_route_key`, but not all call sites construct the active route with a credential identity.
- Fallback-chain deduplication drops credential identity and API mode.
- Capability filtering rejects explicit `supports_tools=False`; missing capability metadata defaults to tools-supported. No explicit ordinary-chat vs translation/safety/auxiliary capability gate exists.
- Therefore same-provider/model with separate credential capacity may appear as a second displayed route, and specialized/large models can remain candidates. These facts do not prove the exact historical selected route.

## 8. Correction: a successful `gateway.log` row does not prove the Telegram fallback chain

**User correction:** One `gateway.log` row for `مرحبا` showed Gemini 2.5 Flash, one API call, successful completion, while Telegram displayed fallback notices. User instructed not to treat that log row as proof of the live fallback sequence.

**Source trace later performed:** The exact fallback-notice string is constructed in `agent/chat_completion_helpers.py::try_activate_fallback()` after a route switch. It describes the old route and new route, and may be buffered/delivered via agent status callbacks. A fallback notice can therefore exist even if a later route/API call succeeds; a successful final response does not imply there was no prior fallback. Gateway turn logs, agent execution/status notices, and Telegram final delivery are separate observability layers. Messages from separate attempts/turns can be interleaved; the exact prior trace’s correlation evidence is not recoverable here, so interleaving for that incident remains unproven.

**Superseded / corrected later:** Any earlier interpretation that the single successful `gateway.log` row represented the complete visible Telegram fallback sequence is superseded by the user correction. The row proves only the logged turn/API completion represented by that row, not the origin/timing of every user-visible notice.

## 9. Route-state lifetime investigation

**Question:** Is unavailable-route state turn-scoped or recreated at each selector call, and do outer retries/recovery paths preserve it?

**Recoverable source conclusions:** Current semantic health is module/process-local `_ROUTE_HEALTH`, so it persists across calls in a running process until cooldown expires or success clears it. Per-agent `_fallback_index` and `_unavailable_fallback_keys` are separate, agent-lifetime fallback state. Each selection consults the process health cache. This means there is not simply one local unavailable-set newly created and discarded by each selector call. However, route keys are inconsistent across route representations, unknown/reasonless failures are not recorded, and retry/restart paths have separate counters. The exact earlier assistant’s full requested call graph is not present; the current source audit is the supporting evidence for these summarized conclusions.

**Status:** “Every selector starts with a completely fresh health state” is **DISPROVED** by process-global health state. The broader invariant “all failures and every retry layer share one consistent turn-scoped failed-route set” is also **DISPROVED**: state is split across process health, per-agent fallback bookkeeping, credential pool, and restart/retry state.

## 10. Why fallback notice may say `provider failure` for unknown

**Question:** Trace a real exception around 19:23:17 through classification, reason, fallback, quarantine, notice; establish whether `unknown` was quarantined and whether it explained Gemini repeats.

**Recoverable exact incident evidence:** The raw exception/body and exact 19:23:17 log context are not available in the current recoverable transcript. No exact exception is invented.

**Current source facts:** `_fallback_reason_text()` maps `unknown` to the user-facing phrase “provider failure.” `mark_route_unavailable()` only writes route health for reasons in `_TRANSIENT_REASONS`, which excludes `unknown`, and returns without a health entry for excluded reasons. Therefore the notice text alone does not prove quarantine.

**Root cause at code level:** Unknown is an allowed display fallback label but is not a quarantinable route-health reason. Whether the historical notice’s reason actually was `unknown` is not recoverable.

**Impact:** Such a route can remain eligible if the fallback path is otherwise taken and route health has no earlier cooldown.

**Does this explain Gemini→Gemini in the same turn?** Not by itself. Missing quarantine can permit later reselection, but the same-turn repeated Gemini can also come from credential rotation or two configured credential routes with the same displayed provider/model. The exact historical mechanism is unresolved.

## 11. Actual runtime request for Groq/OpenRouter/XKiro and failure chain

**Request:** Inspect actual `/workspaces/hermes-agent` and live Gateway state for PID/CWD/config/primary/fallbacks/last three model failures, establish Groq presence, and diagnose Groq/OpenRouter/XKiro failures without secrets.

**Recoverable result:** The resulting runtime inspection/report is not present in the available context. This archive cannot verify current PID/CWD/config, primary route, active fallback list, Groq runtime eligibility, provider response status, or current `_ROUTE_HEALTH`.

**Status:** Unresolved; no credential/status conclusion is copied from assumption.

## 12. Current repository engineering audit (latest complete report)

**Scope:** Read-only audit of current code/test state: repeated Gemini routes, 404/410 classification, quarantine scope, retry/credential/fallback budgets, Telegram no-reply, route identity, error payload robustness, fallback paths, semantic capability filtering, credential pools, delivery, and timing.

### Confirmed current source findings

1. **Generic 404:** `agent/error_classifier.py::_status_404()` checks billing, policy, and model-not-found signals. If none match, it returns `unknown` except for a model ID whose provider catalogue is known to require a prefix. The source intentionally does not infer model-not-found from a bare 404 because endpoint/proxy failure is also possible. The actual historical Gemini 404 category cannot be known without its payload.
2. **Unknown health:** `unknown` is not in `agent/semantic_model_router.py::_TRANSIENT_REASONS`; `mark_route_unavailable()` does not add it to `_ROUTE_HEALTH`.
3. **Gemini→Gemini mechanisms:** credential rotation can retry the same displayed model/provider with a different credential. Semantic route identity can also distinguish credential-bearing entries, while active route construction can omit credential identity. The fallback config’s `_entry_identity()` does the reverse and deduplicates entries without considering credential identity. Source establishes paths, not the exact historical event.
4. **API mode identity:** semantic `_route_key()` includes provider, model, normalized-by-lowercase/trailing-slash base URL, and key reference/hash, but omits `api_mode`. Alias and URL normalization is limited.
5. **Independent loops / coupled cap:** credential recovery runs before generic retries; fallback index advances independently; rebuilt-message outer restarts are bounded by `max_retries`. Therefore the route chain can be cut short by the restart ceiling. The “every provider” explanation can overstate how many routes were attempted.
6. **410:** no dedicated 410 handler exists. Unlisted 4xx defaults to `format_error`, which is fallback-capable but not included in semantic route-health transient reasons.
7. **429:** classifier distinguishes normal rate limit, billing/quota, overloaded provider, and OpenRouter upstream rate limits. Credential recovery attributes failure using the dispatched credential identity and has a provider-pool boundary guard. Upstream OpenRouter 429 deliberately avoids rotating a healthy aggregator credential. No specific live 429 scope error was established.
8. **Capability filtering:** route gathering includes configured named-provider/custom-provider models. Candidate filtering only excludes routes whose capability metadata explicitly says `supports_tools=False`; errors/missing metadata default to tools-supported. Translation/safety/auxiliary suitability is not explicitly excluded. This allows incompatible candidates; actual selection depends on runtime configuration and metadata.
9. **Telegram overrides:** `run_turn_runner.py` disables semantic routing for a session `model_override` or channel model/provider override. Tests include session override and semantic Telegram route behavior, but the current audit’s override tests do not establish every `/model`, channel, and runtime integration permutation.
10. **No-reply text:** “every provider in the fallback chain kept failing over” is associated with `rebuilt_restart_limit_exceeded`, set before Telegram final send when the outer rebuilt restart cap is exceeded. It is not, by itself, evidence of Telegram delivery failure. Telegram final sending is separately handled by the delivery-ledger/send path.
11. **Payload handling:** classifier body extraction accepts dict bodies and catches exceptions from `.json()`. Lists, strings, or `None` do not throw in the inspected dict-gated helpers but can lose structured detail and fall through to message/status classification. Explicit table-driven shape coverage was identified as needed.
12. **Latency instrumentation:** route selection, credential resolution, fallback, request preparation, headers/first chunk, and final send are instrumented. Stream time boundaries are not fully disjoint, and total retry/backoff/credential-rotation/outer restart time is not summarized as a distinct complete chain.

### Latest tests and checks

- `scripts/run_tests.sh` via the repository runner, with the repo `.venv` Python: **14 files, 284 tests passed, 0 failed**.
- The first runner attempt could not create its `/var/tmp` scratch space in the restricted sandbox and collected no tests; it was retried with filesystem approval. This was an environment failure, not a test failure.
- `git diff --check`: passed.
- Python AST syntax parsing of all 14 modified tracked `.py` files: passed.
- `scripts/check --only ruff`: passed.
- No configured mypy/pyright check was found for these Python files.
- The test runner’s normal duration cache did not appear in `git status` afterward.
- Current status contains modified routing/latency/test files and existing untracked `agent/semantic_model_router.py.bak`, `hermes_test.txt`, and `tests/gateway/test_telegram_semantic_free_routing.py`. They were not modified by the audit. The potentially sensitive `hermes_test.txt` was not opened.

### Test gaps identified in the audit

The current focused test run did not establish all requested behavior. Tests still needed include:

- Same exact route cannot be selected twice within one fallback sequence.
- Same-provider credentials remain distinguishable end-to-end after fallback-chain deduplication.
- Generic/model-specific 404 and 410 retirement classification/quarantine.
- 429 credential-vs-provider/upstream scope.
- Timeout fallback/cooldown.
- A fails→B fails→C succeeds and A/B/C all fail→clean exhaustion, with chain longer than retry ceiling.
- Explicit `/model`, session model, and Telegram/channel override behavior end to end.
- Semantic exclusion of translation/safety/auxiliary models from ordinary chat.
- Tool and reasoning behavior preserved after semantic selection.
- Telegram no-reply before final LLM response vs delivery failure after successful final response.
- Classifier dict/list/string/None/nested/malformed payload safety.

## Previously suggested fixes (not applied)

These are plans only; none were applied during the investigations recorded here.

1. Establish one canonical route identity across semantic routing, fallback configuration, current runtime route, and route-health state, including credential identity and API mode when material.
2. Separate per-route retry, credential rotation, fallback route-attempt, and outer restart budgets; only report full exhaustion after eligible routes were actually attempted.
3. Carry an explicit failure scope (credential/model/route/endpoint/provider) and classified reason through all fallback paths; define careful quarantine for retryable unknowns without quarantining deterministic request-shape failures.
4. Treat 410/retired models deliberately and test 404 ambiguity rather than guessing from bare status.
5. Add a conversational-capability eligibility gate for specialized/auxiliary models and a conservative policy for missing metadata.
6. Make “no final LLM response” and “final Telegram delivery failed” distinct result/diagnostic states.
7. Make latency timestamps non-overlapping and report retry, backoff, credential rotation, fallback, and Telegram send totals.
8. Add behavior-contract tests for the test gaps above before deploying any patch.

## Reports/results not fully recoverable

- Full first branch review, including provider-by-provider free/no-paid eligibility and exact 401/429 conclusions.
- Full Gateway tmux/second-Termux-SSH/Codex CLI verification report.
- Full implementation report and exact test command for the historical 51-test result.
- Exact live Gateway restart PID/process-count proof and live Telegram latency breakdown.
- Exact latest `gateway.log` line/context for the Gemini→Gemini→BluesMinds incident and whether the same Gemini entries used identical credential route identity.
- Exact source-load determination for historical PID 86616.
- Exact sanitized exception/body for the incident around 19:23:17.
- Exact runtime config/primary/fallback chain and last three failures for Groq/OpenRouter/XKiro; no conclusion about whether Groq was active or why any of those providers failed.
- Exact measurements for the historical `مرحبا` turn.

These items are explicitly left unresolved rather than inferred from current source.

# Consolidated Current Diagnosis

Only the following conclusions remain supported by the current source and completed checks:

1. The active codebase contains semantic model routing and multiple fallback/recovery mechanisms. Credential rotation, API retry, semantic route fallback, and outer rebuilt restarts are distinct stages, but their state and budgets are not fully unified.
2. Same displayed provider/model can occur through credential rotation or credential-distinct route entries. Conversely, fallback-chain deduplication can collapse credential-distinct entries. Current route identity is inconsistent and omits API mode.
3. A generic/unrecognized 404 is classified `unknown` by design; the code cannot determine whether a particular bare Gemini 404 was model-, endpoint-, proxy-, or configuration-related without its error body/context.
4. `unknown` and reasonless fallback calls do not mark semantic `_ROUTE_HEALTH`; a user-visible “provider failure” notice is not proof a route was quarantined.
5. 410 is not specially classified. It reaches generic unlisted-4xx `format_error` handling and does not enter semantic transient quarantine.
6. The outer fallback/restart ceiling reuses `max_retries`, so a long candidate list can be stopped before every route is attempted; the existing exhaustion wording can therefore be inaccurate.
7. Candidate capability filtering does not explicitly exclude specialized non-chat/auxiliary models when metadata is absent or says only that tools are supported.
8. The “every provider … kept failing over” no-reply explanation is generated from an agent restart-limit exit before final Telegram delivery; it is not evidence of a Telegram send failure.
9. Current latency instrumentation has useful stage measurements but overlapping boundaries and no complete retry/backoff/credential-rotation/fallback total.
10. The latest focused source/test run passed 284 tests, Ruff, syntax parsing, and `git diff --check`. This demonstrates those selected tests and checks pass; it does not resolve the live incidents above.
11. No live Gateway state, active provider chain, credential status, or live Telegram response was inspected for this archive.

# Open Questions

1. What exact sanitized HTTP status/body/code and exception caused the Gemini 404 around the reported turn?
2. Were the two displayed Gemini routes the same credential, two different credentials, or the same route retried internally?
3. Which exact semantic route was selected for the live Arabic greeting, and which source file/version did the then-running PID load?
4. Did the BluesMinds route have explicit capability metadata, missing metadata, or a task-score/ranking reason that placed it in the light-task candidates?
5. What were the active runtime primary route and fallback order for Groq/OpenRouter/XKiro, and which sanitized statuses/errors did their most recent requests return?
6. Was Groq actually included in the running Gateway’s resolved route pool at the time of the earlier runtime request?
7. What was the exact exception/reason for the reported 19:23:17 turn, and did it write to `_ROUTE_HEALTH`?
8. Did the Telegram-visible fallback notices belong to one turn or interleaved turns? The required turn/request correlation IDs and matching raw-but-redacted log lines are unavailable here.
9. What are the exact before/after latency values for classification, ranking, credential resolution, model headers/first chunk, fallback, and final Telegram send?
10. What exact repository state and process/session facts supported the earlier tmux persistence and second SSH/Codex CLI verification?
11. Which configured models/providers are genuinely free and enabled without paid billing? The original inventory report and account/plan evidence are not recoverable here, so no provider is labeled free in this archive.

# Recommended Next Investigation

Perform one read-only, request-correlated capture against the current Gateway, after confirming the exact active PID/CWD and configuration source without printing secrets. For a single Telegram turn, collect only sanitized structured fields: turn/request IDs, provider/model, route identity represented by a non-reversible credential label, API mode, attempt/retry/fallback indices, status/error classification/scope, quarantine state transition, timing stamps, final LLM result state, and Telegram send result. Match all records by the same turn ID before interpreting same-provider/model notices. Separately resolve the configured candidate list and capability metadata locally without model-discovery network calls. Compare the observed attempt sequence to the current source paths and only then decide which proposed patch is justified. Do not apply any fixes as part of this next investigation.
