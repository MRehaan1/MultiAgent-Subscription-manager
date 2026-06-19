# Grilling Session — Design Decisions

The full record of the design interview held before implementation. Each entry
captures the **question**, the **options** considered, the **decision**, the
**rationale**, and **where** it lives in the code. Companion docs:
`CONTEXT.md` (domain language), `docs/adr/0001-*` (the security ADR),
`DEVLOG.md` (implementation history, incl. refinements found while coding).

> A few decisions were *refined* during implementation against the installed
> stack (LangChain 1.3.9 / LangGraph 1.2.5). Those refinements are flagged
> inline and detailed in `DEVLOG.md`.

---

## What the brief fixed vs. what we decided

**Fixed by the brief:** Python + LangChain + LangGraph; Chinook in-memory
SQLite; the `State` schema; the node topology
(`verify_info → load_memory → supervisor → create_memory`, with `human_input`
looping into `verify_info`); two sub-agents (music catalog, invoice) +
supervisor; the four catalog tools and three invoice tools by exact signature;
verification by ID/email/phone with HITL; long-term memory for preferences.

**Left to us (the 14 decisions below):** model, agent abstraction, verification
mechanics, HITL placement, memory architecture, memory-update policy, supervisor
coordination, state details, preference read-path, catalog matching, file
layout, entrypoint, and the invoice→employee mapping.

---

## 1. LLM provider & model
- **Question:** Which model powers the agents (tool-calling reliability,
  structured output, cost)?
- **Options:** OpenAI GPT-4o-mini · Anthropic Claude · Google Gemini.
- **Decision:** **Gemini Flash** via `langchain-google-genai`,
  `temperature=0`, `max_retries=3`.
- **Why:** free tier, easy access, good tool-calling. `temperature=0` for
  deterministic demos; `max_retries=3` to ride out free-tier 429s.
- **Refined later:** model id set to `gemini-3.1-flash-lite-preview`
  (15 RPM vs 5 RPM on flash 2.5) — fewer 429s during the recorded demo.
- **Where:** `src/config.py`.

## 2. Form factor — notebook vs `.py`
- **Question:** Build as a Jupyter notebook (the brief's deliverable) or a `.py`
  codebase?
- **Decision:** **Pure `.py`** package — the notebook deliverable was authorized
  as waived.
- **Why:** modular, testable, diffable, far easier to navigate than one giant
  notebook.
- **Where:** the whole `src/` package.

## 3. Agent abstraction level
- **Question:** Prebuilt agents vs hand-rolled for the sub-agents, supervisor,
  and outer graph?
- **Decision:** prebuilt agents for the two sub-agents +
  **`langgraph-supervisor`** for routing + a **hand-rolled `StateGraph`** for the
  outer topology.
- **Why:** the sub-agents are standard ReAct loops (prebuilt handles the
  boilerplate); the supervisor pattern is exactly what `langgraph-supervisor`
  is for; the outer five-node topology is bespoke and must be hand-built.
- **Refined later:** `create_react_agent` is deprecated on the installed stack →
  switched to `langchain.agents.create_agent`; the music agent's dynamic prompt
  moved to the `dynamic_prompt` middleware.
- **Where:** `src/agents.py`, `src/graph.py`.

## 4. Customer verification mechanics (+ Customer ≡ User)
- **Question:** How to turn free text ("my phone is +55 (12) 3923-5555") into a
  verified `customer_id`? And are "Customer" and "User" the same thing?
- **Decision:** an **LLM structured-output call** extracts the identifier; a
  **deterministic SQL lookup** maps email/phone → canonical `customer_id`.
  **Customer and User are the same entity.**
- **Why:** keep the fuzzy part (parsing messy phone formats) in the LLM and the
  exact part (identity → ID) in SQL — more reliable and more defensible.
- **Where:** `src/verification.py`; term defined in `CONTEXT.md`.

## 5. Human-in-the-loop placement
- **Question:** One centralized `interrupt()` or several scattered through the
  graph?
- **Decision:** a **single `interrupt()` inside `verify_info`**, acting as an
  upstream **gate** — the supervisor only runs after a valid `customer_id`
  exists.
- **Why:** enforces "verify before answering sensitive queries" structurally;
  the diagram's `human_input → verify_info` self-loop matches this; far cleaner
  to demo than interrupts buried in the sub-agents.
- **Where:** `src/verification.py` (`verify_info`); see `docs/adr/0001`.

## 6. Memory architecture
- **Question:** How to implement the two required memories?
- **Decision:** **`InMemorySaver`** (session/short-term, also enables
  `interrupt`/resume) + **`InMemoryStore`** (long-term), keyed by
  `("memory_profile", customer_id)`, holding a **structured `PreferenceProfile`**
  (`favorite_artists`, `favorite_genres`, `notes`).
- **Why:** zero-install, RAM-only (matches "in-memory store"); per-`customer_id`
  keying gives tenant isolation; a structured profile defends better than a
  freeform blob.
- **Where:** `src/memory.py`, `src/graph.py`.

## 7. When to update long-term memory
- **Question:** Write preferences every turn, gate it, or only at conversation
  end?
- **Decision:** **Option B — gated**: `create_memory` runs only when the
  `music_catalog` agent was engaged, with a **PII-excluding extraction prompt**
  and **merge semantics** (existing profile in → full updated profile out).
- **Why:** end-of-conversation writes are useless with a volatile RAM store;
  gating to music turns also keeps financial data out of the profile
  (data minimization); the scoped prompt covers mixed turns that still touch
  invoices.
- **Refined later:** the gate's "music engaged?" detection depends on
  `output_mode="full_history"` so sub-agent tool calls reach the outer state
  (see DEVLOG #6).
- **Where:** `src/memory.py` (`create_memory`).

## 8. Supervisor multi-step coordination (+ identity injection)
- **Question:** How does one turn fan out to *both* sub-agents? And how does the
  invoice tool get `customer_id`?
- **Decision:** **sequential handoffs** + a **multi-intent supervisor prompt**;
  `customer_id` is **injected from verified state via `InjectedState`** (hidden
  from the LLM), never supplied by the model.
- **Why:** sequential is simpler and reliable on the free tier; injection means
  a verified customer can't pass another's id, and the model can't hallucinate
  it — the trust boundary stays in code.
- **Where:** `src/agents.py` (supervisor prompt), `src/invoice_tools.py`
  (`InjectedState`); see `docs/adr/0001`.

## 9. State schema details
- **Question:** Use the imported-but-unused `RemainingSteps`? What
  `recursion_limit`?
- **Decision:** include **`remaining_steps`** and set **`recursion_limit=50`**.
- **Why:** `remaining_steps` lets the ReAct agents stop gracefully near the
  limit and is *required* by `langgraph-supervisor`; 50 sits comfortably above
  the ~22-step worst-case turn while still catching runaway loops.
- **Refined later:** needed two schemas — `AgentState` (no managed channel) for
  `create_agent` sub-agents, `State` (with `remaining_steps`) for the supervisor
  + outer graph (see DEVLOG #5).
- **Where:** `src/state.py`, `recursion_limit` in `src/main.py`.

## 10. Preference read-path
- **Question:** How do stored preferences reach the agent so "songs that match
  my preferences" works?
- **Decision:** `load_memory` flattens the profile into `loaded_memory`, then a
  **dynamic prompt** on the **music_catalog agent** injects it into that agent's
  system prompt at runtime.
- **Why:** keeps preferences out of the visible transcript (cleaner than adding
  a message) and puts them exactly where recommendations are made.
- **Where:** `src/memory.py` (`load_memory`), `src/agents.py`
  (`_music_system_prompt` via `dynamic_prompt`).

## 11. Catalog tool matching
- **Question:** Exact vs fuzzy matching? What does "similar artists" mean? SQL
  safety?
- **Decision:** **fuzzy `LIKE '%value%'`** (case-insensitive) everywhere;
  **"similar artists" = fuzzy name match** (Chinook has no similarity data);
  **parameterized SQL** throughout.
- **Why:** "Rolling Stones" must find "The Rolling Stones"; a genre-similarity
  engine isn't supported by the data; parameterization prevents SQL injection.
- **Where:** `src/catalog_tools.py`, `src/database.py` (`run_query`).

## 12. File / module layout
- **Question:** `src/` package or flat?
- **Decision:** **`src/` package** — `config`, `database`, `catalog_tools`,
  `invoice_tools`, `verification`, `memory`, `state`, `agents`, `graph`, `main`.
- **Why:** one concern per file; `graph.py` is the assembly point; `main.py` is
  the only runnable (and the demo script).
- **Where:** the `src/` directory.

## 13. Entrypoint
- **Question:** Scripted demo vs interactive REPL?
- **Decision:** an **interactive REPL** (`main.py`) with `:new` for a fresh
  session.
- **Why:** the human-in-the-loop interrupt/resume is far more convincing on
  camera when a human types the credentials live.
- **Where:** `src/main.py`.

## 14. Invoice → Employee mapping
- **Question:** What is "the employee associated with an invoice" in Chinook?
- **Decision:** `Invoice → Customer.SupportRepId → Employee`, scoped with
  `WHERE InvoiceId = :inv AND CustomerId = :verified_id`.
- **Why:** Chinook has no direct invoice→employee link; the support rep of the
  owning customer is the only coherent reading; the scope clause + injected
  `customer_id` prevents reading another customer's invoice.
- **Where:** `src/invoice_tools.py` (`get_employee_by_invoice_and_customer`).
