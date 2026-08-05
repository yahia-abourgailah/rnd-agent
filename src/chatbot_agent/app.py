"""Interactive REPL for the chatbot agent.

Usage: python -m chatbot_agent.app [conversation_id]

Shares the Postgres checkpointer with the HTTP endpoint, so a conversation
started here can be continued over the API with the same id.
"""

import logging
import sys
import uuid

from langchain_core.messages import AIMessage, HumanMessage

from chatbot_agent.checkpointer import conversation_checkpointer
from chatbot_agent.graph import build_graph
from config.settings import settings

_EXIT_COMMANDS = {"exit", "quit"}


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    conversation_id = sys.argv[1] if len(sys.argv) > 1 else str(uuid.uuid4())
    config = {"configurable": {"thread_id": conversation_id}}
    print(f"conversation: {conversation_id}")

    with conversation_checkpointer() as checkpointer:
        graph = build_graph(checkpointer)

        while True:
            try:
                question = input("You: ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not question:
                continue
            if question.lower() in _EXIT_COMMANDS:
                return

            result = graph.invoke(
                {"messages": [HumanMessage(content=question)]},
                config=config,
            )
            last = result["messages"][-1]
            print("Bot:", last.content if isinstance(last, AIMessage) else last)


if __name__ == "__main__":
    main()
