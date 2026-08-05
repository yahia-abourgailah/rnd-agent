"""Agent graph: chatbot <-> tools until the model answers without a tool call.

    START -> chatbot -> (tool call?) -> tools -> chatbot -> ... -> END

The edge back from `tools` to `chatbot` is what makes the SQL tools usable: the
model emits a tool call, ToolNode executes it, and the result returns as a
ToolMessage for the model to read before it answers. Without that loop the
bound tools are dead weight — the graph would end on the tool-call message.
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from chatbot_agent.nodes.chatbot import chatbot
from chatbot_agent.state import State
from chatbot_agent.tools.postgres import TOOLS


def build_graph(checkpointer: BaseCheckpointSaver | None = None) -> CompiledStateGraph:
    """Compile the agent graph.

    Pass a checkpointer to persist conversation state; without one the graph is
    single-turn. A function rather than a module-level singleton so compiling
    never happens at import and tests get a fresh graph per case.
    """
    builder = StateGraph(State)
    builder.add_node("chatbot", chatbot)
    builder.add_node("tools", ToolNode(TOOLS))

    builder.add_edge(START, "chatbot")
    # tools_condition routes to "tools" when the last message carries tool
    # calls, and to END when it doesn't.
    builder.add_conditional_edges("chatbot", tools_condition, {"tools": "tools", END: END})
    builder.add_edge("tools", "chatbot")

    return builder.compile(checkpointer=checkpointer)
