from langgraph.graph import StateGraph, START, END

from chatbot_agent.state import State
from chatbot_agent.nodes.chatbot import chatbot

builder = StateGraph(State)

builder.add_node("chatbot", chatbot)

builder.add_edge(START, "chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile()