# Technical Journey — Demo Walkthrough

A code-level trace of the recorded demo: for each user turn, which **nodes** and
**tools** ran, in which **files/functions**, and **how** they were invoked.

**Demo transcript:**
1. `My phone number is +55 (12) 3923-5555. How much was my most recent purchase? What albums do you have by the Rolling Stones?`
2. `List some songs that match my preferences?`

Both turns share one session (`thread_id="session-1"`), so the checkpointer
carries state between them.

---

## Files in play

| File | Role |
|---|---|
| `src/main.py` | REPL; calls `graph.invoke()` and handles interrupts |
| `src/graph.py` | outer `StateGraph`; nodes + edges; `compile(checkpointer, store)` |
| `src/verification.py` | `verify_info` node — identifier extraction + SQL lookup |
| `src/memory.py` | `load_memory` + `create_memory` nodes; `PreferenceProfile` |
| `src/agents.py` | `music_agent`, `invoice_agent` (`create_agent`) + `supervisor` |
| `src/invoice_tools.py` | invoice tools (`customer_id` via `InjectedState`) |
| `src/catalog_tools.py` | music tools (fuzzy `LIKE`) |
| `src/database.py` | Chinook engine + parameterized `run_query` |

**Graph topology** (`src/graph.py`):
`START → verify_info → load_memory → supervisor → create_memory → END`,
compiled with `InMemorySaver` (session) + `InMemoryStore` (long-term).

---

## Turn 1 — "phone + purchase + Rolling Stones albums"

### Entry
`main.py:main()` reads the line → `_run({"messages": [{"role":"user","content": <turn1>}]}, config)`
→ `graph.invoke(...)` with `config={"configurable":{"thread_id":"session-1"}, "recursion_limit":50}`.

### Node 1 — `verify_info`  (`src/verification.py`)
- No `customer_id` in state yet → run verification.
- `_latest_user_text(messages)` → the turn-1 text.
- `_extract_identifier(text)` → **LLM call**: `model.with_structured_output(IdentifierExtraction)`
  → `{identifier_type: "phone", value: "+55 (12) 3923-5555"}`.
- `_lookup_customer_id(parsed)` → phone branch → `run_query("SELECT CustomerId, Phone FROM Customer WHERE Phone IS NOT NULL")`
  (`src/database.py`), digits-normalized compare → **CustomerId = 1** (Luís Gonçalves).
- Returns `{"customer_id": "1"}`. No `interrupt()` (identifier was valid).

### Node 2 — `load_memory`  (`src/memory.py`)
- `store.get(("memory_profile","1"), "user_memory")` → **None** (first turn).
- Returns `{"loaded_memory": "No saved preferences yet."}`.

### Node 3 — `supervisor`  (`src/agents.py`, compiled `create_supervisor` graph)
The internal `router_supervisor` (a ReAct agent) sees two intents and delegates
sequentially via handoff tools:

1. **`transfer_to_invoice_info`** → `invoice_agent` runs:
   - **LLM call** decides to call `get_invoices_by_customer_sorted_by_date`
     (`src/invoice_tools.py`).
   - `customer_id` is **injected from state** (`InjectedState("customer_id")` → `"1"`),
     not chosen by the model.
   - Tool runs `run_query("... FROM Invoice WHERE CustomerId=:c ORDER BY InvoiceDate DESC", {"c":"1"})`
     → most recent = **Invoice #382, 2025-08-07, $8.91**.
   - Per its lane-discipline prompt, the agent answers only invoices, then hands back.
2. **`transfer_to_music_catalog`** → `music_agent` runs:
   - System prompt built by the `dynamic_prompt` middleware `_music_system_prompt`,
     injecting `loaded_memory` (here "No saved preferences yet.").
   - **LLM call** decides to call `get_albums_by_artist(artist="Rolling Stones")`
     (`src/catalog_tools.py`).
   - Tool runs `run_query("... WHERE ar.Name LIKE :p ...", {"p":"%Rolling Stones%"})`
     → fuzzy-matches **"The Rolling Stones"** → Hot Rocks / No Security / Voodoo Lounge.
   - Hands back.
3. `router_supervisor` **combines** both results into the final answer.

`output_mode="full_history"` propagates every sub-agent message (handoffs, tool
calls, tool results) up to the outer state — needed by Node 4.

### Node 4 — `create_memory`  (`src/memory.py`)
- `_music_engaged(messages)` scans the (now full-history) messages for catalog
  tool calls → finds `get_albums_by_artist` → **True** (gate opens).
- Existing profile: none → empty `PreferenceProfile`.
- **LLM call**: `model.with_structured_output(PreferenceProfile)` with the
  PII-excluding system prompt + existing profile + conversation
  → `{favorite_artists: ["The Rolling Stones"], ...}`.
- `store.put(("memory_profile","1"), "user_memory", {...})`.

### Exit
`main.py:_last_text()` flattens the final message blocks → prints the fused
invoice + albums answer.

**LLM calls this turn:** ~5 (extract identifier, supervisor routing ×, invoice
agent, music agent, memory extraction).

---

## Turn 2 — "songs that match my preferences"

Same `thread_id` → the **checkpointer restores** `customer_id="1"` and prior
messages.

### Node 1 — `verify_info`
- `state["customer_id"] == "1"` already set → returns `{}` immediately (no
  re-verification, no LLM call). This is the "short memory holds customer id
  throughout the session" behaviour.

### Node 2 — `load_memory`
- `store.get(("memory_profile","1"), "user_memory")` → **{favorite_artists:
  ["The Rolling Stones"]}**.
- Returns `{"loaded_memory": "Favorite artists: The Rolling Stones"}`.

### Node 3 — `supervisor`
- Router sees a music/recommendation request → **`transfer_to_music_catalog`**.
- `music_agent`'s `dynamic_prompt` injects `loaded_memory` =
  "Favorite artists: The Rolling Stones" → the model now *knows* the taste.
- **LLM call** → `get_tracks_by_artist(artist="The Rolling Stones")`
  (`src/catalog_tools.py`) → `run_query("... WHERE ar.Name LIKE :p ...", {"p":"%The Rolling Stones%"})`
  → 19th Nervous Breakdown, Paint It Black, Satisfaction, Ruby Tuesday, …
- Router finalizes.

### Node 4 — `create_memory`
- Music engaged again → re-extracts and **merges** (still The Rolling Stones) →
  `store.put(...)` (idempotent).

### Exit
Prints the list of Rolling Stones songs — the personalization loop closed.

---

## The key wiring, in one glance

| Concern | Mechanism | File |
|---|---|---|
| Identity → `customer_id` | structured LLM extract + SQL lookup | `verification.py` |
| Customer can't read others' data | `InjectedState("customer_id")` + SQL scope | `invoice_tools.py` |
| Preferences in → out | `InMemoryStore` keyed by `customer_id` | `memory.py` |
| Preferences reach the agent | `dynamic_prompt` middleware | `agents.py` |
| Multi-intent in one turn | sequential handoffs + `output_mode="full_history"` | `agents.py` |
| Fuzzy artist match | `LIKE '%name%'` + parameterized query | `catalog_tools.py` |
| Session memory / resume | `InMemorySaver` checkpointer + `thread_id` | `graph.py`, `main.py` |
