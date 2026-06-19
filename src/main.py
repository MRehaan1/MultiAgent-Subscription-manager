"""Interactive REPL entrypoint (decision: grill #12 & #13).

Run from the project root:   python -m src.main

Commands:
    :new    start a fresh session (new thread_id) — use this to demo Test Case 2
    :quit   exit

Human-in-the-loop: when verification interrupts, the bot's question is printed
and YOU type the credentials live; the graph then resumes.

(Call tracing will be added later via Langfuse.)
"""

import logging

from langgraph.types import Command

# Silence the harmless "wrote to unknown channel remaining_steps, ignoring it"
# log (see state.py) — the graph behaves correctly; we just keep output clean.
logging.getLogger("langgraph").setLevel(logging.ERROR)

from .graph import graph
from .tracing import flush_langfuse, get_langfuse_handler

RECURSION_LIMIT = 50  # grill #9: comfortably above the ~22-step worst-case turn

_LANGFUSE = get_langfuse_handler()  # None if keys are not set


def _config(thread_id: str, customer_id: str | None = None) -> dict:
    cfg = {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }
    if _LANGFUSE is not None:
        cfg["callbacks"] = [_LANGFUSE]
        # Langfuse best practices (instrumentation.md): a descriptive trace name,
        # session grouping, and per-customer attribution.
        cfg["run_name"] = "music-support-turn"
        meta = {"langfuse_session_id": thread_id}
        if customer_id:
            meta["langfuse_user_id"] = customer_id
        cfg["metadata"] = meta
    return cfg


def _current_customer_id(thread_id: str) -> str | None:
    """The verified customer for this session, if verification already happened."""
    try:
        return graph.get_state({"configurable": {"thread_id": thread_id}}).values.get("customer_id")
    except Exception:
        return None


def _last_text(result: dict) -> str:
    messages = result.get("messages") or []
    if not messages:
        return "(no response)"
    content = getattr(messages[-1], "content", "")
    # Gemini returns content as a list of blocks; flatten to plain text.
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return "".join(parts).strip() or "(no response)"
    return content or "(no response)"


def _run(invoke_input, config: dict) -> dict:
    """Invoke the graph, resolving any HITL interrupts via live console input."""
    result = graph.invoke(invoke_input, config)
    while "__interrupt__" in result:
        prompt = result["__interrupt__"][0].value
        answer = input(f"\n[verification needed] {prompt}\nYou: ")
        result = graph.invoke(Command(resume=answer), config)
    return result


def main():
    print("Music Store Customer Support  (type :new for a fresh session, :quit to exit)")
    print(f"Langfuse tracing: {'ON' if _LANGFUSE is not None else 'off (no keys set)'}\n")
    session = 1
    thread_id = f"session-{session}"

    while True:
        try:
            user = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user:
            continue
        if user == ":quit":
            print("Goodbye!")
            break
        if user == ":new":
            session += 1
            thread_id = f"session-{session}"
            print(f"\n--- Started new {thread_id} (no prior verification/memory) ---\n")
            continue

        # Per-turn config so the trace carries the (now-known) verified customer.
        config = _config(thread_id, _current_customer_id(thread_id))
        result = _run({"messages": [{"role": "user", "content": user}]}, config)
        print(f"\nBot: {_last_text(result)}\n")

    flush_langfuse()  # ensure batched traces are sent before exit


if __name__ == "__main__":
    main()
