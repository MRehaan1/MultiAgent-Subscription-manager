"""Interactive REPL entrypoint (decision: grill #12 & #13).

Run from the project root:   python -m src.main

Commands:
    :new    start a fresh session (new thread_id) — use this to demo Test Case 2
    :quit   exit

Human-in-the-loop: when verification interrupts, the bot's question is printed
and YOU type the credentials live; the graph then resumes.
"""

import logging

from langgraph.types import Command

# Silence the harmless "wrote to unknown channel remaining_steps, ignoring it"
# log: the managed RemainingSteps value can't cross the supervisor->outer-graph
# boundary, but it is required by langgraph-supervisor (see state.py). The graph
# behaves correctly; we just keep the demo output clean.
logging.getLogger("langgraph").setLevel(logging.ERROR)

from .graph import graph

RECURSION_LIMIT = 50  # grill #9: comfortably above the ~22-step worst-case turn


def _config(thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": RECURSION_LIMIT,
    }


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
    print("Music Store Customer Support  (type :new for a fresh session, :quit to exit)\n")
    session = 1
    config = _config(f"session-{session}")

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
            config = _config(f"session-{session}")
            print(f"\n--- Started new session-{session} (no prior verification/memory) ---\n")
            continue

        result = _run({"messages": [{"role": "user", "content": user}]}, config)
        print(f"\nBot: {_last_text(result)}\n")


if __name__ == "__main__":
    main()
