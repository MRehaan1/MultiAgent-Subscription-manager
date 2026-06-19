# Development Log

Records every change made **after** the design/grilling phase. The design
decisions themselves live in `CONTEXT.md` (domain language) and
`docs/adr/` (architecture decisions); this file tracks the *implementation*
history — what changed, why, and which files. Newest session on top.

---

## 2026-06-18 — Session 1: Scaffold → working multi-agent system

### 1. Initial scaffold (the 14 locked grill decisions)
- Created the `src/` package: `config`, `database`, `catalog_tools`,
  `invoice_tools`, `verification`, `memory`, `state`, `agents`, `graph`, `main`.
- Added `requirements.txt`, `.env.example`, `.gitignore`, `README.md`.
- **Why:** translate the grilling outcomes into runnable code.

### 2. Model → `gemini-3.1-flash-lite-preview`
- Changed `config.py` `MODEL_NAME` from `gemini-2.0-flash`.
- **Why:** 15 RPM free-tier limit vs 5 RPM, so a multi-call turn is far less
  likely to hit 429s during the recorded demo.

### 3. Migrated `create_react_agent` → `create_agent` (LangChain v1)
- `agents.py` now uses `langchain.agents.create_agent`; the music agent's
  runtime preference injection (grill #10) moved from a callable prompt to the
  `dynamic_prompt` middleware (reads `loaded_memory` from `request.state`).
- **Why:** `langgraph.prebuilt.create_react_agent` is deprecated on the
  installed stack (langchain 1.3.9 / langgraph 1.2.5).

### 4. Dropped `langchain-community`
- Removed the unused `SQLDatabase` import + `db` object from `database.py`;
  removed the dep from `requirements.txt`. Tools query via the raw SQLAlchemy
  engine + `run_query`.
- **Why:** `langchain-community` is being sunset (deprecation warning) and we
  never actually used `SQLDatabase`.

### 5. Split state schema: `AgentState` vs `State`
- `state.py` now defines `AgentState` (no managed channel) for the
  `create_agent` sub-agents, and `State` (adds `remaining_steps`) for the
  supervisor + outer graph.
- **Why:** conflicting library constraints — `create_agent` *rejects* managed
  channels in its `state_schema`, while `langgraph-supervisor`'s internal
  `create_react_agent` *requires* `remaining_steps`.

### 6. BUGFIX — long-term preferences were never saved
- Added `output_mode="full_history"` to `create_supervisor` in `agents.py`.
- **Why:** the default `last_message` mode dropped the sub-agents' tool-call
  messages before they reached the outer state, so `create_memory`'s
  "music engaged?" gate never fired and nothing was written. `full_history`
  propagates those messages up. (Confirmed fixed at runtime: turn 2
  "songs that match my preferences" now returns Rolling Stones songs.)

### 7. BUGFIX (A) — input typed at the verification interrupt was lost
- `verify_info` now appends each `interrupt()` reply to `messages` as a
  `HumanMessage` before returning.
- **Why:** the resumed text (which often contains the actual question, not just
  credentials) was only used for verification and never added to the
  conversation, so the supervisor only saw the first message.

### 8. BUGFIX (B) — multi-intent query only answered by one agent
- Tightened both sub-agent prompts to **stay in their lane** (invoice agent must
  not comment on/apologize about music, and vice-versa) and strengthened the
  supervisor prompt to verify *all* parts are answered before finishing.
- **Why:** on "purchase + Rolling Stones" the invoice agent answered invoices
  *and declined the music part*, so the supervisor thought the request was done
  and never routed to `music_catalog`. (Pending user re-test.)

### 9. Named the internal supervisor `router_supervisor`
- `supervisor_name="router_supervisor"` in `create_supervisor`.
- **Why:** xray graph diagrams collided on two subgraphs both named
  `supervisor` (our outer node + the library's internal node).

### 10. Observability — logging + live trace
- Added `logging_config.py` (`mss.*` logger, `LOG_LEVEL` env var) and
  instrumented `verify_info`, `load_memory`, `create_memory`.
- `main.py` now **streams** the graph (with subgraphs) and prints a live trace
  of nodes, tool calls, tool results, and handoffs; toggle with `:trace`.
- **Why:** requested visibility into agent behaviour under the hood.

### 11. Graph visualization
- Added `src/visualize.py` → writes `graph.mmd` (Mermaid) and `graph.png`
  (best-effort PNG), with sub-agents expanded via `xray=True`.
- **Why:** a reference diagram of the full graph topology.

### 12. Reverted the logging/trace instrumentation (supersedes #10)
- Deleted `logging_config.py`; removed the `mss.*` log calls from `verify_info`,
  `load_memory`, `create_memory`; reverted `main.py` to the simple
  `invoke`-based REPL (no `:trace`, no streaming). Kept the one-line langgraph
  warning suppression and the Gemini content flattening.
- **Why:** call tracing will be done later with **Langfuse** instead. The graph
  visualization (`visualize.py`, change #11) is unaffected and stays.

### 13. Documented the full grilling session
- Added `docs/GRILLING-SESSION.md` recording all 14 design decisions
  (question / options / decision / rationale / code location), with
  implementation refinements cross-referenced to this DEVLOG.
- **Why:** the decisions were scattered across CONTEXT.md, the ADR, and chat;
  needed one consolidated reference.

### 14. Confirmed BUGFIX A & B at runtime
- Verified with the demo: a single combined query ("phone + purchase + Rolling
  Stones albums") now returns both the invoice total ($8.91) AND the albums in
  one fused answer (Bugfix B), and the interrupt input-capture works (Bugfix A).
  Preferences round-trip correctly (turn 2 returns Rolling Stones songs).

### 15. Documented the runtime technical journey
- Added `docs/TECHNICAL-JOURNEY.md`: a code-level walkthrough of the demo
  (nodes, tools, files, functions, and how each is invoked).

### 16. Documented the LLM request flow
- Added `docs/LLM-REQUESTS-DEMO.md`: the full sequence of LLM round-trips for the
  demo (calls A–N), each with request (tools + messages) and response
  (`tool_call` or `content`), explaining how routing and tool calls are the same
  primitive.

### 17. Integrated Langfuse tracing (optional)
- Added `src/tracing.py` (`get_langfuse_handler`, `flush_langfuse`); `main.py`
  attaches the handler via `config["callbacks"]` on every invoke and flushes on
  exit. Reads `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`
  (host); disabled cleanly when keys are blank. Added `langfuse` to
  requirements and the keys to `.env.example` + README.
- **Why:** call tracing (replaces the reverted ad-hoc logging, change #12).
- **Verified:** no-keys → handler None (app runs); fake keys → handler builds.

### 18. Applied Langfuse skill best practices
- Installed the official Langfuse skill (github.com/langfuse/skills) and followed
  its `instrumentation.md`. Enriched the run config in `main.py`:
  `run_name="music-support-turn"` (descriptive trace name),
  `langfuse_session_id = thread_id` (groups a session's turns in the Sessions
  view), and `langfuse_user_id = customer_id` (per-customer attribution, set once
  verification has run). Added `_current_customer_id()` to read the verified id
  from graph state per turn.
- **Why:** the skill's inference table maps multi-turn → session_id and
  user-aware → user_id; both fit this app and add filtering/grouping without
  hiding data.
- Followed the skill's "Documentation First" rule (confirmed the v4
  `get_client()` + `CallbackHandler()` + `config["callbacks"]` pattern against
  current docs).

### 19. Added a visual trace walkthrough
- Added `docs/trace-walkthrough.html`: a self-contained, observability-style
  waterfall built from the Langfuse export of the two demo turns. Color-codes
  each span (verify / router / sub-agent / tool / memory) and shows the real
  token counts, latencies, tool args, and per-turn cost (~$0.0038 total, 14 LLM
  calls). Also published as a shareable Artifact.
- **Why:** an at-a-glance explainer of what happens under the hood, for the demo
  defense — complements `docs/LLM-REQUESTS-DEMO.md` (the raw request flow).

### Open / pending
- _(none)_
- Re-test BUGFIX (B): confirm the single combined query now returns both the
  invoice total *and* the Stones albums in one fused answer.
- Runtime validation of the verification-interrupt input-capture (BUGFIX A).
