# Review — chatbot_agent — 2026-08-05

**Reviewed:** `src/chatbot_agent/{graph,llm_client,checkpointer,app}.py`,
`src/chatbot_agent/nodes/chatbot.py`, `src/chatbot_agent/tools/postgres.py`,
`src/api/routes/chat.py`
**Pattern:** tool-using agent (ladder row 8) · **Tier:** `StateGraph`
**Verdict:** Pattern and tier are right; the defects were bounded spend, an
unrecorded stop reason, and no eval set — all fixed in this pass.

## Findings

**HIGH — `evals/` did not exist — no eval set.**
Every prompt change was an unmeasurable coin flip. This was not theoretical: on
the live database the agent answered "there are 86 launches" when the true count
is 215 — it had reused the top area's figure as the overall total, and nothing
would have caught it. Fixed: `evals/cases.jsonl` (12 cases, each with the reason
it exists) plus `evals/run.py` against the real graph. Two of the twelve failed
on first run *because the expected answers were wrong* — Alexandria does have a
project, and "most common property type" is ambiguous between the units and
projects views — which is itself the argument for the file existing.

**HIGH — `api/routes/chat.py:33` — no stop reason recorded, no step ceiling.**
A model looping on failing SQL hit LangGraph's default recursion limit and
surfaced as a generic 502, indistinguishable from the model endpoint being down.
One is a prompt or schema problem, the other is an outage, and the logs could not
tell them apart. Fixed: `MAX_STEPS = 12` passed as `recursion_limit`,
`GraphRecursionError` caught separately as 504, and `stop_reason=complete |
max_steps | error` logged on every exit path.

**MEDIUM — `tools/postgres.py:147` — tool output bounded by rows, not by size.**
`query_database` capped results at 100 rows, but `raw` is a JSONB column holding
an entire source payload; `SELECT * FROM projects LIMIT 100` would return several
hundred KB and fill the model's 32K window in one tool result, leaving no room to
reason about it. Fixed: 6,000-character bound whose truncation message tells the
model what to do differently (select fewer columns, aggregate in SQL).

**MEDIUM — `nodes/chatbot.py` — prompt inlined in orchestration code.**
Against the stack convention that prompts live in versioned files: an inline
prompt makes diffs unreadable and prevents an eval run from pinning the version
it scored. Fixed: `src/chatbot_agent/prompts/system_v1.md` loaded via
`load_system_prompt()`.

**LOW — no ADR.** The choice of `StateGraph` over `create_agent` is undocumented,
so it will be re-litigated. See the architecture note below; an ADR is still
worth writing.

### Not a finding — audit script false positive

`scripts/audit.py` reports **CRITICAL — vector search with no filter** against
`tools/postgres.py`. There is no vector search here. The check's regex
`(qdrant|\.search\(|query_vector)` matches `_WRITE_KEYWORDS.search(statement)`,
a `re.Pattern.search` call in the SQL guard. This project has no Qdrant
collection and no multi-brand data — it is single-tenant over one Postgres
catalogue. No action.

## Architecture note

The ladder lands on row 8 (tool-using agent): the request is open-ended natural
language, the number and shape of queries depends on the question, and mistakes
are recoverable because the tool is read-only. That is correct — a fixed chain
cannot know whether a question needs one aggregate or three.

The tier is `StateGraph` rather than `create_agent`, and here that is justified
rather than ceremony: the graph carries a Postgres checkpointer keyed by
`conversation_id` so a conversation survives a process restart and can be resumed
over HTTP or from the CLI. That is durable state, which is the stated reason to
choose a graph. The cycle is real too — `chatbot ⇄ tools` runs until the model
answers without a tool call.

Cost of the choice: more moving parts than `create_agent`, and the checkpointer
needs its own tables. Both are paid for by resumable conversations, which the
HTTP endpoint requires.

## Not flagged

Checked and found sound, so the next reviewer need not repeat it:

- **SQL injection / destructive SQL.** Three independent layers: a least-privilege
  role, a Postgres `READ ONLY` transaction with a statement timeout, and an
  allow-list parser. Verified against a live database with the parser
  deliberately disabled — `DELETE` and `DROP` were both refused by the server.
- **Tool error messages teach.** A rejected query returns the reason
  ("Only read-only SELECT/WITH queries are allowed, got 'DROP'"), so the model
  corrects itself rather than retrying blindly.
- **Tool descriptions.** `describe_schema` and `query_database` do not overlap,
  and each states its constraint. No disambiguation burden on the model.
- **Prefix caching.** The system prompt is static — no timestamp, session id or
  interpolation — so the cached prefix holds across requests.
- **Import-time side effects.** Engine and model are both lazy; the whole package
  imports with no database and no model endpoint reachable.
- **Auth.** `/chat` sits behind the same API key as every other data route.
- **Timeouts.** Statement timeout on every query, verified cancelling a
  `pg_sleep(30)` at 1.1s.

## Open

- Eval set is 12 cases; the target is 20.
- No tracing backend. Stop reason and tool calls go to the application log only,
  which is enough to debug but not to measure over time.
- `gemma-4` reliability: the 86-vs-215 error was a real reasoning failure, fixed
  by prompt changes and now guarded by a case. Expect more of this class; the
  eval set is the mechanism that catches them.
