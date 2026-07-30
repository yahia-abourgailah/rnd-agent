"""Interactive REPL for the chatbot agent.

Usage: python -m chatbot_agent.app
"""

import logging

from langchain_core.messages import AIMessage, HumanMessage

from chatbot_agent.graph import build_graph
from config.settings import settings

_EXIT_COMMANDS = {"exit", "quit"}


def main() -> None:
    logging.basicConfig(level=settings.log_level)
    graph = build_graph()
    # Carried across turns so follow-ups ("and in New Cairo?") resolve against
    # what was already asked; each turn previously started from an empty state.
    history: list = []

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

        history.append(HumanMessage(content=question))
        result = graph.invoke({"messages": history})
        history = result["messages"]

        last = history[-1]
        print("Bot:", last.content if isinstance(last, AIMessage) else last)


if __name__ == "__main__":
    main()
