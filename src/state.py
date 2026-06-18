"""Graph state schemas (decision: grill #8 & #9).

Two schemas are needed because of conflicting library constraints on LangChain
v1 / langgraph 1.x:

- `AgentState` (no `remaining_steps`) — used by the two `create_agent`
  sub-agents. `create_agent` rejects managed channels in its state_schema.
- `State` (adds `remaining_steps`) — used by `create_supervisor` (its internal
  create_react_agent REQUIRES `remaining_steps`) and by the outer graph.

Both share `customer_id` (for InjectedState) and `loaded_memory`, so those
values propagate across every layer.
"""

from typing import Annotated

from langgraph.graph.message import AnyMessage, add_messages
from langgraph.managed.is_last_step import RemainingSteps
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """State for the create_agent sub-agents (no managed channels allowed)."""

    customer_id: str
    messages: Annotated[list[AnyMessage], add_messages]
    loaded_memory: str


class State(AgentState):
    """Outer-graph + supervisor state. Adds the managed step counter that
    langgraph-supervisor requires and that gives a graceful stop near the
    recursion limit (grill #9)."""

    remaining_steps: RemainingSteps
