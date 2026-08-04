from pathlib import Path
import sys
from langchain_core.messages import HumanMessage


ROOT_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = ROOT_DIR / "src"

for path in (ROOT_DIR, SRC_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from chatbot_agent.graph import build_graph
from langgraph.checkpoint.postgres import PostgresSaver
from config.settings import settings

checkpoint_db_url = settings.database_url.replace(
    "postgresql+psycopg://",
    "postgresql://",
)

config = {
    "configurable": {
        "thread_id": "terminal-user"
    }
}

with PostgresSaver.from_conn_string(checkpoint_db_url) as checkpointer:
    # checkpointer.setup()

    graph = build_graph(checkpointer)

    while True:
        question = input("You: ")

        if question.lower() == "exit":
            break

        result = graph.invoke(
            {
                "messages": [HumanMessage(content=question)]
            },
            config=config,
        )

        print("Bot:", result["messages"][-1].content)