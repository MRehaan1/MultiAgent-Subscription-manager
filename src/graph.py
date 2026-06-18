"""Outer workflow assembly (Task 8).

Topology (from the brief's diagram):
    START -> verify_info -> load_memory -> supervisor -> create_memory -> END

verify_info is the HITL gate (interrupt loops back into itself on its own).
Compiled with an InMemorySaver (session memory) + InMemoryStore (long-term
memory) per decision grill #6.
"""

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.store.memory import InMemoryStore

from .agents import supervisor
from .memory import create_memory, load_memory
from .state import State
from .verification import verify_info


def build_graph():
    builder = StateGraph(State)

    builder.add_node("verify_info", verify_info)
    builder.add_node("load_memory", load_memory)
    builder.add_node("supervisor", supervisor)
    builder.add_node("create_memory", create_memory)

    builder.add_edge(START, "verify_info")
    builder.add_edge("verify_info", "load_memory")
    builder.add_edge("load_memory", "supervisor")
    builder.add_edge("supervisor", "create_memory")
    builder.add_edge("create_memory", END)

    checkpointer = InMemorySaver()  # short-term / session memory (+ enables interrupt)
    store = InMemoryStore()         # long-term / cross-session preference memory
    return builder.compile(checkpointer=checkpointer, store=store)


graph = build_graph()
