from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

for path in (ROOT_DIR, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot_agent.graph import graph


while True:
    question = input("You: ")

    if question.lower() == "exit":
        break

    result = graph.invoke({"messages": [question]})

    print("Bot:", result["messages"][-1].content)