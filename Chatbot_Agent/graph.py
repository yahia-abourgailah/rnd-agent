from langgraph.graph import StateGraph, START, END

from state import State
from nodes.chatbot import chatbot

builder = StateGraph(State)

builder.add_node("chatbot", chatbot)

builder.add_edge(START, "chatbot")
builder.add_edge("chatbot", END)

graph = builder.compile()